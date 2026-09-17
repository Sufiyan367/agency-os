"""
Focused test suite for Dynamic Multi-Niche Revenue Acquisition.
Covers the 11 required invariants:
1. Multiple niches coexist in portfolio (>= 4 distinct niches)
2. Portfolio does not collapse to one niche (no niche > 30%)
3. Exploit mode strictly requires actual real evidence (sample >= 10 and positive outcomes)
4. Explore mode is assigned for insufficient data
5. Zero fabricated historical performance (truthful zero metrics)
6. High-value niches enter dynamically based on commercial potential
7. No hardcoded permanent city or niche monopoly (multiple cities & countries)
8. Qualified lead invariant preserved (>= 55.0 score, audited, compliant)
9. Invalid email artifacts remain rejected (image artifacts, malformed strings)
10. Market selection score is strictly operational and not treated as revenue
11. Duplicate businesses remain excluded
"""

import pytest
from app.market_intelligence.autonomous_market_engine import (
    AutonomousMarketIntelligenceEngine,
    autonomous_market_engine,
    HARD_EXCLUDED_COUNTRIES,
    TargetReasonCode,
)
from app.analytics.truth_engine import is_lead_qualified
from app.core.security import sanitize_scraped_email, normalize_domain
from app.database.models import Business, PipelineStage
from sqlalchemy import select


@pytest.mark.asyncio
async def test_1_multiple_niches_coexist_in_portfolio(db_session):
    """Invariant 1: Active portfolio contains at least 4 distinct high-value niches."""
    engine = AutonomousMarketIntelligenceEngine()
    portfolio = await engine.rebalance_target_queue(db_session, force=True)
    assert len(portfolio) >= 8, f"Expected at least 8 active corridors, got {len(portfolio)}"
    
    distinct_niches = set(t.niche_id for t in portfolio)
    assert len(distinct_niches) >= 4, (
        f"Portfolio must contain >= 4 distinct niches to prevent single-niche concentration. "
        f"Found: {distinct_niches}"
    )


@pytest.mark.asyncio
async def test_2_portfolio_does_not_collapse_to_one_niche(db_session):
    """Invariant 2: No single niche represents more than 30% of the active portfolio."""
    engine = AutonomousMarketIntelligenceEngine()
    portfolio = await engine.rebalance_target_queue(db_session, force=True)
    total_active = len(portfolio)
    assert total_active > 0

    niche_counts = {}
    for t in portfolio:
        niche_counts[t.niche_id] = niche_counts.get(t.niche_id, 0) + 1

    for niche_id, count in niche_counts.items():
        share = count / total_active
        assert share <= 0.30, (
            f"Niche {niche_id} has {count}/{total_active} ({share:.1%}) share, "
            f"exceeding the 30% concentration ceiling."
        )


@pytest.mark.asyncio
async def test_3_exploit_requires_actual_real_evidence(db_session):
    """Invariant 3: EXPLOIT mode strictly requires sample_size >= 10 and real positive outcomes."""
    engine = AutonomousMarketIntelligenceEngine()
    
    # Sub-case A: 0 sample size -> EXPLORE
    empty_outcomes = {
        "sample_size": 0, "reply_rate": 0.0, "positive_replies": 0,
        "won_deals": 0, "verified_revenue": 0.0, "last_interaction": None,
        "qualified_leads": 0, "outreach_sent": 0, "total_replies": 0
    }
    score_a, conf_a, reasons_a, mode_a = engine._score_target("US", "ROOFING", empty_outcomes)
    assert mode_a == "EXPLORE", f"Expected EXPLORE for 0 samples, got {mode_a}"
    assert TargetReasonCode.EXPLORATION_REQUIRED in reasons_a

    # Sub-case B: Insufficient sample size (< 10) even with positive reply -> EXPLORE
    insufficient_outcomes = {
        "sample_size": 5, "reply_rate": 0.20, "positive_replies": 1,
        "won_deals": 0, "verified_revenue": 0.0, "last_interaction": None,
        "qualified_leads": 5, "outreach_sent": 5, "total_replies": 1
    }
    score_b, conf_b, reasons_b, mode_b = engine._score_target("US", "LEGAL_SERVICES", insufficient_outcomes)
    assert mode_b == "EXPLORE", f"Sample size 5 (< 10) must remain EXPLORE, got {mode_b}"

    # Sub-case C: Sufficient sample (>= 10) and real positive outcome -> EXPLOIT
    proven_outcomes = {
        "sample_size": 15, "reply_rate": 0.20, "positive_replies": 3,
        "won_deals": 1, "verified_revenue": 2500.0, "last_interaction": None,
        "qualified_leads": 15, "outreach_sent": 15, "total_replies": 3
    }
    score_c, conf_c, reasons_c, mode_c = engine._score_target("US", "LEGAL_SERVICES", proven_outcomes)
    assert mode_c == "EXPLOIT", f"Sample size 15 with positive replies and revenue must be EXPLOIT, got {mode_c}"
    assert TargetReasonCode.POSITIVE_HISTORICAL_OUTCOMES in reasons_c


@pytest.mark.asyncio
async def test_4_explore_mode_for_insufficient_data(db_session):
    """Invariant 4: Markets without empirical proof remain in EXPLORE mode with is_insufficient_data=True."""
    engine = AutonomousMarketIntelligenceEngine()
    portfolio = await engine.rebalance_target_queue(db_session, force=True)
    
    # In a clean DB, all baseline targets must be in EXPLORE mode with is_insufficient_data == True
    for item in portfolio:
        assert item.mode == "EXPLORE", f"Unproven market {item.key} should be EXPLORE, got {item.mode}"
        assert item.is_insufficient_data is True, f"Unproven market {item.key} must flag is_insufficient_data=True"


@pytest.mark.asyncio
async def test_5_no_fabricated_historical_performance(db_session):
    """Invariant 5: Zero fabricated historical performance; all telemetry reflects factual zero metrics."""
    engine = AutonomousMarketIntelligenceEngine()
    await engine.rebalance_target_queue(db_session, force=True)
    res = await engine.get_autonomous_target_queue(db_session)
    active = res.get("active_portfolio", [])
    assert len(active) > 0

    for m in active:
        assert m["historical_sample_count"] == 0, f"Expected 0 historical samples, got {m['historical_sample_count']}"
        assert m["win_rate"] == 0.0, f"Expected 0.0 win rate, got {m['win_rate']}"
        assert m["real_revenue"] == 0.0, f"Expected $0.0 real revenue, got {m['real_revenue']}"
        assert m["real_outreach_count"] == 0, f"Expected 0 real outreach, got {m['real_outreach_count']}"
        assert m["real_reply_count"] == 0, f"Expected 0 real replies, got {m['real_reply_count']}"
        assert m["is_insufficient_data"] is True


@pytest.mark.asyncio
async def test_6_high_value_niches_enter_dynamically(db_session):
    """Invariant 6: High-value commercial niches enter dynamically based on service value weighting."""
    engine = AutonomousMarketIntelligenceEngine()
    portfolio = await engine.rebalance_target_queue(db_session, force=True)
    active_niches = set(t.niche_id for t in portfolio)

    # Check that high-ticket service niches (min deal >= $2,000) are represented
    high_value_candidates = {"LEGAL_SERVICES", "MEDICAL_CLINICS", "REAL_ESTATE", "DENTAL", "HVAC", "REMODELING"}
    overlap = active_niches.intersection(high_value_candidates)
    assert len(overlap) >= 3, (
        f"Dynamic portfolio should prioritize high-value niches. "
        f"Active: {active_niches}, Expected overlap with {high_value_candidates}: {overlap}"
    )


@pytest.mark.asyncio
async def test_7_no_hardcoded_permanent_city_niche_monopoly(db_session):
    """Invariant 7: No permanent monopoly on a single city or country; portfolio is geographically diversified."""
    engine = AutonomousMarketIntelligenceEngine()
    portfolio = await engine.rebalance_target_queue(db_session, force=True)
    
    distinct_countries = set(t.country_code for t in portfolio)
    distinct_cities = set(t.city for t in portfolio)
    
    assert len(distinct_countries) >= 3, f"Expected >= 3 distinct countries, got {distinct_countries}"
    assert len(distinct_cities) >= 6, f"Expected >= 6 distinct cities, got {len(distinct_cities)}: {distinct_cities}"


def test_8_qualified_lead_invariant_preserved():
    """Invariant 8: Canonical qualification floor (score >= 55.0, audited, compliant) is strictly preserved."""
    class DummyBiz:
        def __init__(self, country="US", domain="austinlegal.com", email="contact@austinlegal.com", verification_status="VERIFIED"):
            self.id = 101
            self.name = "Austin Legal Counsel"
            self.domain = domain
            self.website_url = f"https://{domain}"
            self.country = country
            self.public_email = email
            self.niche = "legal-services"
            self.verification_status = verification_status
            self.whatsapp_consent_status = "INELIGIBLE_NO_CONSENT"
            self.compliance_status = "CLEARED"
            self.compliance_flags = []
            self.pipeline_stage = PipelineStage.AUDITED.value

    class DummyScore:
        def __init__(self, total_score=75.0):
            self.total_score = total_score

    class DummyAudit:
        def __init__(self, score=78.0, url="https://austinlegal.com", findings=None, summary="Healthy site"):
            self.overall_health_score = score
            self.url_audited = url
            self.findings = findings if findings is not None else [{"code": "PAGE_SPEED_LOW", "title": "Slow LCP"}]
            self.summary = summary
            self.metrics = {}

    biz = DummyBiz()
    audit = DummyAudit()
    good_score = DummyScore(75.0)
    floor_score = DummyScore(55.0)
    sub_floor_score = DummyScore(54.9)
    zero_score = DummyScore(0.0)

    # Case A: Score < 55.0 cannot qualify
    assert is_lead_qualified(biz, sub_floor_score, audit=audit) is False
    assert is_lead_qualified(biz, zero_score, audit=audit) is False

    # Case B: Missing audit cannot qualify
    assert is_lead_qualified(biz, good_score, audit=None) is False

    # Case C: Audit with 0 findings or empty URL cannot qualify
    empty_url_audit = DummyAudit(url="")
    assert is_lead_qualified(biz, good_score, audit=empty_url_audit) is False
    no_findings_audit = DummyAudit(findings=[])
    assert is_lead_qualified(biz, good_score, audit=no_findings_audit) is False

    # Case D: Prohibited country cannot qualify
    biz_prohibited = DummyBiz(country="IN")
    assert is_lead_qualified(biz_prohibited, good_score, audit=audit) is False

    # Case E: Unverified business cannot qualify
    biz_unverified = DummyBiz(verification_status="UNVERIFIED")
    assert is_lead_qualified(biz_unverified, good_score, audit=audit) is False

    # Case F: Valid lead meeting all invariants qualifies
    assert is_lead_qualified(biz, floor_score, audit=audit) is True
    assert is_lead_qualified(biz, good_score, audit=audit) is True


def test_9_invalid_email_artifacts_remain_rejected():
    """Invariant 9: Email sanitization strictly rejects image artifacts, data URIs, and malformed strings."""
    invalid_cases = [
        "hero-image@2x.png",
        "logo@3x.jpg",
        "graphic@2x.jpeg",
        "icon@svg.png",
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA",
        "support@.com",
        "plainaddress",
        "@missingusername.com",
        "two@@domain.com"
    ]
    for case in invalid_cases:
        sanitized = sanitize_scraped_email(case)
        assert sanitized is None, f"Expected rejection for '{case}', but got '{sanitized}'"


@pytest.mark.asyncio
async def test_10_market_selection_score_not_treated_as_revenue(db_session):
    """Invariant 10: Market selection score is strictly an operational rank, distinct from revenue."""
    engine = AutonomousMarketIntelligenceEngine()
    portfolio = await engine.rebalance_target_queue(db_session, force=True)
    assert len(portfolio) > 0

    for item in portfolio:
        # Operational score is a prioritization ranking [0, 100]
        assert 0.0 <= item.score <= 100.0
        # Financial revenue in clean state is strictly $0.0, never populated with score
        assert item.real_revenue == 0.0
        assert item.score != item.real_revenue or item.score == 0.0


@pytest.mark.asyncio
async def test_11_duplicate_businesses_remain_excluded(db_session):
    """Invariant 11: Domain normalization and deduplication prevents duplicate businesses."""
    dom = "austinpremierlaw.com"
    norm1 = normalize_domain("https://www.austinpremierlaw.com/about")
    norm2 = normalize_domain("http://austinpremierlaw.com/")
    assert norm1 == dom
    assert norm2 == dom

    # Insert first business
    biz1 = Business(
        name="Austin Premier Law",
        domain=dom,
        website_url="https://austinpremierlaw.com",
        country="US",
        niche="legal-services",
        public_email="info@austinpremierlaw.com"
    )
    db_session.add(biz1)
    await db_session.commit()

    # Query existing domains as done in discovery
    existing_domains_q = select(Business.domain)
    existing_domains = set((await db_session.execute(existing_domains_q)).scalars().all())
    assert dom in existing_domains

    # Second discovery attempt of the same domain must be detected as duplicate
    duplicate_candidate_domain = "https://www.austinpremierlaw.com/contact"
    norm_candidate = normalize_domain(duplicate_candidate_domain)
    is_duplicate = norm_candidate in existing_domains
    assert is_duplicate is True, "Duplicate domain must be detected and excluded from insertion."
