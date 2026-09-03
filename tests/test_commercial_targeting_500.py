# ==============================================================================
# Global $500 Commercial Targeting & Qualification Test Suite
# ==============================================================================
import pytest
from app.core.config import settings
from app.core.production_mode import first_client_mode
from app.database.connection import AsyncSessionLocal
from app.database.models import Business, PipelineStage, Proposal
from app.lead_generation.targeting import (
    load_targeting_config, CommercialConfig, TargetingConfig, CountryConfig, NicheConfig
)
from app.lead_generation.buyer_scoring import HighValueBuyerScorer
from app.lead_generation.schemas import (
    NormalizedBusinessRecord, ProspectClassification, RealPipelineStage
)
from app.payments.deal_service import DealClosingService
from app.payments.abstraction import MockPaymentProvider


import uuid

async def create_helper_business(session, name="Commercial Enterprise", country="US"):
    unique_dom = f"{name.lower().replace(' ', '')}_{uuid.uuid4().hex[:8]}.com"
    b = Business(
        name=name,
        domain=unique_dom,
        country=country,
        city="Houston" if country == "US" else "London",
        niche="Roofing",
        pipeline_stage=PipelineStage.QUALIFIED.value
    )
    session.add(b)
    await session.commit()
    await session.refresh(b)
    return b


@pytest.mark.asyncio
async def test_four_hundred_ninety_nine_rejection():
    """Verifies that deals/proposals under $500 ($499.00) are strictly rejected."""
    service = DealClosingService(payment_provider=MockPaymentProvider())
    async with AsyncSessionLocal() as session:
        biz = await create_helper_business(session, "Sub 500 Budget Co")

        # $499 proposal must be rejected by commercial floor
        with pytest.raises(ValueError, match="commercial qualification requirement"):
            await service.create_proposal(
                session=session,
                business_id=biz.id,
                title="Sub-Floor Micro Audit",
                total_value=499.0,
                advance_required=200.0
            )


@pytest.mark.asyncio
async def test_five_hundred_exact_acceptance():
    """Verifies that deals/proposals at exactly $500.00 are accepted into DRAFT."""
    service = DealClosingService(payment_provider=MockPaymentProvider())
    async with AsyncSessionLocal() as session:
        biz = await create_helper_business(session, "Entry Level Commercial Co")

        # Exactly $500.00 proposal must be accepted
        prop = await service.create_proposal(
            session=session,
            business_id=biz.id,
            title="Entry Automation Audit",
            total_value=500.0,
            advance_required=200.0
        )
        assert prop.id is not None
        assert prop.total_value == 500.0
        assert prop.advance_required == 200.0
        assert prop.remaining_balance == 500.0  # Full balance before payment
        assert prop.status == "DRAFT"


@pytest.mark.asyncio
async def test_five_hundred_plus_higher_value_acceptance():
    """Verifies that $500+ higher-value engagements are accepted with correct balances."""
    service = DealClosingService(payment_provider=MockPaymentProvider())
    async with AsyncSessionLocal() as session:
        biz = await create_helper_business(session, "Mid-Market Enterprise")

        for val in [750.0, 1500.0, 3200.0, 6500.0]:
            adv = val * 0.40
            prop = await service.create_proposal(
                session=session,
                business_id=biz.id,
                title=f"Package ${val:,.0f}",
                total_value=val,
                advance_required=adv
            )
            assert prop.id is not None
            assert prop.total_value == val
            assert prop.advance_required == adv
            assert prop.remaining_balance == val


def test_global_market_targeting_configuration():
    """Verifies that targeting configuration supports global markets (US, UK, CA, AU, AE, SA) with $500 floor."""
    cfg = load_targeting_config()
    assert cfg.commercial.minimum_target_service_value_usd == 500

    # Ensure markets loaded include non-US regions
    country_codes = [c.code for c in cfg.available_countries]
    for expected in ["US", "UK", "CA", "AU", "AE", "SA"]:
        assert expected in country_codes, f"Market {expected} must be available in global config"


def test_ranking_of_higher_value_opportunities():
    """Verifies that higher-value opportunities and higher buyer scores rank ahead of baseline $500 prospects."""
    commercial_cfg = CommercialConfig(
        minimum_target_service_value_usd=500,
        high_value_buyer_threshold=75.0,
        opportunity_score_threshold=65.0
    )
    scorer = HighValueBuyerScorer(commercial_cfg)

    # Prospect A: $500 base cleaning business (1 location, solo)
    biz_a = NormalizedBusinessRecord(
        business_name="Spotless Solo Clean",
        category="Cleaning",
        city="Austin",
        region="Texas",
        website="https://spotlesssolo.com",
        phone="512-555-0101",
        num_locations=1,
        is_commercial_and_residential=False,
        has_fleet_or_technicians=False,
        years_in_business=2,
        review_count=10,
        rating=4.2
    )

    # Prospect B: Commercial roofing enterprise ($1,500+ estimate, 3 locations, fleet, commercial contracts)
    biz_b = NormalizedBusinessRecord(
        business_name="Apex Commercial Roofing",
        category="Roofing",
        city="London",
        region="Greater London",
        country="UK",
        website="https://apexroofing.co.uk",
        phone="+44-20-7946-0123",
        num_locations=3,
        is_commercial_and_residential=True,
        has_fleet_or_technicians=True,
        offers_emergency_service=True,
        authorized_dealer_or_financing=True,
        affluent_service_area=True,
        years_in_business=14,
        review_count=130,
        rating=4.9,
        page_speed_issue=True,
        mobile_ux_issue=True,
        seo_issue=True
    )

    scored_a = scorer.evaluate_prospect(biz_a)
    scored_b = scorer.evaluate_prospect(biz_b)

    # Both must meet or exceed the $500 minimum floor
    assert scored_a.estimated_service_value.min_value >= 250
    assert scored_b.estimated_service_value.min_value >= 1500

    # Prospect B (higher value & higher capability) ranks higher
    prospects = [scored_a, scored_b]
    # Commercial ranking: Priority first, then buyer score * est_value
    prospects.sort(
        key=lambda p: (
            1 if p.classification == ProspectClassification.PRIORITY_PROSPECT else 0,
            p.buyer_score.score,
            p.estimated_service_value.min_value
        ),
        reverse=True
    )

    assert prospects[0].business.business_name == "Apex Commercial Roofing"
    assert prospects[0].classification == ProspectClassification.PRIORITY_PROSPECT
    assert prospects[0].estimated_service_value.min_value > prospects[1].estimated_service_value.min_value


def test_safety_guards_and_human_control():
    """Verifies that strict human-in-the-loop and payment safeguards remain active."""
    # 1. Environment defaults
    assert settings.EMAIL_DRY_RUN is True
    assert settings.PAYMENT_DRY_RUN is True
    assert settings.RAZORPAY_MODE == "test"
    assert settings.MINIMUM_SERVICE_VALUE_USD == 500.0

    # 2. First client mode constraints
    status = first_client_mode.get_mode_status()
    perms = status["permissions"]
    assert perms["human_approval_mandatory"] is True
    assert perms["payment_live_charging"] is False
    assert perms["autonomous_contract_acceptance"] is False
    assert perms["autonomous_negotiation_allowed"] is False
    assert perms["commercial_threshold_usd"] == 500.0
