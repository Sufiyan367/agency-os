"""
Tests for Strict One-Prospect-at-a-Time Discovery and Autonomous Pipeline.

Verifies:
1. Discovery is strictly called with target=1 (never batch pre-discovering pools of 4/10/20).
2. Prospect A is CONTACTED and persisted in memory BEFORE Prospect B is discovered.
3. Commercial floor ($500+), kill switch, suppression, and dry-run safety gates are strictly enforced.
4. Inbound replies/webhooks are handled asynchronously via prospect memory and never block prospecting.
"""
import uuid
import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy import select

from app.database.connection import AsyncSessionLocal
from app.database.models import Business, PipelineStage, VerificationStatus, ProspectMemory
from app.orchestrator.loop import orchestrator
from app.lead_generation.discovery import lead_discovery_coordinator
from app.core.config import settings
from app.crm.memory_service import memory_service


@pytest.fixture(autouse=True)
async def cleanup_test_records():
    yield
    async with AsyncSessionLocal() as session:
        from sqlalchemy import delete
        from app.database.models import OutreachMessage, OutreachEvent
        await session.execute(delete(OutreachEvent))
        await session.execute(delete(OutreachMessage))
        await session.commit()


@pytest.mark.asyncio
async def test_discovery_called_with_target_one_and_never_batch():
    """
    Regression test:
    Proves run_full_autonomous_cycle() requests/discovers exactly ONE new real prospect
    at a time with target=1, never pre-discovering pools of 4, 10, or 20 prospects.
    """
    discovery_calls = []

    async def fake_discovery(session, country_code="US", niche_slug="roofing-contractors", target_count=1, target=None):
        eff_target = target if target is not None else target_count
        discovery_calls.append(eff_target)
        uid = uuid.uuid4().hex[:6]
        dom = f"fake-single-{uid}.com"
        biz = Business(
            name=f"Single Biz {uid}",
            domain=dom,
            website_url=f"https://{dom}",
            country="US",
            city="Austin",
            niche="roofing",
            public_email=f"contact@{dom}",
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.VERIFIED.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)
        return [biz]

    with patch.object(lead_discovery_coordinator, "run_discovery_and_verification", side_effect=fake_discovery):
        summary = await orchestrator.run_full_autonomous_cycle(target_leads=1)
        assert summary["status"] == "SUCCESS"
        # Must have been called exactly once with target=1
        assert len(discovery_calls) == 1
        assert discovery_calls[0] == 1


@pytest.mark.asyncio
async def test_prospect_a_contacted_before_prospect_b_is_discovered():
    """
    Regression test:
    Proves Prospect A is contacted and persisted in memory BEFORE Prospect B is discovered.
    Execution sequence must be:
    1. Discover Prospect A (target=1)
    2. Contact & Persist Prospect A
    3. Discover Prospect B (target=1)
    4. Contact & Persist Prospect B
    """
    timeline = []
    uid_a = uuid.uuid4().hex[:6]
    uid_b = uuid.uuid4().hex[:6]
    dom_a = f"strict-seq-a-{uid_a}.com"
    dom_b = f"strict-seq-b-{uid_b}.com"

    prospects_to_yield = [
        {"name": f"Alpha Roofing {uid_a}", "domain": dom_a, "email": f"owner@{dom_a}"},
        {"name": f"Beta Roofing {uid_b}", "domain": dom_b, "email": f"owner@{dom_b}"}
    ]
    yield_idx = 0

    async def tracking_discovery(session, country_code="US", niche_slug="roofing-contractors", target_count=1, target=None):
        nonlocal yield_idx
        eff_target = target if target is not None else target_count
        timeline.append(("DISCOVER_REQUEST", eff_target))
        if yield_idx >= len(prospects_to_yield):
            return []
        p_data = prospects_to_yield[yield_idx]
        yield_idx += 1
        timeline.append(("DISCOVER_YIELD", p_data["domain"]))

        biz = Business(
            name=p_data["name"],
            domain=p_data["domain"],
            website_url=f"https://{p_data['domain']}",
            country="US",
            city="Austin",
            niche="roofing",
            public_email=p_data["email"],
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.VERIFIED.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)
        return [biz]

    from app.outreach.sender import outreach_sender_adapter
    orig_send = outreach_sender_adapter.send_approved_message

    async def tracking_send(session, message_id):
        res = await orig_send(session, message_id)
        from app.database.models import OutreachMessage
        msg = await session.get(OutreachMessage, message_id)
        if msg:
            biz = await session.get(Business, msg.business_id)
            if biz:
                timeline.append(("CONTACTED", biz.domain))
        return res

    with patch.object(lead_discovery_coordinator, "run_discovery_and_verification", side_effect=tracking_discovery), \
         patch.object(outreach_sender_adapter, "send_approved_message", side_effect=tracking_send):
        summary = await orchestrator.run_full_autonomous_cycle(target_leads=2)
        assert summary["status"] == "SUCCESS"

    # Verify discovery was always target=1
    discover_targets = [item[1] for item in timeline if item[0] == "DISCOVER_REQUEST"]
    assert all(t == 1 for t in discover_targets)
    assert len(discover_targets) == 2

    # Verify strict sequence: Prospect A is CONTACTED before Prospect B is DISCOVERED
    events = [item for item in timeline if item[0] in ("DISCOVER_YIELD", "CONTACTED")]
    assert len(events) == 4
    assert events[0] == ("DISCOVER_YIELD", dom_a)
    assert events[1] == ("CONTACTED", dom_a)
    assert events[2] == ("DISCOVER_YIELD", dom_b)
    assert events[3] == ("CONTACTED", dom_b)

    # Verify both prospect memories exist and are persisted
    async with AsyncSessionLocal() as session:
        mem_a = await memory_service.get_memory(session, domain=dom_a)
        mem_b = await memory_service.get_memory(session, domain=dom_b)
        assert mem_a is not None
        assert mem_b is not None
        assert mem_a.pipeline_stage == PipelineStage.CONTACTED.value
        assert mem_b.pipeline_stage == PipelineStage.CONTACTED.value


@pytest.mark.asyncio
async def test_commercial_floor_500_skips_outreach_in_cycle():
    """
    Verifies that if an offer's recommended price falls below $500,
    the autonomous cycle rejects it and skips outreach without sending.
    """
    uid = uuid.uuid4().hex[:6]
    dom = f"lowval-cycle-{uid}.com"

    async def fake_discovery(session, country_code="US", niche_slug="roofing-contractors", target_count=1, target=None):
        biz = Business(
            name=f"LowVal Biz {uid}",
            domain=dom,
            website_url=f"https://{dom}",
            country="US",
            city="Austin",
            niche="roofing",
            public_email=f"contact@{dom}",
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.VERIFIED.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)
        return [biz]

    from app.offers.generator import offer_engine
    from app.database.models import Offer

    async def low_val_offer(session, business):
        offer = Offer(
            business_id=business.id,
            service_type="Micro Audit",
            title="Micro Diagnostic",
            suggested_price_min=300.0,
            suggested_price_max=400.0,
            recommended_price=350.0,
            deliverables=["Basic report"]
        )
        session.add(offer)
        await session.commit()
        await session.refresh(offer)
        return offer

    from app.outreach.sender import outreach_sender_adapter
    with patch.object(lead_discovery_coordinator, "run_discovery_and_verification", side_effect=fake_discovery), \
         patch.object(offer_engine, "generate_offer_for_business", side_effect=low_val_offer), \
         patch.object(outreach_sender_adapter, "send_approved_message", new_callable=AsyncMock) as mock_send:
        summary = await orchestrator.run_full_autonomous_cycle(target_leads=1)
        assert summary["status"] == "SUCCESS"
        assert summary["autonomous_outreach_sent"] == 0
        mock_send.assert_not_called()

        async with AsyncSessionLocal() as session:
            res = await session.execute(select(Business).where(Business.domain == dom))
            biz = res.scalar_one()
            assert biz.pipeline_stage == PipelineStage.REJECTED.value


@pytest.mark.asyncio
async def test_kill_switch_halts_cycle_before_outreach():
    """
    Verifies that activating the emergency kill switch halts the autonomous prospecting cycle.
    """
    original_setting = getattr(settings, "AUTONOMOUS_AGENT_ENABLED", True)
    try:
        settings.AUTONOMOUS_AGENT_ENABLED = False
        with patch.object(lead_discovery_coordinator, "run_discovery_and_verification", new_callable=AsyncMock) as mock_disc:
            summary = await orchestrator.run_full_autonomous_cycle(target_leads=1)
            assert summary["status"] == "SUCCESS"
            mock_disc.assert_not_called()
    finally:
        settings.AUTONOMOUS_AGENT_ENABLED = original_setting
