"""Comprehensive Test Suite for Phase 7: Client Intelligence & Service Matching Engine.
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport

from app.client_intelligence.models import (
    BusinessSegment,
    PainCategory,
    BusinessProfile,
    BusinessSizeEstimate,
    DetectedPainPoint,
    OperationalWasteEstimate,
    ServiceMatch,
    ROIEstimate,
    ClientOffer,
    PricingRecommendation,
    DecisionTrace,
)
from app.client_intelligence.catalog import SERVICE_CATALOG, service_catalog
from app.client_intelligence.profiler import BusinessProfiler
from app.client_intelligence.size_estimator import BusinessSizeEstimator
from app.client_intelligence.pain_detector import PainPointDetector
from app.client_intelligence.waste_detector import OperationalWasteDetector
from app.client_intelligence.matcher import ServiceMatcher
from app.client_intelligence.roi_estimator import ROIEstimator
from app.client_intelligence.pricing import PricingEngine
from app.client_intelligence.composer import OfferComposer
from app.client_intelligence.selector import ProspectSelector
from app.client_intelligence.traceability import DecisionTraceManager
from app.client_intelligence.engine import ClientIntelligenceEngine
from app.database.models import Business, AuditRun, AuditFinding, ClientIntelligenceRecord, ProspectMemory
from app.api.app import app


class MockBusiness:
    def __init__(self, id=1, name="Apex Roof Works", domain="apexroofing.com", niche="Roofing Contractors", country="United States", city="Dallas"):
        self.id = id
        self.name = name
        self.domain = domain
        self.niche = niche
        self.country = country
        self.city = city
        self.address = "123 Main St, Dallas, TX"
        self.public_email = "service@apexroofing.com"
        self.phone = "+1-214-555-0199"
        self.contact_page_url = "https://apexroofing.com/contact"
        self.social_profiles = {}
        self.memory = None


class MockAudit:
    def __init__(self, overall_health_score=52.0, performance_score=48.0, seo_score=62.0, a11y_score=55.0, ux_conversion_score=45.0, tech_stack=None):
        self.overall_health_score = overall_health_score
        self.performance_score = performance_score
        self.seo_score = seo_score
        self.a11y_score = a11y_score
        self.ux_conversion_score = ux_conversion_score
        self.tech_stack = tech_stack or ["WordPress", "Apache"]
        self.metrics = {"performance": performance_score, "seo": seo_score, "ux": ux_conversion_score}
        self.findings = []


# 1. Service Catalog Tests
def test_service_catalog_completeness():
    services = service_catalog.list_services()
    assert len(services) == 10
    service_ids = {s.id for s in services}
    for i in range(1, 11):
        assert f"SERVICE_{i:03d}" in service_ids

    for s in services:
        assert s.pricing_min_usd >= 500.0, f"Service {s.id} violates $500 floor"
        assert s.recommended_target_price_usd >= 1000.0, f"Service {s.id} target must be >= $1,000"
        assert len(s.suitable_business_sizes) > 0
        assert s.implementation_complexity in ("Low", "Moderate", "High", "Enterprise")
        assert len(s.expected_business_outcomes) >= 2


# 2. Business Profiler Tests
def test_business_profiler_with_signals():
    profiler = BusinessProfiler()
    biz = MockBusiness()
    audit = MockAudit(tech_stack=["WordPress", "Contact Form 7"])
    raw_signals = {"reviews_count": 34, "rating": 4.8}

    profile = profiler.profile_business(biz, audit=audit, raw_signals=raw_signals)
    assert profile.business_name == "Apex Roof Works"
    assert profile.domain == "apexroofing.com"
    assert profile.industry.value == "Roofing Contractors"
    assert profile.location.value == "Dallas, United States"
    assert profile.website_quality.value == 52.0
    assert "email" in profile.contact_channels.value
    assert profile.booking_workflow.value == "static_form"
    assert profile.review_signals.value["count"] == 34


def test_business_profiler_honesty_on_missing_data():
    profiler = BusinessProfiler()
    sparse_biz = MockBusiness(name="", domain="anon-corp.net", niche="", country="", city="")
    sparse_biz.public_email = None
    sparse_biz.phone = None
    sparse_biz.contact_page_url = None

    profile = profiler.profile_business(sparse_biz, audit=None, raw_signals={})
    assert profile.industry.value == "UNKNOWN"
    assert profile.industry.confidence <= 0.2
    assert profile.location.value == "UNKNOWN"
    assert profile.review_signals.value == "UNKNOWN"


# 3. Size Estimator Tests
def test_size_estimator_segments():
    estimator = BusinessSizeEstimator()
    profiler = BusinessProfiler()
    biz = MockBusiness()

    # Small local contractor
    audit_small = MockAudit(tech_stack=["WordPress"])
    prof_small = profiler.profile_business(biz, audit=audit_small, raw_signals={"reviews_count": 45})
    size_small = estimator.estimate_size(prof_small, business=biz)
    assert size_small.segment in (BusinessSegment.SMALL, BusinessSegment.SMB)

    # Enterprise signals
    audit_ent = MockAudit(tech_stack=["Salesforce", "Marketo", "Workday"])
    prof_ent = profiler.profile_business(biz, audit=audit_ent, raw_signals={})
    size_ent = estimator.estimate_size(prof_ent, business=biz)
    assert size_ent.segment == BusinessSegment.ENTERPRISE


# 4. Pain Point Detector Tests
def test_pain_point_detector_finds_verifiable_issues():
    detector = PainPointDetector()
    profiler = BusinessProfiler()
    estimator = BusinessSizeEstimator()
    
    biz = MockBusiness()
    audit = MockAudit(performance_score=35.0, ux_conversion_score=40.0, tech_stack=["WordPress"])
    prof = profiler.profile_business(biz, audit=audit, raw_signals={})
    size = estimator.estimate_size(prof, business=biz)

    pains = detector.detect_pain_points(prof, size, audit=audit)
    categories = {p.category for p in pains}

    assert PainCategory.APPOINTMENT_SCHEDULING in categories
    assert PainCategory.WEBSITE_CONVERSION in categories
    assert PainCategory.CRM_DATA_ENTRY in categories
    for p in pains:
        assert len(p.evidence) > 0, "Pain point must contain concrete evidence"
        assert p.severity > 0.0


# 5. Operational Waste Detector Tests
def test_waste_detector_calculates_bounds():
    detector = OperationalWasteDetector()
    profiler = BusinessProfiler()
    estimator = BusinessSizeEstimator()
    pain_det = PainPointDetector()

    biz = MockBusiness()
    audit = MockAudit()
    prof = profiler.profile_business(biz, audit=audit, raw_signals={})
    size = estimator.estimate_size(prof, business=biz)
    pains = pain_det.detect_pain_points(prof, size, audit=audit)

    waste = detector.estimate_waste(prof, size, pains)
    assert waste.estimated_manual_hours_weekly_low > 0.0
    assert waste.estimated_manual_hours_weekly_high >= waste.estimated_manual_hours_weekly_low
    assert 10.0 <= waste.automation_opportunity_score <= 100.0
    assert len(waste.observed_inefficiencies) > 0


# 6. Service Matcher Tests
def test_service_matcher_ranks_appropriate_service():
    matcher = ServiceMatcher()
    profiler = BusinessProfiler()
    estimator = BusinessSizeEstimator()
    pain_det = PainPointDetector()
    waste_det = OperationalWasteDetector()

    biz = MockBusiness()
    audit = MockAudit()
    prof = profiler.profile_business(biz, audit=audit, raw_signals={})
    size = estimator.estimate_size(prof, business=biz)
    pains = pain_det.detect_pain_points(prof, size, audit=audit)
    waste = waste_det.estimate_waste(prof, size, pains)

    matches = matcher.match_services(prof, size, pains, waste)
    assert len(matches) > 0
    top = matches[0]
    assert top.fit_score > 0.4
    assert len(top.reasons) > 0


def test_service_matcher_filters_contraindications():
    matcher = ServiceMatcher()
    profiler = BusinessProfiler()
    estimator = BusinessSizeEstimator()
    pain_det = PainPointDetector()
    waste_det = OperationalWasteDetector()

    biz = MockBusiness()
    # Has active Calendly widget
    audit = MockAudit(tech_stack=["Calendly", "HubSpot"])
    prof = profiler.profile_business(biz, audit=audit, raw_signals={})
    size = estimator.estimate_size(prof, business=biz)
    pains = pain_det.detect_pain_points(prof, size, audit=audit)
    waste = waste_det.estimate_waste(prof, size, pains)

    matches = matcher.match_services(prof, size, pains, waste)
    matched_ids = {m.service_id for m in matches}
    # SERVICE_006 (Appointment Automation) should be contraindicated
    assert "SERVICE_006" not in matched_ids


# 7. ROI Estimator Tests
def test_roi_estimator_bounds_and_safety():
    roi_est = ROIEstimator()
    profiler = BusinessProfiler()
    estimator = BusinessSizeEstimator()
    matcher = ServiceMatcher()

    biz = MockBusiness()
    prof = profiler.profile_business(biz, audit=MockAudit(), raw_signals={})
    size = estimator.estimate_size(prof, business=biz)
    waste = OperationalWasteEstimate(
        estimated_manual_hours_weekly_low=4.0,
        estimated_manual_hours_weekly_high=8.0,
        automation_opportunity_score=75.0,
        observed_inefficiencies=["Manual scheduling back-and-forth"],
    )
    match = ServiceMatch(
        service_id="SERVICE_001",
        service_name="AI Lead Qualification",
        fit_score=0.85,
        reasons=["Direct fit"],
        evidence=["Form with no qualification"],
    )

    roi = roi_est.estimate_roi(prof, size, waste, match)
    assert roi.status == "ESTIMATED"
    assert roi.monthly_value_expected_usd > 0.0
    assert roi.monthly_value_high_usd >= roi.monthly_value_expected_usd >= roi.monthly_value_low_usd
    assert len(roi.assumptions) >= 2


def test_roi_estimator_insufficient_data():
    roi_est = ROIEstimator()
    biz = MockBusiness()
    prof = BusinessProfiler().profile_business(biz)
    size = BusinessSizeEstimate(segment=BusinessSegment.MICRO)
    empty_waste = OperationalWasteEstimate()

    roi = roi_est.estimate_roi(prof, size, empty_waste, None)
    assert roi.status == "INSUFFICIENT_DATA"
    assert roi.monthly_value_expected_usd is None


# 8. Pricing Engine Tests
def test_pricing_engine_enforces_commercial_rules():
    pricing = PricingEngine()
    biz = MockBusiness()
    prof = BusinessProfiler().profile_business(biz)
    size_micro = BusinessSizeEstimate(segment=BusinessSegment.MICRO)
    size_small = BusinessSizeEstimate(segment=BusinessSegment.SMALL)
    size_smb = BusinessSizeEstimate(segment=BusinessSegment.SMB)

    match = ServiceMatch(
        service_id="SERVICE_001",
        service_name="AI Lead Qualification",
        fit_score=0.8,
    )

    p_micro = pricing.recommend_pricing(prof, size_micro, match)
    assert p_micro.recommended_price_usd >= 500.0, "Never quote below $500 floor"
    assert p_micro.target_price_usd >= 1000.0, "Target minimum is $1,000"

    p_small = pricing.recommend_pricing(prof, size_small, match)
    assert p_small.recommended_price_usd >= 1000.0

    p_smb = pricing.recommend_pricing(prof, size_smb, match)
    assert p_smb.recommended_price_usd >= 1250.0


# 9. Offer Composer Tests
def test_offer_composer_creates_8_part_offer():
    composer = OfferComposer()
    biz = MockBusiness()
    prof = BusinessProfiler().profile_business(biz)
    size = BusinessSizeEstimate(segment=BusinessSegment.SMALL)
    match = ServiceMatch(
        service_id="SERVICE_001",
        service_name="AI Lead Qualification",
        fit_score=0.85,
        evidence=["Manual web form"],
    )
    pricing = PricingRecommendation(
        recommended_price_usd=1200.0,
        target_price_usd=1500.0,
        minimum_price_usd=500.0,
    )
    pains = [
        DetectedPainPoint(
            category=PainCategory.LEAD_QUALIFICATION,
            severity=0.75,
            evidence=["Manual triage required"],
            estimated_business_impact="Owner spends hours sifting bad leads",
        )
    ]

    offer = composer.compose_offer(prof, size, match, pricing, pains)
    assert offer.problem_statement != ""
    assert len(offer.observed_evidence) > 0
    assert offer.recommended_solution.startswith("AI Lead Qualification")
    assert len(offer.implementation_scope) >= 3
    assert offer.investment_usd == 1200.0
    assert offer.target_investment_usd == 1500.0
    assert offer.timeline_days > 0
    assert "diagnostic walkthrough" in offer.next_step.lower()


# 10. Prospect Selector Tests
def test_prospect_selector_expected_value_ranking():
    selector = ProspectSelector()
    biz = MockBusiness()
    prof = BusinessProfiler().profile_business(biz)
    size = BusinessSizeEstimate(segment=BusinessSegment.SMALL)
    match = ServiceMatch(
        service_id="SERVICE_001",
        service_name="AI Lead Qualification",
        fit_score=0.85,
    )
    pricing = PricingRecommendation(
        recommended_price_usd=1000.0,
        target_price_usd=1200.0,
        minimum_price_usd=500.0,
    )

    eval_data = selector.evaluate_prospect(prof, size, match, pricing, [])
    assert 0.0 < eval_data["p_win"] <= 1.0
    assert eval_data["expected_value_usd"] == 1000.0
    assert eval_data["selection_score"] == round(eval_data["p_win"] * 1000.0, 2)
    assert len(eval_data["why_this_business"]) >= 3


# 11. End-to-End Engine Integration Test
def test_client_intelligence_engine_end_to_end():
    engine = ClientIntelligenceEngine()
    biz = MockBusiness()
    audit = MockAudit()

    res = engine.analyze_business(session=None, business=biz, audit=audit, persist=False)
    assert res["business_id"] == 1
    assert res["domain"] == "apexroofing.com"
    assert "profile" in res
    assert "size_estimate" in res
    assert "pain_points" in res
    assert "service_matches" in res
    assert "top_match" in res
    assert "roi_estimate" in res
    assert "pricing" in res
    assert "offer" in res
    assert "decision_trace" in res
    assert res["pricing"]["recommended_price_usd"] >= 500.0
    assert res["pricing"]["target_price_usd"] >= 1000.0
    assert res["selection_score"] > 0.0
    assert len(res["why_this_business"]) > 0


# 12. API Endpoint Tests
@pytest.mark.asyncio
async def test_client_intelligence_api_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Test services catalog endpoint
        catalog_res = await ac.get("/api/client-intelligence/services")
        assert catalog_res.status_code == 200
        catalog_data = catalog_res.json()
        assert catalog_data["status"] == "SUCCESS"
        assert len(catalog_data["services"]) == 10

        # Test top ranked prospects endpoint
        top_res = await ac.get("/api/client-intelligence/top")
        assert top_res.status_code == 200
        top_data = top_res.json()
        assert top_data["status"] == "SUCCESS"
        assert "prospects" in top_data
