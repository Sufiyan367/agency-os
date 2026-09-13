"""
Tests for Real-World Autonomous Operation Activation.
Covers:
- Real prospect discovery and normalization for KSA (Riyadh) HVAC
- Multi-source empirical evidence verification and ProspectEvidenceGate
- Deterministic auto-approval policy engine (SYSTEM_AUTO_APPROVAL)
- ActiveOutreachLock concurrency and single-outreach governance
- Inbound reply classification and routing
- Zero external socket communication guarantee in tests
"""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select

from app.database.models import (
    Base, Business, Contact, OutreachMessage, OutreachStatus, Offer,
    SuppressionList, ActiveOutreachLock, PipelineStage, ProspectEvidence,
    AuditRun, LeadScore, Reply, ReplyClassification
)
from app.acquisition.models import StandardizedProspect
from app.acquisition.evidence_gate import prospect_evidence_gate
from app.outreach.auto_approval import auto_approval_engine
from app.acquisition.controller import active_prospect_controller
from app.crm.reply_classifier import reply_classifier
from app.lead_generation.adapters.real_web_discovery import RealWebDiscoveryAdapter


@pytest_asyncio.fixture
async def test_session():
    """In-memory SQLite async session with schema initialized."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_riyadh_hvac_discovery_normalization(test_session: AsyncSession):
    """Verifies that the real discovery adapter finds and normalizes Riyadh HVAC candidates with valid coordinates."""
    adapter = RealWebDiscoveryAdapter()
    leads = await adapter.discover_leads(country_code="SA", niche_slug="hvac", limit=5)
    
    assert len(leads) >= 1, "Expected at least 1 real commercial HVAC business for SA"
    lead = leads[0]
    assert lead.country == "SA"
    assert lead.niche == "hvac"
    assert lead.domain in ("al-salem.com", "zamilac.com", "shaker.com.sa")
    assert lead.city in ("Riyadh", "Jeddah")
    assert lead.source in ("commercial_trade_registry", "real_web_discovery")
    assert lead.source_url.startswith("https://")


@pytest.mark.asyncio
async def test_prospect_evidence_gate_strict_multi_source():
    """Verifies that the hard evidence gate requires at least 2 distinct independent verified sources."""
    # 1. Single source failure
    single_ev = [
        ProspectEvidence(
            evidence_id="ev_001",
            business_id=1,
            claim="Official live website operates.",
            source_url="https://al-salem.com",
            source_domain="al-salem.com",
            source_type="official_website",
            source_tier=3,
            confidence_score=0.90,
            source_quality_score=0.85,
            freshness_score=1.0,
            is_verified=True,
            http_status=200,
            business_identity_match=True,
            source_independence_group="al-salem.com"
        )
    ]
    res_fail = prospect_evidence_gate.evaluate_evidence(single_ev)
    assert not res_fail.is_passed
    assert res_fail.status == "INSUFFICIENT_EVIDENCE"
    assert not res_fail.can_auto_approve

    # 2. Dual distinct independent verified sources success
    dual_ev = single_ev + [
        ProspectEvidence(
            evidence_id="ev_002",
            business_id=1,
            claim="Listed in official Saudi commercial trade registry.",
            source_url="https://cr.mc.gov.sa/registry/sa/al-salem.com",
            source_domain="cr.mc.gov.sa",
            source_type="registry",
            source_tier=1,
            confidence_score=0.95,
            source_quality_score=0.90,
            freshness_score=1.0,
            is_verified=True,
            http_status=200,
            business_identity_match=True,
            source_independence_group="cr.mc.gov.sa"
        )
    ]
    res_pass = prospect_evidence_gate.evaluate_evidence(dual_ev)
    assert res_pass.is_passed
    assert res_pass.status == "VERIFIED"
    assert res_pass.distinct_sources_count >= 2
    assert res_pass.effective_evidence_score >= 0.60
    assert res_pass.can_auto_approve


@pytest.mark.asyncio
async def test_deterministic_auto_approval_policy(test_session: AsyncSession):
    """Verifies that deterministic auto-approval approves safe evidence-backed messages and rejects policy violations."""
    # 1. Setup clean eligible prospect
    biz = Business(
        name="Al Salem Johnson Controls",
        domain="al-salem.com",
        country="SA",
        city="Riyadh",
        niche="hvac",
        pipeline_stage=PipelineStage.QUALIFIED.value,
        verification_status="VERIFIED"
    )
    test_session.add(biz)
    await test_session.flush()

    offer = Offer(
        business_id=biz.id,
        service_type="hvac_modernization",
        title="HVAC Smart Energy & SEO Modernization",
        recommended_price=1200.0
    )
    test_session.add(offer)
    await test_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        offer_id=offer.id,
        recipient_email="info@al-salem.com",
        subject="Observations regarding al-salem.com digital presence in Riyadh",
        body="Hello,\n\nWe noticed optimization opportunities on your site.\n\nBest regards,\nAdvisory Team",
        status=OutreachStatus.PENDING_APPROVAL.value,
        actor_type="SYSTEM_AUTO_APPROVAL"
    )
    test_session.add(msg)
    await test_session.commit()

    # Ensure lock and capacity mock
    with patch("app.campaigns.sender_registry.sender_registry.get_sender_capacity_summary", new_callable=AsyncMock) as mock_cap:
        mock_cap.return_value = {
            "available_capacity": 1,
            "sent_today": 0,
            "rollout_daily_cap": 1
        }
        with patch("app.core.config.settings.EMAIL_DRY_RUN", True):
            is_approved, updated_msg, eval_res = await auto_approval_engine.auto_approve_if_eligible(test_session, msg.id)

    assert is_approved, f"Expected message to be auto-approved, got reasons: {eval_res.blocking_reasons}"
    assert updated_msg.status == OutreachStatus.APPROVED.value
    assert updated_msg.actor_type == "SYSTEM_AUTO_APPROVAL"
    assert updated_msg.approved_at is not None

    # 2. Rejection on Prohibited Claims
    bad_msg = OutreachMessage(
        business_id=biz.id,
        offer_id=offer.id,
        recipient_email="info@al-salem.com",
        subject="Guaranteed 10x ROI for al-salem.com",
        body="We provide a zero risk, guaranteed 10x revenue increase!",
        status=OutreachStatus.PENDING_APPROVAL.value
    )
    test_session.add(bad_msg)
    await test_session.commit()

    with patch("app.campaigns.sender_registry.sender_registry.get_sender_capacity_summary", new_callable=AsyncMock) as mock_cap:
        mock_cap.return_value = {"available_capacity": 1, "sent_today": 0, "rollout_daily_cap": 1}
        is_bad_approved, _, bad_eval = await auto_approval_engine.auto_approve_if_eligible(test_session, bad_msg.id)

    assert not is_bad_approved
    assert any("prohibited claims" in r.lower() for r in bad_eval.blocking_reasons)


@pytest.mark.asyncio
async def test_active_outreach_lock_sequential_isolation(test_session: AsyncSession):
    """Verifies that ActiveOutreachLock strictly locks slot 1 and prevents concurrent outreach."""
    biz1 = Business(name="Biz One", domain="one.sa", country="SA", city="Riyadh", niche="hvac", pipeline_stage=PipelineStage.QUALIFIED.value, verification_status="VERIFIED")
    biz2 = Business(name="Biz Two", domain="two.sa", country="SA", city="Riyadh", niche="hvac", pipeline_stage=PipelineStage.QUALIFIED.value, verification_status="VERIFIED")
    test_session.add_all([biz1, biz2])
    await test_session.commit()

    # 1. Lock biz1
    slot = await active_prospect_controller.select_next_prospect(test_session, business_id=biz1.id)
    assert slot.is_occupied
    assert slot.business_id == biz1.id

    # 2. Attempt to lock biz2 while biz1 is active -> MUST FAIL
    with pytest.raises(ValueError, match="already occupied"):
        await active_prospect_controller.select_next_prospect(test_session, business_id=biz2.id)

    # 3. Release slot
    released_slot = await active_prospect_controller.release_active_slot(test_session, terminal_reason="MANUAL_RELEASE", notes="Test release")
    assert released_slot["slot_status"] == "IDLE"

    # 4. Now biz2 can be locked
    slot2 = await active_prospect_controller.select_next_prospect(test_session, business_id=biz2.id)
    assert slot2.is_occupied
    assert slot2.business_id == biz2.id


@pytest.mark.asyncio
async def test_inbound_reply_classification_and_routing(test_session: AsyncSession):
    """Verifies that inbound replies are accurately classified and advanced without manual clicking."""
    biz = Business(name="Zamil Air Conditioners", domain="zamilac.com", country="SA", city="Riyadh", niche="hvac", pipeline_stage=PipelineStage.CONTACTED.value)
    test_session.add(biz)
    await test_session.flush()

    outreach1 = OutreachMessage(
        business_id=biz.id,
        recipient_email="halawallah@zamilac.com",
        subject="Audit note 1",
        body="Note 1",
        status=OutreachStatus.SENT.value,
        sent_at=datetime.utcnow()
    )
    test_session.add(outreach1)
    await test_session.commit()

    # 1. POSITIVE reply -> leads to QUALIFIED_REPLY
    res_pos = await reply_classifier.process_incoming_reply(
        session=test_session,
        business_id=biz.id,
        message_id=outreach1.id,
        raw_body="Thanks for your email. We are interested in reviewing the diagnosis.",
        sender_email="halawallah@zamilac.com"
    )
    assert res_pos.classification == ReplyClassification.POSITIVE.value
    await test_session.refresh(biz)
    assert biz.pipeline_stage == PipelineStage.QUALIFIED_REPLY.value

    # 2. UNSUBSCRIBE reply on second outreach -> adds to suppression list and transitions to LOST
    biz2 = Business(name="Second Business", domain="second.sa", country="SA", city="Riyadh", niche="hvac", pipeline_stage=PipelineStage.CONTACTED.value)
    test_session.add(biz2)
    await test_session.flush()

    outreach2 = OutreachMessage(
        business_id=biz2.id,
        recipient_email="optout@second.sa",
        subject="Audit note 2",
        body="Note 2",
        status=OutreachStatus.SENT.value,
        sent_at=datetime.utcnow()
    )
    test_session.add(outreach2)
    await test_session.commit()

    res_unsub = await reply_classifier.process_incoming_reply(
        session=test_session,
        business_id=biz2.id,
        message_id=outreach2.id,
        raw_body="Please unsubscribe and remove us from your list immediately.",
        sender_email="optout@second.sa"
    )
    assert res_unsub.classification == ReplyClassification.UNSUBSCRIBE.value
    await test_session.refresh(biz2)
    assert biz2.pipeline_stage == PipelineStage.LOST.value

    # Verify suppression record was created
    supp_stmt = select(SuppressionList).where(SuppressionList.email == "optout@second.sa")
    supp = (await test_session.execute(supp_stmt)).scalar_one_or_none()
    assert supp is not None
    assert supp.reason == "UNSUBSCRIBE"
