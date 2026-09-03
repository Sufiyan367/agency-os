import os
import pytest
from httpx import AsyncClient, ASGITransport
from app.api.app import app
from app.core.config import settings
from app.core.production_mode import first_client_mode
from app.database.production_init import production_reset_service
from app.lead_generation.providers.prospect_provider import RealProspectProvider
from app.lead_generation.targeting import load_targeting_config
from app.lead_generation.buyer_scoring import HighValueBuyerScorer
from app.lead_generation.schemas import NormalizedBusinessRecord, ProspectClassification, RejectionReason
from app.lead_generation.service import ProspectQualityFilter
from app.outreach.contact_verifier import contactability_verifier

@pytest.fixture(autouse=True)
def preserve_env_and_db():
    """Preserves .env state and safety flags across test executions."""
    orig_email_dry = settings.EMAIL_DRY_RUN
    orig_pay_dry = settings.PAYMENT_DRY_RUN
    orig_pay_mode = getattr(settings, "RAZORPAY_MODE", "test")

    yield

    settings.EMAIL_DRY_RUN = orig_email_dry
    settings.PAYMENT_DRY_RUN = orig_pay_dry
    setattr(settings, "RAZORPAY_MODE", orig_pay_mode)


@pytest.mark.asyncio
async def test_zero_state_dashboard_metrics():
    """
    Verifies that on a clean production database, all KPI metrics start at exactly 0.
    """
    production_reset_service.initialize_clean_production(create_backup=False)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/metrics")
        assert res.status_code == 200
        data = res.json()

        # Zero-state baseline verification
        assert data["leads"]["total"] == 0
        assert data["leads"]["qualified"] == 0
        assert data["outreach"]["sent"] == 0
        assert data["sales"]["replies_total"] == 0
        assert data["sales"]["calls_scheduled"] == 0
        assert data["sales"]["deals_won"] == 0
        assert data["revenue"]["pipeline_value_usd"] == 0.0
        assert data["revenue"]["won_revenue_usd"] == 0.0


@pytest.mark.asyncio
async def test_production_database_initialization_and_reference_preservation():
    """
    Verifies that production reset clears operational tables while strictly
    preserving reference metadata (Countries, Niches, Markets).
    """
    summary = production_reset_service.initialize_clean_production(create_backup=False)
    assert summary["status"] == "INITIALIZED"
    assert summary["mode"] == "FIRST_CLIENT_MODE"
    assert summary["metrics"]["prospects"] == 0
    assert summary["metrics"]["won_deals"] == 0
    assert summary["metrics"]["pipeline_value_usd"] == 0.0

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Reference markets must remain intact
        res = await client.get("/api/markets")
        assert res.status_code == 200
        markets = res.json()
        assert len(markets) > 0
        assert any(m["country_code"] == "US" for m in markets)


@pytest.mark.asyncio
async def test_first_client_mode_safeguards_active():
    """
    Verifies First Client Mode permissions matrix and safeguards:
    - Real discovery: ALLOWED
    - Real audits: ALLOWED
    - Live email sending: BLOCKED (DRY_RUN=True)
    - Live payment charging: BLOCKED (TEST MODE / DRY_RUN=True)
    - Human approval: MANDATORY
    """
    status = first_client_mode.get_mode_status()
    assert status["mode"] == "FIRST_CLIENT_MODE"
    
    perms = status["permissions"]
    assert perms["real_discovery_allowed"] is True
    assert perms["real_audits_allowed"] is True
    assert perms["real_scoring_allowed"] is True
    assert perms["real_dossiers_allowed"] is True
    assert perms["outreach_live_sending"] is False
    assert perms["payment_live_charging"] is False
    assert perms["human_approval_mandatory"] is True
    assert perms["autonomous_negotiation_allowed"] is False
    assert perms["autonomous_contract_acceptance"] is False
    assert perms["commercial_threshold_usd"] >= 500.0

    # Human approval gate check
    with pytest.raises(RuntimeError) as exc:
        first_client_mode.verify_outreach_allowed(is_operator_approved=False)
    assert "Automated direct outreach dispatch is strictly blocked" in str(exc.value)


@pytest.mark.asyncio
async def test_real_prospect_discovery_and_directory_rejection():
    """
    Verifies that real prospect discovery filters out directory aggregators,
    social profiles, and parked domains.
    """
    is_valid_yelp, reason_yelp = ProspectQualityFilter.check_validity("yelp.com", "https://yelp.com/biz/austin-hvac")
    assert is_valid_yelp is False
    assert reason_yelp == RejectionReason.DIRECTORY_AGGREGATOR

    is_valid_fb, reason_fb = ProspectQualityFilter.check_validity("facebook.com", "https://facebook.com/hvacpros")
    assert is_valid_fb is False
    assert reason_fb == RejectionReason.SOCIAL_PROFILE

    is_valid_parked, reason_parked = ProspectQualityFilter.check_validity("godaddy.com", "https://godaddy.com")
    assert is_valid_parked is False
    assert reason_parked == RejectionReason.PARKED_DOMAIN

    # Valid commercial domain passes
    is_valid_real, reason_real = ProspectQualityFilter.check_validity("austinairpros.com", "https://austinairpros.com")
    assert is_valid_real is True
    assert reason_real is None


@pytest.mark.asyncio
async def test_five_hundred_dollar_commercial_threshold_and_scoring():
    """
    Verifies that the $500+ commercial threshold is strictly enforced and
    sub-threshold / low-capacity operators are rejected with explainable reasons.
    """
    targeting = load_targeting_config()
    scorer = HighValueBuyerScorer(targeting.commercial)

    # 1. Sub-$500 solo operator
    tiny_biz = NormalizedBusinessRecord(
        business_name="Solo Handyman",
        category="Cleaning",
        city="Austin",
        region="Texas",
        country="US",
        num_locations=1,
        is_commercial_and_residential=False,
        has_fleet_or_technicians=False,
        years_in_business=1,
        rating=3.5,
        review_count=6,
        phone="512-555-0100"
    )
    res_tiny = scorer.evaluate_prospect(tiny_biz)
    assert res_tiny.classification == ProspectClassification.LOW_VALUE
    assert "unlikely to purchase" in res_tiny.classification_rationale or "Low estimated purchasing capacity" in res_tiny.classification_rationale

    # 2. Large established business ($500+ capable)
    large_biz = NormalizedBusinessRecord(
        business_name="Lone Star Industrial HVAC & Mechanical",
        category="HVAC",
        city="Austin",
        region="Texas",
        country="US",
        num_locations=3,
        is_commercial_and_residential=True,
        has_fleet_or_technicians=True,
        offers_emergency_service=True,
        authorized_dealer_or_financing=True,
        affluent_service_area=True,
        years_in_business=14,
        rating=4.8,
        review_count=165,
        email="commercial@lonestarhvac.com",
        phone="512-555-0199",
        page_speed_issue=True,
        mobile_ux_issue=True,
        seo_issue=True
    )
    res_large = scorer.evaluate_prospect(large_biz)
    assert res_large.classification == ProspectClassification.PRIORITY_PROSPECT
    assert res_large.estimated_service_value.min_value >= 500
    assert "Strong evidence that this business is commercially suitable" in res_large.classification_rationale


@pytest.mark.asyncio
async def test_no_fabricated_contact_data():
    """
    Verifies that the system NEVER fabricates contact info when missing.
    Unobserved contacts strictly enter CONTACT_UNAVAILABLE.
    """
    res = contactability_verifier.verify_contact_email(None, "real-domain.com")
    assert res.is_valid is False
    assert res.status == "CONTACT_UNAVAILABLE"
    assert res.email is None

    res_empty = contactability_verifier.verify_contact_email("", "real-domain.com")
    assert res_empty.is_valid is False
    assert res_empty.status == "CONTACT_UNAVAILABLE"

    # Synthetic fallback like info@domain without observation must not be generated
    res_fake = contactability_verifier.verify_contact_email("info@example.com", "example.com")
    assert res_fake.is_valid is False
    assert res_fake.status == "CONTACT_UNAVAILABLE"
    assert "example.com" in res_fake.reason.lower()


@pytest.mark.asyncio
async def test_production_api_routes():
    """Verifies that /api/production/status and /api/production/reset endpoints respond correctly."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/production/status")
        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "FIRST_CLIENT_MODE"
        assert data["permissions"]["human_approval_mandatory"] is True

        res_reset = await client.post("/api/production/reset")
        assert res_reset.status_code == 200
        reset_data = res_reset.json()
        assert reset_data["status"] == "INITIALIZED"
        assert reset_data["metrics"]["prospects"] == 0
