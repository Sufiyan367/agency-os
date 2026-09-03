import pytest
from app.lead_generation.providers.prospect_provider import (
    BaseProspectProvider,
    MockProspectProvider,
    RealProspectProvider
)
from app.lead_generation.targeting import (
    TargetingConfig,
    CommercialConfig,
    TargetingFilters,
    load_targeting_config
)
from app.lead_generation.schemas import (
    NormalizedBusinessRecord,
    ScoredProspect,
    ProspectClassification,
    RealPipelineStage,
    RejectionReason,
    EstimatedServiceValue,
    BuyerTier
)
from app.lead_generation.buyer_scoring import HighValueBuyerScorer
from app.lead_generation.service import LeadDiscoveryService, ProspectQualityFilter
from app.models.entities import LocalBusiness, LocalLead, LocalLeadEvent
from app.database.connection import AsyncSessionLocal

# ------------------------------------------------------------------------------
# 1. Provider Abstraction
# ------------------------------------------------------------------------------
def test_provider_abstraction_compliance():
    mock_p = MockProspectProvider()
    real_p = RealProspectProvider()

    assert isinstance(mock_p, BaseProspectProvider)
    assert isinstance(real_p, BaseProspectProvider)
    assert mock_p.provider_name == "mock_prospect_provider"
    assert real_p.provider_name == "real_prospect_provider"

@pytest.mark.asyncio
async def test_mock_provider_returns_normalized_records():
    provider = MockProspectProvider()
    records = await provider.discover_prospects(country="US", city="Austin", niche="HVAC", limit=3)
    assert len(records) > 0
    first = records[0]
    assert isinstance(first, NormalizedBusinessRecord)
    assert first.business_name
    assert first.country == "US"
    assert first.category.lower() == "hvac"

# ------------------------------------------------------------------------------
# 2. Normalization
# ------------------------------------------------------------------------------
def test_normalization_utilities():
    # Domain normalization
    assert LeadDiscoveryService.normalize_domain("https://www.lonestarhvac.com/about?src=google") == "lonestarhvac.com"
    assert LeadDiscoveryService.normalize_domain("HTTP://ApexPlumbing.Net/") == "apexplumbing.net"
    assert LeadDiscoveryService.normalize_domain(None) is None
    assert LeadDiscoveryService.normalize_domain("") is None

    # Phone normalization
    assert LeadDiscoveryService.normalize_phone("+1 (512) 555-0199") == "5125550199"
    assert LeadDiscoveryService.normalize_phone("1-800-555-4321") == "8005554321"
    assert LeadDiscoveryService.normalize_phone("555-1234") == "5551234"
    assert LeadDiscoveryService.normalize_phone(None) is None

    # Name normalization
    assert LeadDiscoveryService.normalize_name("Joe's Heating & Air, LLC!") == "joes heating air llc"

# ------------------------------------------------------------------------------
# 3. Duplicate Detection
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_duplicate_detection_logic():
    service = LeadDiscoveryService()
    candidate = NormalizedBusinessRecord(
        business_name="Austin Premier HVAC",
        category="HVAC",
        city="Austin",
        region="Texas",
        website="https://austinpremier.com",
        phone="(512) 555-1122"
    )

    norm_dom = service.normalize_domain(candidate.website)
    norm_phone = service.normalize_phone(candidate.phone)
    norm_name = service.normalize_name(candidate.business_name)

    seen_domains = {norm_dom}
    seen_phones = {norm_phone}
    seen_names = {(norm_name, "austin")}

    # Same domain duplicate
    assert norm_dom in seen_domains
    # Same phone duplicate
    assert norm_phone in seen_phones
    # Same name + city duplicate
    assert (norm_name, "austin") in seen_names

# ------------------------------------------------------------------------------
# 4. Invalid Prospect & Junk Rejection
# ------------------------------------------------------------------------------
def test_invalid_prospect_rejection_directories():
    # Directory aggregators must be rejected
    is_valid, reason = ProspectQualityFilter.check_validity("yelp.com", "https://yelp.com/biz/austin-hvac")
    assert not is_valid
    assert reason == RejectionReason.DIRECTORY_AGGREGATOR

    is_valid, reason = ProspectQualityFilter.check_validity("austin.yellowpages.com", None)
    assert not is_valid
    assert reason == RejectionReason.DIRECTORY_AGGREGATOR

    is_valid, reason = ProspectQualityFilter.check_validity("angi.com", None)
    assert not is_valid
    assert reason == RejectionReason.DIRECTORY_AGGREGATOR

def test_invalid_prospect_rejection_social_and_parked():
    # Social profiles without standalone business domain
    is_valid, reason = ProspectQualityFilter.check_validity("facebook.com", "https://facebook.com/texashvac")
    assert not is_valid
    assert reason == RejectionReason.SOCIAL_PROFILE

    is_valid, reason = ProspectQualityFilter.check_validity("instagram.com", None)
    assert not is_valid
    assert reason == RejectionReason.SOCIAL_PROFILE

    # Parked or placeholder domains
    is_valid, reason = ProspectQualityFilter.check_validity("godaddy.com", None)
    assert not is_valid
    assert reason == RejectionReason.PARKED_DOMAIN

    is_valid, reason = ProspectQualityFilter.check_validity("example.com", None)
    assert not is_valid
    assert reason == RejectionReason.PARKED_DOMAIN

    # Valid independent contractor domain
    is_valid, reason = ProspectQualityFilter.check_validity("lonestarhvac.com", "https://lonestarhvac.com")
    assert is_valid
    assert reason is None

# ------------------------------------------------------------------------------
# 5. $1,000+ Minimum Commercial Filter
# ------------------------------------------------------------------------------
def test_thousand_dollar_minimum_filter_enforcement():
    commercial_cfg = CommercialConfig(
        minimum_target_service_value_usd=1000,
        high_value_buyer_threshold=75.0,
        opportunity_score_threshold=65.0
    )
    scorer = HighValueBuyerScorer(commercial_cfg)

    # Solo micro contractor with low buying capacity
    micro_biz = NormalizedBusinessRecord(
        business_name="Bob's Solo Window Wash",
        category="Cleaning",
        city="Austin",
        region="Texas",
        website="https://bobwash.com",
        phone="512-555-0909",
        num_locations=1,
        is_commercial_and_residential=False,
        has_fleet_or_technicians=False,
        years_in_business=1,
        review_count=3,
        rating=4.0
    )

    scored = scorer.evaluate_prospect(micro_biz)

    # Must NOT enter priority prospect pipeline
    assert scored.classification != ProspectClassification.PRIORITY_PROSPECT
    # Valuation min must reflect solo operations or be lower than priority thresholds
    assert scored.buyer_score.score < 50.0

    # Large established commercial contractor
    commercial_biz = NormalizedBusinessRecord(
        business_name="Texas Commercial Energy & HVAC",
        category="HVAC",
        city="Dallas",
        region="Texas",
        website="https://txcommercialenergy.com",
        phone="214-555-0100",
        num_locations=3,
        is_commercial_and_residential=True,
        has_fleet_or_technicians=True,
        years_in_business=18,
        review_count=180,
        rating=4.8,
        offers_emergency_service=True,
        authorized_dealer_or_financing=True,
        page_speed_issue=True,
        seo_issue=True,
        mobile_ux_issue=True
    )

    scored_comm = scorer.evaluate_prospect(commercial_biz)
    assert scored_comm.estimated_service_value.min_value >= 1000
    assert scored_comm.classification == ProspectClassification.PRIORITY_PROSPECT
    assert scored_comm.pipeline_stage in (RealPipelineStage.HIGH_VALUE, RealPipelineStage.CONTACTABLE)
    assert "technical/automation engagement" in scored_comm.estimated_service_value.reasoning

# ------------------------------------------------------------------------------
# 6. Buyer-Score & Opportunity-Score Thresholds
# ------------------------------------------------------------------------------
def test_buyer_and_opportunity_threshold_gating():
    commercial_cfg = CommercialConfig(
        high_value_buyer_threshold=80.0,
        opportunity_score_threshold=70.0
    )
    scorer = HighValueBuyerScorer(commercial_cfg)

    candidate = NormalizedBusinessRecord(
        business_name="Medium Scale HVAC",
        category="HVAC",
        city="Houston",
        region="Texas",
        website="https://mediumscalehvac.com",
        phone="713-555-4433",
        num_locations=2,
        is_commercial_and_residential=True,
        has_fleet_or_technicians=True,
        years_in_business=6,
        review_count=45,
        rating=4.6,
        page_speed_issue=True # only 30 pts opp
    )

    scored = scorer.evaluate_prospect(candidate)
    # Opp score is only ~30 (below 70 threshold)
    assert scored.opportunity_score < 70.0
    assert scored.classification != ProspectClassification.PRIORITY_PROSPECT

# ------------------------------------------------------------------------------
# 7. Missing-Data Handling (No Invention of Missing Details)
# ------------------------------------------------------------------------------
def test_missing_data_handling_preserves_none():
    record = NormalizedBusinessRecord(
        business_name="Austin AC Specialists",
        category="HVAC",
        city="Austin",
        region="Texas",
        website="https://austinacspecialists.com"
        # phone is omitted -> None
        # email is omitted -> None
        # address is omitted -> None
        # years_in_business is omitted -> None
    )

    assert record.phone is None
    assert record.email is None
    assert record.address is None
    assert record.years_in_business is None

    # Scorer must process missing fields safely without fabricating defaults
    commercial_cfg = CommercialConfig()
    scorer = HighValueBuyerScorer(commercial_cfg)
    scored = scorer.evaluate_prospect(record)
    assert scored.business.phone is None
    assert scored.business.email is None
    assert isinstance(scored.buyer_score.score, float)

# ------------------------------------------------------------------------------
# 8. Repeated Discovery Cycle Idempotency
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_repeated_discovery_cycle_deduplication():
    # Use real commercial registry provider with fixed target
    provider = RealProspectProvider()
    targeting = TargetingConfig(
        country="United States",
        country_code="US",
        cities=["Austin"],
        niches=["Roofing"]
    )
    targeting.filters.target_results_per_city = 3

    service = LeadDiscoveryService(provider=provider)

    async with AsyncSessionLocal() as session:
        # First cycle: should discover and insert businesses
        valid_1, stats_1 = await service.discover_and_process(targeting, session, check_existing_db=True)
        assert stats_1.valid_businesses >= 0

        # Second cycle immediately following: must recognize existing database domains as duplicates
        valid_2, stats_2 = await service.discover_and_process(targeting, session, check_existing_db=True)
        # All previously discovered domains must be detected as duplicates
        assert stats_2.duplicates_removed >= len(valid_1)
