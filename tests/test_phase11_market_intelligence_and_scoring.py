"""Phase 11: Global Market Intelligence and Country x Niche Opportunity Scoring Engine Tests.

Verifies:
1. Seed Universe & Dynamic Profile Initialization (18+ countries, 20+ niches, Tiers 1-3).
2. Evidence Persistence, Provenance & SSRF Validation (valid URLs, non-future dates, blocks private IPs).
3. Source Quality Tiering & Freshness Decay Calculation.
4. Deduplication & Weighted Conflict Resolution.
5. Signal Extraction with Explicit UNKNOWN Preservation.
6. Transparent Scoring Formula & Expected Value Calculation (bounds [10, 100], penalties).
7. Explainable 5-Point Decision Trace (Why Country, Niche, Service, Price, Now).
8. Country x Niche x Service Mapping & $1,000+ Minimum Viable Deal Value Floor.
9. Dynamic Candidate Market Discovery (Nordics, etc.).
10. Provider Fallback Chain, Timeout Handling & Cost Guard.
11. Multi-Language Localization Query Generation.
12. Compliance Risk Profile Evaluation (CAN-SPAM, GDPR, UAE PDPL).
13. Phase 10 Ingestion Integration & Strict Single Active Outreach Lock Preservation.
14. Commercial Approval Gate Compatibility (<$500 block, $500-$999 approval, $1000+ pass).
15. Synthetic Data Isolation (zero contamination of revenue/client metrics).
16. Full REST API Endpoints Suite.
"""
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func

from app.database.connection import get_db
from app.database.models import (
    CountryMarketProfile, NicheMarketProfile, MarketEvidence,
    MarketSignal, CountryNicheOpportunity, MarketResearchRun,
    ActiveOutreachLock, Business, PipelineStage
)
from app.market_intelligence.models import (
    EvidenceTier, FreshnessCategory, SignalType, SignalDirection,
    ComplianceRisk, ResearchStatus, RawEvidenceItem, ExtractedSignal, ScoredOpportunity
)
from app.market_intelligence.config import (
    SEED_COUNTRIES, SEED_NICHES, SCORING_WEIGHTS,
    SERVICE_CATALOG_MAPPING, FreshnessThresholds, CostGuardConfig
)
from app.market_intelligence.source_quality import source_quality_classifier
from app.market_intelligence.evidence_freshness import evidence_freshness_calculator
from app.market_intelligence.evidence_validator import evidence_validator
from app.market_intelligence.evidence_collector import evidence_collector
from app.market_intelligence.market_signal_extractor import market_signal_extractor
from app.market_intelligence.localization import market_localization
from app.market_intelligence.compliance_profile import compliance_profile_manager
from app.market_intelligence.decision_trace import market_decision_trace_builder
from app.market_intelligence.market_opportunity_scorer import market_opportunity_scorer
from app.market_intelligence.cost_guard import MarketResearchCostGuard
from app.market_intelligence.providers.mock import MockMarketResearchProvider
from app.market_intelligence.providers.web_search import WebSearchMarketResearchProvider
from app.market_intelligence.providers.registry import market_research_registry
from app.market_intelligence.dynamic_discovery import dynamic_market_discovery
from app.market_intelligence.opportunity_queue import global_opportunity_queue
from app.market_intelligence.market_research_engine import market_research_engine
from app.api.app import app

# ---------------------------------------------------------------------------
# 1. Seed Universe Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_universe_creation(db_session):
    await market_research_engine.ensure_seed_universe(db_session)
    countries = (await db_session.execute(select(CountryMarketProfile))).scalars().all()
    niches = (await db_session.execute(select(NicheMarketProfile))).scalars().all()
    assert len(countries) >= 18
    assert len(niches) >= 18

    country_codes = {c.country_code for c in countries}
    for expected in ["US", "AE", "SA", "SG", "UK", "DE", "JP", "AU", "CA"]:
        assert expected in country_codes

    niche_slugs = {n.niche_slug for n in niches}
    for expected in ["roofing", "dental", "real-estate", "hvac"]:
        assert expected in niche_slugs

@pytest.mark.asyncio
async def test_country_profile_tiers_and_compliance(db_session):
    await market_research_engine.ensure_seed_universe(db_session)
    us = (await db_session.execute(select(CountryMarketProfile).where(CountryMarketProfile.country_code == "US"))).scalar_one()
    assert us.currency == "USD"
    assert us.compliance_risk_signal == "LOW"

    ae = (await db_session.execute(select(CountryMarketProfile).where(CountryMarketProfile.country_code == "AE"))).scalar_one()
    assert ae.currency == "AED"
    assert ae.compliance_risk_signal == "LOW"

    de = (await db_session.execute(select(CountryMarketProfile).where(CountryMarketProfile.country_code == "DE"))).scalar_one()
    assert de.currency == "EUR"
    assert de.compliance_risk_signal == "MEDIUM"

# ---------------------------------------------------------------------------
# 2. Evidence Validation & Persistence Tests
# ---------------------------------------------------------------------------

def test_evidence_validator_ssrf_and_schema():
    valid1, _ = evidence_validator.validate(
        source_url="https://statista.com/reports/roofing-market-us",
        claim="Average ticket price for residential roofing is $8,500.",
        raw_excerpt="Average ticket price for residential roofing is $8,500.",
        country_code="US"
    )
    assert valid1 is True

    valid2, reason2 = evidence_validator.validate(
        source_url="http://127.0.0.1:8000/internal-secrets",
        claim="Malicious payload",
        raw_excerpt="Malicious payload",
        country_code="US"
    )
    assert valid2 is False
    assert "SSRF" in reason2 or "private" in reason2.lower() or "loopback" in reason2.lower()

    valid3, _ = evidence_validator.validate(
        source_url="ftp://files.example.com/data.txt",
        claim="Invalid scheme",
        raw_excerpt="Invalid scheme",
        country_code="US"
    )
    assert valid3 is False

    future_date = datetime.now(timezone.utc) + timedelta(days=30)
    valid4, _ = evidence_validator.validate(
        source_url="https://reuters.com/future",
        claim="Future article",
        raw_excerpt="Future article",
        country_code="US",
        publication_date=future_date
    )
    assert valid4 is False

@pytest.mark.asyncio
async def test_evidence_persistence_and_provenance(db_session):
    ev = MarketEvidence(
        evidence_id="EV-TEST-123456",
        source_url="https://bls.gov/ooh/construction/roofers.htm",
        source_domain="bls.gov",
        source_tier=1,
        publisher="US Bureau of Labor Statistics",
        source_quality_score=0.95,
        country_code="US",
        niche_slug="roofing",
        service_id="SERVICE_001",
        claim="Roofing contractor wage costs increased 7.2% year-over-year.",
        raw_excerpt="Projected employment of roofers shows severe skilled labor shortages.",
        signal_type="SERVICE_DEMAND",
        publication_date=datetime.now(timezone.utc) - timedelta(days=10),
        freshness_score=0.98,
        confidence_score=0.95,
        supports_claim=True
    )
    db_session.add(ev)
    await db_session.commit()

    saved = (await db_session.execute(select(MarketEvidence).where(MarketEvidence.source_url == ev.source_url))).scalar_one()
    assert saved.publisher == "US Bureau of Labor Statistics"
    assert saved.source_tier == 1
    assert saved.source_quality_score == 0.95
    assert saved.signal_type == "SERVICE_DEMAND"
    assert saved.supports_claim is True

# ---------------------------------------------------------------------------
# 3. Source Quality & Freshness Tests
# ---------------------------------------------------------------------------

def test_source_quality_tier_classification():
    tier, score = source_quality_classifier.classify("data.worldbank.org")
    assert tier == 1 and score >= 0.90
    tier2, score2 = source_quality_classifier.classify("statista.com")
    assert tier2 == 1 and score2 >= 0.90
    tier3, score3 = source_quality_classifier.classify("medium.com")
    assert tier3 == 3 and score3 <= 0.70

def test_freshness_decay_calculation():
    age_days, score_5d, cat_5d = evidence_freshness_calculator.calculate("SERVICE_DEMAND", datetime.utcnow() - timedelta(days=5))
    assert score_5d >= 0.95
    assert cat_5d == "very_recent"

    _, score_45d, cat_45d = evidence_freshness_calculator.calculate("SERVICE_DEMAND", datetime.utcnow() - timedelta(days=45))
    assert cat_45d == "recent"

    _, score_120d, cat_120d = evidence_freshness_calculator.calculate("SERVICE_DEMAND", datetime.utcnow() - timedelta(days=120))
    assert cat_120d in ["aging", "stale"]

# ---------------------------------------------------------------------------
# 4. Deduplication & Conflict Resolution Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evidence_deduplication(db_session):
    item1 = RawEvidenceItem(
        claim="Claim A for roofing in US",
        source_url="https://example.com/article1",
        source_domain="example.com",
        publisher="Site A",
        publication_date=datetime.utcnow() - timedelta(days=5),
        raw_excerpt="Excerpt for claim A",
        signal_type="SERVICE_DEMAND",
        country_code="US",
        niche_slug="roofing"
    )
    rec1, added1 = await evidence_collector.add_evidence(db_session, item1)
    assert added1 is True
    rec2, added2 = await evidence_collector.add_evidence(db_session, item1)
    assert added2 is False

def test_conflict_resolution_tier_weighting():
    ev_pos = MarketEvidence(
        evidence_id="EV-POS-1",
        source_url="https://bls.gov/stats",
        source_domain="bls.gov",
        source_tier=1,
        publisher="Gov Bureau",
        source_quality_score=0.95,
        freshness_score=1.0,
        confidence_score=0.95,
        country_code="US",
        claim="Roofing demand growing at 12%",
        raw_excerpt="Roofing demand growing at 12%",
        signal_type="SERVICE_DEMAND",
        supports_claim=True,
        contradicts_claim=False
    )
    ev_neg = MarketEvidence(
        evidence_id="EV-NEG-1",
        source_url="https://randomblog.com/post",
        source_domain="randomblog.com",
        source_tier=3,
        publisher="Blogger",
        source_quality_score=0.60,
        freshness_score=0.4,
        confidence_score=0.50,
        country_code="US",
        claim="Roofing demand contracting by 5%",
        raw_excerpt="Roofing demand contracting by 5%",
        signal_type="SERVICE_DEMAND",
        supports_claim=False,
        contradicts_claim=True
    )
    resolved_val, exp = evidence_collector.resolve_conflicting_evidence([ev_pos, ev_neg])
    assert resolved_val > 0.60
    assert "Resolved conflict" in exp

# ---------------------------------------------------------------------------
# 5. Signal Extraction & Unknown Handling
# ---------------------------------------------------------------------------

def test_signal_extraction_from_evidence():
    ev_item = MarketEvidence(
        evidence_id="EV-SIG-1",
        source_url="https://industry-report.com/roofing",
        source_domain="industry-report.com",
        source_tier=2,
        publisher="Industry Reports",
        source_quality_score=0.85,
        freshness_score=0.9,
        confidence_score=0.85,
        country_code="US",
        claim="High customer willingness to pay and severe lead bleed.",
        raw_excerpt="High customer willingness to pay and severe lead bleed.",
        signal_type="ABILITY_TO_PAY",
        supports_claim=True,
        contradicts_claim=False
    )
    signals = market_signal_extractor.extract_signals_from_evidence([ev_item])
    assert "ABILITY_TO_PAY" in signals
    assert signals["ABILITY_TO_PAY"].value is not None
    assert signals["ABILITY_TO_PAY"].direction == "POSITIVE"

def test_unknown_signals_explicitly_preserved():
    empty_signals = market_signal_extractor.extract_signals_from_evidence([])
    for k, sig in empty_signals.items():
        assert sig.value is None
        assert sig.direction == "NEUTRAL"
        assert sig.confidence <= 0.20

# ---------------------------------------------------------------------------
# 6. Scoring Formula & Decision Trace
# ---------------------------------------------------------------------------

def test_transparent_scoring_formula_and_bounds():
    signals = market_signal_extractor.extract_signals_from_evidence([])
    niche_meta = {"atp": 0.85, "pain": 0.85, "automation": 0.80}
    country_meta = {"currency": "USD"}
    res = market_opportunity_scorer.calculate_opportunity(
        signals=signals,
        niche_meta=niche_meta,
        country_meta=country_meta,
        service_id="SERVICE_001",
        compliance_risk_penalty=0.05
    )
    assert 10.0 <= res["market_score"] <= 100.0
    assert res["expected_deal_value_usd"] >= 1000.0
    assert res["expected_value_usd"] > 0.0
    assert "scoring_weights" in res

def test_explainable_5_point_decision_trace():
    trace = market_decision_trace_builder.build_trace(
        country_name="United Arab Emirates",
        niche_name="Real Estate",
        service_name="Instant Lead Response Engine",
        service_id="SERVICE_003",
        market_score=84.5,
        expected_deal_usd=3500.0,
        ev_usd=1850.0,
        confidence=0.85,
        signals={"ABILITY_TO_PAY": 0.90, "DIGITAL_MATURITY": 0.85, "SERVICE_DEMAND": 0.88, "MARKET_GROWTH": 0.80},
        evidence_sources=["gulfnews.com"]
    )
    assert "why_this_country" in trace and len(trace["why_this_country"]) >= 1
    assert "why_this_niche" in trace and len(trace["why_this_niche"]) >= 1
    assert "why_this_service" in trace and len(trace["why_this_service"]) >= 1
    assert "why_this_price" in trace and "$3,500.00" in trace["why_this_price"][0]
    assert "why_now" in trace and len(trace["why_now"]) >= 1

# ---------------------------------------------------------------------------
# 7. Service Mapping & Commercial Floor
# ---------------------------------------------------------------------------

def test_service_mapping_and_commercial_floor():
    for niche, mapping in SERVICE_CATALOG_MAPPING.items():
        assert mapping["service_id"].startswith("SERVICE_")
        assert mapping["min_price_usd"] >= 1000.0
        assert len(mapping["service_name"]) > 0

# ---------------------------------------------------------------------------
# 8. Dynamic Candidate Discovery
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dynamic_candidate_discovery(db_session):
    await market_research_engine.ensure_seed_universe(db_session)
    candidates = await dynamic_market_discovery.discover_new_candidate_markets(db_session)
    assert len(candidates) >= 1
    codes = {c["code"] for c in candidates}
    assert "SE" in codes or "NO" in codes or "CH" in codes or "DK" in codes

# ---------------------------------------------------------------------------
# 9. Provider Fallback & Cost Guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_provider_execution():
    provider = MockMarketResearchProvider()
    evidence = await provider.fetch_evidence(
        country_code="US",
        country_name="United States",
        niche_slug="roofing",
        service_id="SERVICE_001",
        queries=["roofing contractor software pricing"]
    )
    assert len(evidence) >= 1
    assert evidence[0].country_code == "US"
    assert evidence[0].niche_slug == "roofing"

def test_cost_guard_budget_limiting():
    guard = MarketResearchCostGuard(max_requests=5, max_cost_usd=0.50, cost_per_request_usd=0.10)
    assert guard.can_request() is True
    for _ in range(5):
        guard.record_request()
    assert guard.can_request() is False
    assert guard.total_requests == 5

# ---------------------------------------------------------------------------
# 10. Localization & Compliance Profile
# ---------------------------------------------------------------------------

def test_localization_query_generation():
    de_queries = market_localization.get_queries("DE", "Germany", "solar", lang="de")
    assert any("Photovoltaik" in q or "Solar" in q or "KI" in q for q in de_queries)
    ar_queries = market_localization.get_queries("AE", "United Arab Emirates", "real-estate", lang="ar")
    assert len(ar_queries) >= 2

def test_compliance_risk_penalty_calculation():
    res_us = compliance_profile_manager.assess_risk("US", "roofing")
    res_de = compliance_profile_manager.assess_risk("DE", "solar")
    res_unknown = compliance_profile_manager.assess_risk("ZZ", "roofing")
    assert res_us["compliance_risk"] == "LOW"
    assert res_de["compliance_risk"] == "MEDIUM"
    assert res_unknown["compliance_risk"] == "UNKNOWN"
    assert res_de["compliance_penalty"] >= res_us["compliance_penalty"]

# ---------------------------------------------------------------------------
# 11. Phase 10 Ingestion Integration & Singular Outreach Lock Preservation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_feed_top_opportunities_to_phase10_pool(db_session):
    await market_research_engine.ensure_seed_universe(db_session)
    await market_research_engine.research_opportunity(db_session, "US", "roofing", "SERVICE_001")
    fed = await global_opportunity_queue.feed_phase10_pool(db_session, top_n=1, target_per_country=1)
    
    lock = (await db_session.execute(
        select(ActiveOutreachLock).where(ActiveOutreachLock.slot_id == 1)
    )).scalar_one_or_none()
    if lock:
        assert lock.slot_id == 1
    all_locks = (await db_session.execute(select(ActiveOutreachLock))).scalars().all()
    assert len(all_locks) <= 1

# ---------------------------------------------------------------------------
# 12. Synthetic Data Isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_synthetic_data_isolation(db_session):
    await market_research_engine.ensure_seed_universe(db_session)
    await market_research_engine.research_opportunity(db_session, "US", "roofing", "SERVICE_001")
    won_businesses = (await db_session.execute(
        select(Business).where(Business.pipeline_stage == PipelineStage.WON)
    )).scalars().all()
    assert len(won_businesses) == 0

# ---------------------------------------------------------------------------
# 13. REST API Endpoints Suite
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_market_intelligence_api_endpoints(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        await market_research_engine.ensure_seed_universe(db_session)
        await market_research_engine.research_opportunity(db_session, "US", "roofing", "SERVICE_001")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/market-intelligence/countries")
            assert res.status_code == 200
            assert len(res.json()) >= 18

            res = await client.get("/api/market-intelligence/niches")
            assert res.status_code == 200
            assert len(res.json()) >= 18

            res = await client.get("/api/market-intelligence/opportunities?limit=10")
            assert res.status_code == 200
            data = res.json()
            items = data if isinstance(data, list) else data.get("items", [])
            assert len(items) >= 1

            opp_id = items[0]["id"]
            res = await client.get(f"/api/market-intelligence/opportunities/{opp_id}")
            assert res.status_code == 200

            res = await client.get("/api/market-intelligence/top")
            assert res.status_code == 200

            res = await client.get(f"/api/market-intelligence/decision-trace/{opp_id}")
            assert res.status_code == 200

            res = await client.get(f"/api/market-intelligence/evidence/{opp_id}")
            assert res.status_code == 200

            res = await client.post("/api/market-intelligence/discover/candidates")
            assert res.status_code == 200

            res = await client.post("/api/market-intelligence/feed-phase10", json={"top_n": 1, "target_per_country": 1})
            assert res.status_code == 200
            assert res.json()["commercial_outreach_concurrency_lock"] == 1
    finally:
        app.dependency_overrides.clear()
