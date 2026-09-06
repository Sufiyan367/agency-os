import pytest
from uuid import uuid4
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import (
    Business, Contact, ProspectEvidence, DiscoveryRun,
    PipelineStage, VerificationStatus, ClientIntelligenceRecord, ActiveOutreachLock
)
from app.acquisition.evidence_gate import prospect_evidence_gate, GateEvaluationResult
from app.acquisition.prospect_discovery import real_prospect_discovery_engine
from app.acquisition.pool import global_prospect_pool
from app.acquisition.ranking import global_ranker
from app.acquisition.controller import active_prospect_controller


@pytest.mark.asyncio
async def test_evidence_gate_zero_evidence_strictly_blocks():
    """Invariant: If VERIFIED_EVIDENCE_COUNT == 0, gate MUST fail."""
    result = prospect_evidence_gate.evaluate_evidence([])
    assert result.is_passed is False
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.evidence_count == 0
    assert result.can_outreach is False
    assert result.can_auto_approve is False
    assert result.details.get("failure_code") == "ZERO_EVIDENCE"


@pytest.mark.asyncio
async def test_evidence_gate_single_source_fails():
    """Invariant: Minimum 2 independent sources required."""
    single_ev = ProspectEvidence(
        evidence_id="ev_single_001",
        business_id=1,
        claim="Operates commercial service in Austin.",
        source_url="https://austinroofingpro.com",
        source_domain="austinroofingpro.com",
        source_type="official_website",
        source_tier=3,
        publisher="Austin Roofing Pro",
        raw_excerpt="Active website found at domain.",
        evidence_category="operational",
        confidence_score=0.90,
        source_quality_score=0.85,
        freshness_score=1.0,
        is_verified=True
    )
    result = prospect_evidence_gate.evaluate_evidence([single_ev])
    assert result.is_passed is False
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.evidence_count == 1
    assert result.distinct_sources_count == 1
    assert result.can_outreach is False


@pytest.mark.asyncio
async def test_evidence_gate_two_verified_sources_passes():
    """Invariant: At least 2 independent verified sources with score >= 0.60 passes gate."""
    ev1 = ProspectEvidence(
        evidence_id="ev_test_001",
        business_id=1,
        claim="Commercial entity operations website.",
        source_url="https://austinroofingpro.com",
        source_domain="austinroofingpro.com",
        source_type="official_website",
        source_tier=3,
        publisher="Austin Roofing Pro",
        raw_excerpt="Verified live operations at domain.",
        evidence_category="operational",
        confidence_score=0.88,
        source_quality_score=0.80,
        freshness_score=1.0,
        is_verified=True
    )
    ev2 = ProspectEvidence(
        evidence_id="ev_test_002",
        business_id=1,
        claim="Official commercial registry entry.",
        source_url="https://www.openstreetmap.org/node/12345",
        source_domain="openstreetmap.org",
        source_type="registry",
        source_tier=2,
        publisher="OpenStreetMap Commercial Index",
        raw_excerpt="Entity indexed as registered business.",
        evidence_category="identity",
        confidence_score=0.92,
        source_quality_score=0.88,
        freshness_score=1.0,
        is_verified=True
    )
    result = prospect_evidence_gate.evaluate_evidence([ev1, ev2])
    assert result.is_passed is True
    assert result.status == "VERIFIED"
    assert result.evidence_count == 2
    assert result.distinct_sources_count == 2
    assert result.effective_evidence_score >= 0.60
    assert result.can_outreach is True
    assert result.can_auto_approve is True


@pytest.mark.asyncio
async def test_evidence_gate_low_score_fails():
    """Invariant: Even with 2 items, low effective score (<0.60) fails gate."""
    ev1 = ProspectEvidence(
        evidence_id="ev_low_001",
        business_id=1,
        claim="Uncertain claim 1",
        source_url="https://example.com/1",
        source_domain="example.com",
        source_type="web",
        source_tier=3,
        publisher="Unknown Blog",
        raw_excerpt="Vague mention.",
        evidence_category="operational",
        confidence_score=0.20,
        source_quality_score=0.20,
        freshness_score=0.30,
        is_verified=True
    )
    ev2 = ProspectEvidence(
        evidence_id="ev_low_002",
        business_id=1,
        claim="Uncertain claim 2",
        source_url="https://another-site.com/2",
        source_domain="another-site.com",
        source_type="directory",
        source_tier=3,
        publisher="Random Dir",
        raw_excerpt="Vague listing.",
        evidence_category="identity",
        confidence_score=0.25,
        source_quality_score=0.20,
        freshness_score=0.30,
        is_verified=True
    )
    result = prospect_evidence_gate.evaluate_evidence([ev1, ev2])
    assert result.is_passed is False
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.effective_evidence_score < 0.60
    assert result.details.get("failure_code") == "LOW_EVIDENCE_SCORE"


@pytest.mark.asyncio
async def test_evidence_gate_database_synchronization(db_session: AsyncSession):
    """Test evaluate_and_apply correctly updates Business model state in DB."""
    uid = uuid4().hex[:8]
    biz = Business(
        name=f"Test Sync Roofing {uid}",
        domain=f"testsyncroofing_{uid}.com",
        website_url=f"https://testsyncroofing_{uid}.com",
        country="US",
        city="Houston",
        niche="roofing-contractors",
        verification_status="VERIFIED",
        pipeline_stage=PipelineStage.DISCOVERED.value
    )
    db_session.add(biz)
    await db_session.commit()

    # 1. Evaluate with 0 evidence in DB -> must be rolled back to INSUFFICIENT_EVIDENCE
    gate_res = await prospect_evidence_gate.evaluate_and_apply(db_session, biz)
    assert gate_res.is_passed is False
    assert biz.verification_status == "INSUFFICIENT_EVIDENCE"
    assert biz.research_status == "RESEARCH_REQUIRED"
    assert biz.evidence_count == 0

    # 2. Add 2 verified evidence items
    ev1 = ProspectEvidence(
        evidence_id=f"ev_sync_1_{uid}",
        business_id=biz.id,
        claim="Domain operational.",
        source_url=biz.website_url,
        source_domain=biz.domain,
        source_type="official_website",
        source_tier=3,
        raw_excerpt="Website is reachable and serving services.",
        confidence_score=0.90,
        source_quality_score=0.85,
        freshness_score=1.0,
        is_verified=True
    )
    ev2 = ProspectEvidence(
        evidence_id=f"ev_sync_2_{uid}",
        business_id=biz.id,
        claim="Registry record confirmed.",
        source_url=f"https://www.openstreetmap.org/search?query={biz.domain}",
        source_domain="openstreetmap.org",
        source_type="registry",
        source_tier=2,
        raw_excerpt="Commercial registry coordinates confirmed.",
        confidence_score=0.92,
        source_quality_score=0.88,
        freshness_score=1.0,
        is_verified=True
    )
    db_session.add_all([ev1, ev2])
    await db_session.commit()

    # 3. Re-evaluate -> must pass
    gate_res2 = await prospect_evidence_gate.evaluate_and_apply(db_session, biz)
    assert gate_res2.is_passed is True
    assert biz.verification_status == "VERIFIED"
    assert biz.research_status == "VERIFIED"
    assert biz.evidence_count == 2
    assert biz.effective_evidence_score >= 0.60


@pytest.mark.asyncio
async def test_pool_get_uncontacted_candidates_filters_zero_evidence(db_session: AsyncSession):
    """Test that prospects failing evidence gate are never returned for ranking."""
    uid = uuid4().hex[:8]
    # Prospect A: Has 0 evidence and is marked INSUFFICIENT_EVIDENCE
    biz_insufficient = Business(
        name=f"Zero Ev Biz {uid}",
        domain=f"zeroev_{uid}.com",
        website_url=f"https://zeroev_{uid}.com",
        country="US",
        niche="roofing-contractors",
        verification_status="INSUFFICIENT_EVIDENCE",
        research_status="RESEARCH_REQUIRED",
        evidence_count=0,
        pipeline_stage=PipelineStage.DISCOVERED.value
    )
    # Prospect B: Has 2 evidence items and is VERIFIED
    biz_verified = Business(
        name=f"Verified Ev Biz {uid}",
        domain=f"verifiedev_{uid}.com",
        website_url=f"https://verifiedev_{uid}.com",
        country="US",
        niche="roofing-contractors",
        verification_status="VERIFIED",
        research_status="VERIFIED",
        evidence_count=2,
        effective_evidence_score=0.82,
        pipeline_stage=PipelineStage.VERIFIED.value
    )
    db_session.add_all([biz_insufficient, biz_verified])
    await db_session.commit()

    candidates = await global_prospect_pool.get_uncontacted_candidates(db_session, limit=50)
    candidate_ids = [c.id for c in candidates]

    assert biz_verified.id in candidate_ids
    assert biz_insufficient.id not in candidate_ids


@pytest.mark.asyncio
async def test_active_controller_rejects_insufficient_evidence_prospect(db_session: AsyncSession):
    """Invariant: ActiveOutreachLock cannot be acquired by a zero/insufficient evidence prospect."""
    uid = uuid4().hex[:8]
    bad_biz = Business(
        name=f"Unverified Bad Biz {uid}",
        domain=f"badbiz_{uid}.com",
        website_url=f"https://badbiz_{uid}.com",
        country="US",
        niche="roofing-contractors",
        verification_status="INSUFFICIENT_EVIDENCE",
        research_status="RESEARCH_REQUIRED",
        evidence_count=0,
        pipeline_stage=PipelineStage.DISCOVERED.value
    )
    db_session.add(bad_biz)
    await db_session.commit()

    # Attempt to select for active outreach slot
    with pytest.raises(ValueError, match="failed hard evidence gate"):
        await active_prospect_controller.select_next_prospect(db_session, business_id=bad_biz.id)


@pytest.mark.asyncio
async def test_pricing_gate_under_500_blocked(db_session: AsyncSession):
    """Invariant: Pricing under $500 is blocked from commercial outreach."""
    uid = uuid4().hex[:8]
    cheap_biz = Business(
        name=f"Low Price Biz {uid}",
        domain=f"lowprice_{uid}.com",
        website_url=f"https://lowprice_{uid}.com",
        country="US",
        niche="roofing-contractors",
        verification_status="VERIFIED",
        research_status="VERIFIED",
        evidence_count=2,
        effective_evidence_score=0.85,
        pipeline_stage=PipelineStage.AUDITED.value
    )
    db_session.add(cheap_biz)
    await db_session.flush()

    # Intel with price $350 (below $500 threshold)
    intel = ClientIntelligenceRecord(
        business_id=cheap_biz.id,
        recommended_price_usd=350.0,
        top_service_name="Basic Audit",
        fit_score=0.80,
        p_win=0.60
    )
    db_session.add(intel)
    await db_session.commit()

    # Release any existing active slot to isolate test
    await active_prospect_controller.release_active_slot(db_session, terminal_reason="MANUAL_RELEASE")

    with pytest.raises(ValueError, match="below the minimum threshold"):
        await active_prospect_controller.select_next_prospect(db_session, business_id=cheap_biz.id)


@pytest.mark.asyncio
async def test_prospect_score_calculated_and_persisted(db_session: AsyncSession):
    """Test GlobalRanker computes transparent prospect_score and persists to Business model."""
    uid = uuid4().hex[:8]
    biz = Business(
        name=f"Scored Biz {uid}",
        domain=f"scored_{uid}.com",
        website_url=f"https://scored_{uid}.com",
        country="US",
        niche="roofing-contractors",
        public_email=f"contact@scored_{uid}.com",
        phone="+1 512-555-0199",
        verification_status="VERIFIED",
        research_status="VERIFIED",
        evidence_count=3,
        effective_evidence_score=0.88,
        pipeline_stage=PipelineStage.AUDITED.value
    )
    db_session.add(biz)
    await db_session.commit()

    ranked = await global_ranker.rank_pool(db_session)
    matching = [r for r in ranked if r.business_id == biz.id]
    assert len(matching) == 1
    top_item = matching[0]

    # Verify decision trace details
    signals = top_item.decision_trace.get("signals", {})
    assert "prospect_score" in signals
    assert "evidence_score" in signals
    assert "evidence_count" in signals
    assert signals["evidence_count"] == 3
    assert signals["evidence_score"] == 0.88

    # Verify database persistence of prospect_score
    refreshed_biz = await db_session.get(Business, biz.id)
    assert refreshed_biz.prospect_score > 0.0


@pytest.mark.asyncio
async def test_real_prospect_discovery_engine(db_session: AsyncSession):
    """Test end-to-end multi-city prospect acquisition and evidence harvesting."""
    res = await real_prospect_discovery_engine.discover_prospects_for_market(
        session=db_session,
        country_code="US",
        niche_slug="roofing-contractors",
        target_count=2,
        cities=["Austin", "Dallas"]
    )
    assert res["status"] == "COMPLETED"
    assert res["country_code"] == "US"
    assert res["niche_slug"] == "roofing-contractors"
    assert res["prospects_discovered"] >= 1
    assert res["evidence_items_extracted"] >= 2
    assert "run_id" in res

    # Verify DiscoveryRun telemetry persisted
    run_stmt = select(DiscoveryRun).where(DiscoveryRun.run_id == res["run_id"])
    run_obj = (await db_session.execute(run_stmt)).scalar_one_or_none()
    assert run_obj is not None
    assert run_obj.status == "COMPLETED"
    assert run_obj.prospects_discovered >= 1


@pytest.mark.asyncio
async def test_prospect_api_endpoints():
    """Test Phase 12 REST API routes."""
    from httpx import AsyncClient, ASGITransport
    from app.api.app import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Pipeline status
        res = await client.get("/api/prospects/pipeline-status")
        assert res.status_code == 200
        data = res.json()
        assert "total_prospects" in data
        assert "total_verified_evidence_items" in data
        assert "evidence_gate_passed" in data
        assert "active_slot" in data

        # 2. Discovery runs telemetry
        res_runs = await client.get("/api/prospects/runs")
        assert res_runs.status_code == 200
        assert isinstance(res_runs.json(), list)

        # 3. Top candidate
        res_top = await client.get("/api/prospects/top-candidate")
        assert res_top.status_code == 200

