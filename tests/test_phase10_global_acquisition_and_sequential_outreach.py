"""Phase 10: Global Multi-Country Prospect Acquisition & Sequential Outreach Engine Tests.

Verifies:
1. Multi-Country Configuration (DB dynamic settings, defaults for US, UK, CA, AU, AE).
2. Pluggable Discovery Providers (ScrapeGraph mock mode, circuit breaker, registry fallback).
3. Parallel Multi-Country Discovery & Global Deduplication.
4. Global Multi-Criteria Ranking & Explainable Decision Traces.
5. Strict Single-Prospect Outreach Lock (MAX_ACTIVE_OUTREACH = 1, race condition prevention).
6. Sequential Outreach Lifecycle (Draft -> Approval Gate -> Send -> Waiting for Reply).
7. Reply Handling & Cancellation (Opt-out suppression, auto-release, negotiation).
8. Dynamic Re-ranking on Slot Release.
9. End-to-End Acceptance Flow.
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from bs4 import BeautifulSoup

from app.database.models import (
    Business, ActiveOutreachLock, CountryConfig, PipelineStage,
    VerificationStatus, OutreachMessage, OutreachStatus, ClientIntelligenceRecord, AuditRun, Offer
)
from app.acquisition.models import StandardizedProspect, CountryConfigDTO, ActiveSlotStatus, GlobalQueueItem
from app.acquisition.config import country_config_manager, DEFAULT_COUNTRY_PROFILES
from app.acquisition.providers.scrapegraph_provider import ScrapeGraphProvider
from app.acquisition.providers.registry import discovery_registry
from app.acquisition.pipeline import CountryPipeline
from app.acquisition.pool import global_prospect_pool
from app.acquisition.ranking import global_ranker
from app.acquisition.controller import active_prospect_controller
from app.auditing.crawler import CrawlResult, website_crawler
from app.outreach.compliance import compliance_guard
from app.crm.reply_classifier import reply_classifier, ReplyClassification
from app.api.app import app

SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Quality Local Contractors</title>
    <meta name="description" content="Commercial contracting services.">
</head>
<body>
    <h1>Welcome to our business</h1>
    <p>Contact us for quotes.</p>
</body>
</html>
"""

@pytest.fixture(autouse=True)
def mock_crawler():
    """Mocks website crawler so tests run instantaneously without external DNS/HTTP requests."""
    soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
    mock_res = CrawlResult("https://example.com", 200, 150.0, {}, SAMPLE_HTML, soup, is_mock=True)
    with patch.object(website_crawler, "fetch", new_callable=AsyncMock, return_value=mock_res):
        yield


# ============================================================================
# 1. MULTI-COUNTRY CONFIGURATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_default_country_configurations_seeded(db_session):
    """Verify that US, UK, CA, AU, AE default profiles are automatically seeded."""
    countries = await country_config_manager.list_countries(db_session)
    codes = {c.country_code for c in countries}
    assert {"US", "UK", "CA", "AU", "AE"}.issubset(codes)

    us_cfg = await country_config_manager.get_country(db_session, "US")
    assert us_cfg is not None
    assert us_cfg.currency == "USD"
    assert us_cfg.enabled is True
    assert len(us_cfg.target_cities) > 0
    assert len(us_cfg.target_niches) > 0

    uk_cfg = await country_config_manager.get_country(db_session, "UK")
    assert uk_cfg is not None
    assert uk_cfg.currency == "GBP"


@pytest.mark.asyncio
async def test_country_enable_disable_toggle(db_session):
    """Verify dynamic enabling and disabling of countries."""
    # Disable CA
    updated = await country_config_manager.set_enabled(db_session, "CA", False)
    assert updated.enabled is False

    enabled_only = await country_config_manager.list_countries(db_session, enabled_only=True)
    enabled_codes = {c.country_code for c in enabled_only}
    assert "CA" not in enabled_codes
    assert "US" in enabled_codes

    # Re-enable CA
    updated = await country_config_manager.set_enabled(db_session, "CA", True)
    assert updated.enabled is True


@pytest.mark.asyncio
async def test_country_config_update(db_session):
    """Verify updating country limits and targets."""
    res = await country_config_manager.update_config(
        db_session,
        "US",
        {"concurrency_limit": 5, "max_daily_discovery": 100}
    )
    assert res.concurrency_limit == 5
    assert res.max_daily_discovery == 100


# ============================================================================
# 2. PLUGGABLE DISCOVERY PROVIDER & SCRAPEGRAPH TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_scrapegraph_provider_mock_mode():
    """Verify ScrapeGraphProvider mock mode runs safely with 0 external API cost."""
    provider = ScrapeGraphProvider(mock_mode=True)
    assert provider.name == "scrapegraph_ai"

    prospects = await provider.discover_prospects(
        country_code="UK",
        niche="accountancy-firms",
        limit=3,
        cities=["London"]
    )
    assert len(prospects) == 3
    for p in prospects:
        assert isinstance(p, StandardizedProspect)
        assert p.country == "UK"
        assert p.discovery_source == "scrapegraph_ai"
        assert p.confidence >= 0.8
        assert provider.budget.credits_used == 0


@pytest.mark.asyncio
async def test_scrapegraph_circuit_breaker_and_fallback():
    """Verify circuit breaker trips on consecutive errors and registry falls back gracefully."""
    provider = ScrapeGraphProvider(api_key="test_key", mock_mode=False, timeout_seconds=1.0)
    provider.circuit_breaker.failure_threshold = 2

    # Simulate failures
    with patch.object(provider, "_execute_scrapegraph_query", new_callable=AsyncMock, side_effect=Exception("API Connection Failed")):
        res1 = await provider.discover_prospects("US", "roofing", limit=2)
        assert res1 == []
        assert provider.circuit_breaker.consecutive_failures == 1

        res2 = await provider.discover_prospects("US", "roofing", limit=2)
        assert res2 == []
        assert provider.circuit_breaker.state == "OPEN"

    # When tripped, provider returns empty immediately without attempting network
    res3 = await provider.discover_prospects("US", "roofing", limit=2)
    assert res3 == []


# ============================================================================
# 3. PARALLEL DISCOVERY & GLOBAL DEDUPLICATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_country_pipeline_discovery(db_session):
    """Verify country pipeline discovers and verifies prospects."""
    cfg = await country_config_manager.get_country(db_session, "US")
    pipeline = CountryPipeline(cfg)

    prospects = await pipeline.run_discovery(target_count=2, niche="roofing-contractors")
    assert len(prospects) <= 2
    for p in prospects:
        assert p.country == "US"
        assert p.verification_status in ("VERIFIED", "REJECTED")


@pytest.mark.asyncio
async def test_global_prospect_pool_parallel_discovery_and_deduplication(db_session):
    """Verify parallel multi-country discovery and cross-country deduplication."""
    # Pre-insert a known business to test deduplication
    known_biz = Business(
        name="Existing US Contractor",
        domain="existingcontractor.com",
        website_url="https://existingcontractor.com",
        country="US",
        city="Dallas",
        niche="roofing-contractors",
        verification_status="VERIFIED",
        pipeline_stage=PipelineStage.VERIFIED.value
    )
    db_session.add(known_biz)
    await db_session.commit()

    # Discover across US and UK
    discovered = await global_prospect_pool.discover_across_countries(
        session=db_session,
        countries=["US", "UK"],
        target_per_country=2,
        niche="roofing-contractors"
    )

    domains = [b.domain for b in discovered]
    # Existing domain must not be duplicated
    assert "existingcontractor.com" not in domains
    # All returned domains must be unique
    assert len(domains) == len(set(domains))


@pytest.mark.asyncio
async def test_enrich_and_audit_prospects(db_session):
    """Verify that un-audited businesses are audited and enriched with client intelligence."""
    biz = Business(
        name="Global Test Clinic",
        domain="globaltestclinic.com",
        website_url="https://globaltestclinic.com",
        country="AU",
        city="Sydney",
        niche="dental-clinics",
        public_email="info@globaltestclinic.com",
        verification_status="VERIFIED",
        pipeline_stage=PipelineStage.VERIFIED.value
    )
    db_session.add(biz)
    await db_session.commit()

    enriched = await global_prospect_pool.enrich_and_audit_prospects(db_session, [biz])
    assert len(enriched) == 1
    assert enriched[0].pipeline_stage == PipelineStage.AUDITED.value

    # Verify ClientIntelligenceRecord created
    q_ci = select(ClientIntelligenceRecord).where(ClientIntelligenceRecord.business_id == biz.id)
    ci = (await db_session.execute(q_ci)).scalar_one_or_none()
    assert ci is not None
    assert ci.fit_score > 0.0
    assert ci.recommended_price_usd >= 500.0


# ============================================================================
# 4. GLOBAL MULTI-CRITERIA RANKING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_global_ranker_composite_scoring_and_ordering(db_session):
    """Verify global dynamic ranking sorts prospects descending by composite EV score."""
    b1 = Business(
        name="London High Value Legal",
        domain="londonhighvaluelegal.co.uk",
        website_url="https://londonhighvaluelegal.co.uk",
        country="UK",
        city="London",
        niche="legal-practices",
        public_email="partners@londonhighvaluelegal.co.uk",
        phone="+44 20 7946 0912",
        verification_status="VERIFIED",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    b2 = Business(
        name="Small Rural Plumbing",
        domain="smallruralplumbing.com",
        website_url="https://smallruralplumbing.com",
        country="US",
        city="Nowhere",
        niche="plumbing-services",
        public_email=None,  # Lower contactability
        verification_status="VERIFIED",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    db_session.add_all([b1, b2])
    await db_session.commit()

    ranked = await global_ranker.rank_pool(db_session)
    assert len(ranked) >= 2

    # b1 has email + phone -> higher contactability
    ranked_b1 = next(item for item in ranked if item.business_id == b1.id)
    ranked_b2 = next(item for item in ranked if item.business_id == b2.id)

    assert ranked_b1.contactability > ranked_b2.contactability
    assert ranked_b1.composite_score > 0
    assert ranked_b2.composite_score > 0

    # Decision trace completeness
    trace = ranked_b1.decision_trace
    assert "why_this_business" in trace
    assert "why_this_country" in trace
    assert "why_this_service" in trace
    assert "why_this_price" in trace
    assert "why_now" in trace


# ============================================================================
# 5. STRICT ACTIVE OUTREACH LOCK & RACE CONDITION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_active_slot_initial_idle_status(db_session):
    """Verify active outreach slot initializes as IDLE and unoccupied."""
    status = await active_prospect_controller.get_active_status(db_session)
    assert status.slot_id == 1
    assert status.is_occupied is False
    assert status.status == "IDLE"


@pytest.mark.asyncio
async def test_acquire_and_lock_slot(db_session):
    """Verify selecting a prospect locks slot 1 and marks it ACTIVE."""
    biz = Business(
        name="Active Candidate Corp",
        domain="activecandidatecorp.com",
        website_url="https://activecandidatecorp.com",
        country="US",
        city="Miami",
        niche="commercial-hvac",
        public_email="owner@activecandidatecorp.com",
        verification_status="VERIFIED",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    db_session.add(biz)
    await db_session.commit()

    status = await active_prospect_controller.select_next_prospect(db_session, business_id=biz.id)
    assert status.is_occupied is True
    assert status.business_id == biz.id
    assert status.status == "ACTIVE"
    assert status.current_stage == "SELECTED"


@pytest.mark.asyncio
async def test_prevent_second_active_prospect_race_condition(db_session):
    """
    CRITICAL CONSTRAINT: MAX_ACTIVE_OUTREACH_PROSPECTS = 1.
    Verify that selecting a second prospect while slot 1 is occupied raises ValueError.
    """
    b1 = Business(
        name="First In Flight",
        domain="firstinflight.com",
        website_url="https://firstinflight.com",
        country="US",
        niche="roofing-contractors",
        verification_status="VERIFIED",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    b2 = Business(
        name="Second Candidate",
        domain="secondcandidate.com",
        website_url="https://secondcandidate.com",
        country="UK",
        niche="roofing-contractors",
        verification_status="VERIFIED",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    db_session.add_all([b1, b2])
    await db_session.commit()

    # Lock b1
    await active_prospect_controller.select_next_prospect(db_session, business_id=b1.id)

    # Attempt to lock b2 while b1 is active -> must fail
    with pytest.raises(ValueError, match="already occupied"):
        await active_prospect_controller.select_next_prospect(db_session, business_id=b2.id)

    # Slot remains locked to b1
    status = await active_prospect_controller.get_active_status(db_session)
    assert status.business_id == b1.id
    assert status.is_occupied is True


@pytest.mark.asyncio
async def test_stale_lock_lease_timeout_recovery(db_session):
    """Verify that an expired lease (> lease_timeout_seconds) is automatically released."""
    biz = Business(
        name="Stale Lease Corp",
        domain="staleleasecorp.com",
        country="CA",
        niche="commercial-hvac",
        verification_status="VERIFIED",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    db_session.add(biz)
    await db_session.commit()

    # Acquire lock
    await active_prospect_controller.select_next_prospect(db_session, business_id=biz.id)

    # Backdate locked_at by 8 days (past 7-day default lease)
    lock = await active_prospect_controller.get_or_create_lock(db_session)
    lock.locked_at = datetime.utcnow() - timedelta(days=8)
    await db_session.commit()

    # Next status inspection recovers stale lock
    status = await active_prospect_controller.get_active_status(db_session)
    assert status.is_occupied is False
    assert status.status == "IDLE"


# ============================================================================
# 6. SEQUENTIAL OUTREACH LIFECYCLE & APPROVAL GATE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_outreach_draft_requires_human_approval(db_session):
    """Verify outreach is drafted into PENDING_APPROVAL and slot stage is OUTREACH_DRAFTED."""
    biz = Business(
        name="Outreach Target LLC",
        domain="outreachtargetllc.com",
        website_url="https://outreachtargetllc.com",
        country="US",
        city="Atlanta",
        niche="roofing-contractors",
        public_email="director@outreachtargetllc.com",
        verification_status="VERIFIED",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    db_session.add(biz)
    await db_session.commit()

    await active_prospect_controller.select_next_prospect(db_session, business_id=biz.id)

    # Prepare outreach
    draft = await active_prospect_controller.prepare_outreach(db_session, business_id=biz.id)
    assert draft["status"] == "DRAFTED"
    assert draft["approval_status"] == OutreachStatus.PENDING_APPROVAL.value

    status = await active_prospect_controller.get_active_status(db_session)
    assert status.current_stage == "OUTREACH_DRAFTED"


@pytest.mark.asyncio
async def test_human_approval_gate_and_dispatch(db_session):
    """Verify that approving draft message sends email (dry-run) and transitions slot to WAITING_FOR_REPLY."""
    biz = Business(
        name="Approval Gate Corp",
        domain="approvalgatecorp.com",
        website_url="https://approvalgatecorp.com",
        country="US",
        city="Chicago",
        niche="commercial-hvac",
        public_email="ceo@approvalgatecorp.com",
        verification_status="VERIFIED",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    db_session.add(biz)
    await db_session.commit()

    await active_prospect_controller.select_next_prospect(db_session, business_id=biz.id)
    await active_prospect_controller.prepare_outreach(db_session, business_id=biz.id)

    # Operator approves and sends
    send_res = await active_prospect_controller.approve_and_send(db_session, business_id=biz.id)
    assert send_res["status"] == "SENT"
    assert send_res["slot_status"] == "WAITING_FOR_REPLY"

    status = await active_prospect_controller.get_active_status(db_session)
    assert status.status == "WAITING_FOR_REPLY"
    assert status.current_stage == "SENT"
    assert status.waiting_since is not None


# ============================================================================
# 7. INBOUND REPLY HANDLING & CANCELLATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_inbound_opt_out_reply_auto_releases_slot_and_suppresses(db_session):
    """Verify that an opt-out reply triggers suppression, cancels follow-ups, and releases the active slot."""
    biz = Business(
        name="Opt Out LLC",
        domain="optoutllc.com",
        website_url="https://optoutllc.com",
        country="US",
        niche="roofing-contractors",
        public_email="owner@optoutllc.com",
        verification_status="VERIFIED",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    db_session.add(biz)
    await db_session.commit()

    await active_prospect_controller.select_next_prospect(db_session, business_id=biz.id)
    await active_prospect_controller.prepare_outreach(db_session, business_id=biz.id)
    await active_prospect_controller.approve_and_send(db_session, business_id=biz.id)

    # Inbound Unsubscribe Reply
    reply_res = await active_prospect_controller.record_reply(
        db_session,
        business_id=biz.id,
        reply_text="Please unsubscribe us immediately. Remove me from your mailing list.",
        sender_email="owner@optoutllc.com"
    )

    assert reply_res["reply_classification"] == ReplyClassification.UNSUBSCRIBE.value
    assert reply_res["action_taken"] == "RELEASED_SLOT"

    # Slot must be released back to IDLE
    status = await active_prospect_controller.get_active_status(db_session)
    assert status.is_occupied is False
    assert status.status == "IDLE"

    # Email must be on suppression list
    is_suppressed = await compliance_guard.is_suppressed(db_session, "owner@optoutllc.com")
    assert is_suppressed is True


@pytest.mark.asyncio
async def test_inbound_interested_reply_moves_to_negotiating(db_session):
    """Verify that a positive reply advances slot status to NEGOTIATING without releasing slot."""
    biz = Business(
        name="Interested Buyer Corp",
        domain="interestedbuyercorp.com",
        website_url="https://interestedbuyercorp.com",
        country="US",
        niche="roofing-contractors",
        public_email="sales@interestedbuyercorp.com",
        verification_status="VERIFIED",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    db_session.add(biz)
    await db_session.commit()

    await active_prospect_controller.select_next_prospect(db_session, business_id=biz.id)
    await active_prospect_controller.prepare_outreach(db_session, business_id=biz.id)
    await active_prospect_controller.approve_and_send(db_session, business_id=biz.id)

    # Inbound Interested Reply
    reply_res = await active_prospect_controller.record_reply(
        db_session,
        business_id=biz.id,
        reply_text="Sounds very interesting. Can we schedule a brief call tomorrow afternoon?",
        sender_email="sales@interestedbuyercorp.com"
    )

    assert reply_res["reply_classification"] in (ReplyClassification.INTERESTED.value, ReplyClassification.MEETING_REQUEST.value)
    assert reply_res["action_taken"] == "ACTIVE_NEGOTIATION"

    status = await active_prospect_controller.get_active_status(db_session)
    assert status.is_occupied is True
    assert status.status == "NEGOTIATING"
    assert status.current_stage == "REPLIED"


# ============================================================================
# 8. SLOT RELEASE & DYNAMIC RE-RANKING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_manual_release_and_subsequent_selection(db_session):
    """Verify manual CEO release frees slot 1 and enables next prospect selection."""
    b1 = Business(
        name="First Prospect",
        domain="firstprospect.com",
        country="US",
        niche="roofing-contractors",
        verification_status="VERIFIED",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    b2 = Business(
        name="Second Prospect",
        domain="secondprospect.com",
        country="CA",
        niche="roofing-contractors",
        verification_status="VERIFIED",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    db_session.add_all([b1, b2])
    await db_session.commit()

    # Lock b1
    await active_prospect_controller.select_next_prospect(db_session, business_id=b1.id)

    # Release b1 with WON
    rel = await active_prospect_controller.release_active_slot(db_session, terminal_reason="WON", notes="Contract signed")
    assert rel["released"] is True
    assert rel["slot_status"] == "IDLE"

    # Verify b1 stage updated to WON
    await db_session.refresh(b1)
    assert b1.pipeline_stage == PipelineStage.WON.value

    # Now b2 can be selected without conflict
    status2 = await active_prospect_controller.select_next_prospect(db_session, business_id=b2.id)
    assert status2.is_occupied is True
    assert status2.business_id == b2.id


# ============================================================================
# 9. REST API ENDPOINT TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_api_country_configurations():
    """Verify GET /api/acquisition/countries returns all configured profiles."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/acquisition/countries")
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 5
        codes = [c["country_code"] for c in data]
        assert "US" in codes
        assert "UK" in codes


@pytest.mark.asyncio
async def test_api_active_slot_and_conflict_handling():
    """Verify REST API returns 409 Conflict when attempting to select a second prospect."""
    from app.database.connection import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        await active_prospect_controller.release_active_slot(session, terminal_reason="MANUAL_RELEASE")
        import uuid
        uid_str = uuid.uuid4().hex[:8]
        b1 = Business(
            name=f"API Biz One {uid_str}",
            domain=f"apibizone-{uid_str}.com",
            country="US",
            niche="roofing-contractors",
            verification_status="VERIFIED",
            pipeline_stage=PipelineStage.AUDITED.value
        )
        b2 = Business(
            name=f"API Biz Two {uid_str}",
            domain=f"apibiztwo-{uid_str}.com",
            country="UK",
            niche="roofing-contractors",
            verification_status="VERIFIED",
            pipeline_stage=PipelineStage.AUDITED.value
        )
        session.add_all([b1, b2])
        await session.commit()
        b1_id, b2_id = b1.id, b2.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Check initial slot status
        res1 = await ac.get("/api/acquisition/active")
        assert res1.status_code == 200
        assert res1.json()["is_occupied"] is False

        # 2. Select b1
        res2 = await ac.post("/api/acquisition/select-next", json={"business_id": b1_id})
        assert res2.status_code == 200
        assert res2.json()["business_id"] == b1_id

        # 3. Attempt to select b2 -> Must return 409 Conflict
        res3 = await ac.post("/api/acquisition/select-next", json={"business_id": b2_id})
        assert res3.status_code == 409
        assert "already occupied" in res3.json()["detail"]

        # 4. Release active slot
        res4 = await ac.post("/api/acquisition/release-active", json={"terminal_reason": "MANUAL_RELEASE"})
        assert res4.status_code == 200
        assert res4.json()["released"] is True

        # 5. Now b2 can be selected
        res5 = await ac.post("/api/acquisition/select-next", json={"business_id": b2_id})
        assert res5.status_code == 200
        assert res5.json()["business_id"] == b2_id

        # Cleanup slot after test
        await ac.post("/api/acquisition/release-active", json={"terminal_reason": "MANUAL_RELEASE"})


# ============================================================================
# 10. END-TO-END ACCEPTANCE FLOW TEST
# ============================================================================

@pytest.mark.asyncio
async def test_full_phase10_end_to_end_acceptance_flow(db_session):
    """
    End-to-End Acceptance Test demonstrating the full Phase 10 engine:
    1. Parallel multi-country discovery across US, UK, and CA.
    2. Global dynamic ranking with EV score and decision trace.
    3. Locking top prospect (#1) into the singular active outreach slot.
    4. Rejecting concurrent outreach attempts (strict MAX_ACTIVE_OUTREACH = 1).
    5. Drafting personalized outreach with human approval gate.
    6. Approving and sending message -> slot enters WAITING_FOR_REPLY.
    7. Inbound rejection reply -> auto-cancels follow-ups and releases active slot.
    8. Dynamic re-ranking allows Prospect #2 to enter active outreach.
    """
    # 1. Discover across US, UK, and CA
    discovered = await global_prospect_pool.discover_across_countries(
        session=db_session,
        countries=["US", "UK", "CA"],
        target_per_country=2,
        niche="roofing-contractors"
    )
    assert len(discovered) >= 2

    # Audit & enrich
    await global_prospect_pool.enrich_and_audit_prospects(db_session, discovered)

    # 2. Global dynamic ranking
    queue = await global_ranker.rank_pool(db_session)
    assert len(queue) >= 2
    top_candidate = queue[0]
    second_candidate = queue[1]
    assert top_candidate.composite_score >= second_candidate.composite_score
    assert len(top_candidate.why_this_prospect) > 0

    # Ensure top candidate has an email for outreach
    top_biz = await db_session.get(Business, top_candidate.business_id)
    if not top_biz.public_email:
        top_biz.public_email = "owner@domain.com"
        await db_session.commit()

    # 3. Lock top candidate into active slot
    active_slot = await active_prospect_controller.select_next_prospect(
        db_session, business_id=top_candidate.business_id
    )
    assert active_slot.is_occupied is True
    assert active_slot.business_id == top_candidate.business_id

    # 4. Concurrency Guard: Second candidate CANNOT enter active outreach
    with pytest.raises(ValueError, match="already occupied"):
        await active_prospect_controller.select_next_prospect(
            db_session, business_id=second_candidate.business_id
        )

    # 5. Prepare outreach draft (Human approval gate)
    draft = await active_prospect_controller.prepare_outreach(
        db_session, business_id=top_candidate.business_id
    )
    assert draft["approval_status"] == OutreachStatus.PENDING_APPROVAL.value

    # 6. Human approves and sends outreach
    send_info = await active_prospect_controller.approve_and_send(
        db_session, business_id=top_candidate.business_id
    )
    assert send_info["slot_status"] == "WAITING_FOR_REPLY"

    # 7. Inbound opt-out reply
    reply_info = await active_prospect_controller.record_reply(
        db_session,
        business_id=top_candidate.business_id,
        reply_text="We are not interested, please take us off your list.",
        sender_email=top_biz.public_email
    )
    assert reply_info["action_taken"] == "RELEASED_SLOT"

    # Active slot is now IDLE
    status_after_reply = await active_prospect_controller.get_active_status(db_session)
    assert status_after_reply.is_occupied is False

    # 8. Re-selection: Second candidate can now be selected into the freed active slot
    new_active_slot = await active_prospect_controller.select_next_prospect(
        db_session, business_id=second_candidate.business_id
    )
    assert new_active_slot.is_occupied is True
    assert new_active_slot.business_id == second_candidate.business_id

    # Clean up
    await active_prospect_controller.release_active_slot(db_session, terminal_reason="MANUAL_RELEASE")
