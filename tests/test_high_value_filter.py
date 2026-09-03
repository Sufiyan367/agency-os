import pytest
from app.lead_generation.schemas import (
    NormalizedBusinessRecord,
    ProspectClassification,
    BuyerTier,
    HighValueBuyerScore
)
from app.lead_generation.targeting import CommercialConfig
from app.lead_generation.buyer_scoring import HighValueBuyerScorer

def test_large_established_business_scores_highly():
    commercial_cfg = CommercialConfig(
        high_value_buyer_threshold=75.0,
        opportunity_score_threshold=65.0
    )
    scorer = HighValueBuyerScorer(commercial_cfg)

    large_biz = NormalizedBusinessRecord(
        business_name="Metroplex Commercial & Residential HVAC",
        category="HVAC Contractor",
        city="Dallas",
        region="Texas",
        website="https://metroplexhvac.example.com",
        phone="(214) 555-0199",
        rating=4.8,
        review_count=210,
        num_locations=3,
        years_in_business=15,
        is_commercial_and_residential=True,
        has_fleet_or_technicians=True,
        offers_emergency_service=True,
        authorized_dealer_or_financing=True,
        hiring_active=True,
        affluent_service_area=True,
        page_speed_issue=True,
        mobile_ux_issue=True,
        seo_issue=True,
        lacks_lead_capture=True
    )

    scored = scorer.evaluate_prospect(large_biz)

    # Must score above 85
    assert scored.buyer_score.score >= 85.0
    assert scored.buyer_score.tier == BuyerTier.VERY_HIGH
    assert scored.opportunity_score >= 80.0
    assert scored.classification == ProspectClassification.PRIORITY_PROSPECT
    assert "Estimated purchasing capacity range" in scored.buyer_score.estimated_service_budget
    assert len(scored.buyer_score.buying_capacity_signals) >= 4

def test_tiny_new_business_scores_low():
    commercial_cfg = CommercialConfig(
        high_value_buyer_threshold=75.0,
        opportunity_score_threshold=65.0
    )
    scorer = HighValueBuyerScorer(commercial_cfg)

    tiny_biz = NormalizedBusinessRecord(
        business_name="Joe's Solo Handyman AC",
        category="HVAC Contractor",
        city="Austin",
        region="Texas",
        website="https://joeshandyman.example.com",
        phone="(512) 555-0011",
        rating=4.2,
        review_count=4,
        num_locations=1,
        years_in_business=1,
        is_commercial_and_residential=False,
        has_fleet_or_technicians=False,
        offers_emergency_service=False,
        authorized_dealer_or_financing=False,
        hiring_active=False,
        affluent_service_area=False,
        page_speed_issue=True,
        mobile_ux_issue=True
    )

    scored = scorer.evaluate_prospect(tiny_biz)

    assert scored.buyer_score.score < 40.0
    assert scored.buyer_score.tier == BuyerTier.LOW
    assert scored.classification != ProspectClassification.PRIORITY_PROSPECT
    assert scored.classification in (ProspectClassification.LOW_VALUE, ProspectClassification.DISCARD)

def test_high_opportunity_plus_low_buying_capacity_does_not_become_priority():
    commercial_cfg = CommercialConfig(
        high_value_buyer_threshold=75.0,
        opportunity_score_threshold=65.0
    )
    scorer = HighValueBuyerScorer(commercial_cfg)

    # Broken website (100 opp score), but tiny solo operator (<40 buyer score)
    broken_site_solo_biz = NormalizedBusinessRecord(
        business_name="Struggling Solo AC Fixer",
        category="HVAC Contractor",
        city="Houston",
        region="Texas",
        website="https://brokenair.example.com",
        phone="(713) 555-0022",
        rating=3.6,
        review_count=8,
        num_locations=1,
        years_in_business=1,
        is_commercial_and_residential=False,
        has_fleet_or_technicians=False,
        offers_emergency_service=False,
        authorized_dealer_or_financing=False,
        hiring_active=False,
        affluent_service_area=False,
        page_speed_issue=True,
        mobile_ux_issue=True,
        seo_issue=True,
        lacks_lead_capture=True
    )

    scored = scorer.evaluate_prospect(broken_site_solo_biz)

    assert scored.opportunity_score >= 80.0 # High opportunity
    assert scored.buyer_score.score < 50.0  # Low purchasing capacity
    # MUST NOT be Priority Prospect
    assert scored.classification != ProspectClassification.PRIORITY_PROSPECT
    assert scored.classification in (ProspectClassification.LOW_VALUE, ProspectClassification.NURTURE)

def test_high_buying_capacity_plus_low_opportunity_does_not_become_priority():
    commercial_cfg = CommercialConfig(
        high_value_buyer_threshold=75.0,
        opportunity_score_threshold=65.0
    )
    scorer = HighValueBuyerScorer(commercial_cfg)

    # Massive company (90+ buyer score), but website is pristine (low opp score)
    established_flawless_biz = NormalizedBusinessRecord(
        business_name="Apex Elite Climate Systems",
        category="HVAC Contractor",
        city="Austin",
        region="Texas",
        website="https://apexeliteclimate.example.com",
        phone="(512) 555-9988",
        rating=4.9,
        review_count=350,
        num_locations=4,
        years_in_business=22,
        is_commercial_and_residential=True,
        has_fleet_or_technicians=True,
        offers_emergency_service=True,
        authorized_dealer_or_financing=True,
        hiring_active=True,
        affluent_service_area=True,
        page_speed_issue=False,
        mobile_ux_issue=False,
        seo_issue=False,
        lacks_lead_capture=False
    )

    scored = scorer.evaluate_prospect(established_flawless_biz)

    assert scored.buyer_score.score >= 85.0 # High buying capacity
    assert scored.opportunity_score < 40.0  # Low opportunity
    # MUST NOT be Priority Prospect; must be NURTURE
    assert scored.classification != ProspectClassification.PRIORITY_PROSPECT
    assert scored.classification == ProspectClassification.NURTURE

def test_system_never_represents_budget_as_confirmed_revenue():
    commercial_cfg = CommercialConfig()
    scorer = HighValueBuyerScorer(commercial_cfg)

    sample = NormalizedBusinessRecord(
        business_name="Texas Premier Air",
        category="HVAC Contractor",
        city="Austin",
        region="Texas",
        website="https://texaspremier.example.com",
        phone="(512) 555-4433",
        rating=4.7,
        review_count=90,
        num_locations=2,
        is_commercial_and_residential=True
    )

    scored = scorer.evaluate_prospect(sample)

    # Verify that the budget description explicitly states it is an estimate, not confirmed revenue
    budget_desc = scored.buyer_score.estimated_service_budget
    assert "Estimated" in budget_desc or "estimated" in budget_desc
    assert "confirmed revenue" not in budget_desc.lower()
    assert "guaranteed" not in budget_desc.lower()

def test_configurable_thresholds():
    strict_cfg = CommercialConfig(
        high_value_buyer_threshold=90.0, # Highly restrictive
        opportunity_score_threshold=85.0
    )
    scorer_strict = HighValueBuyerScorer(strict_cfg)

    borderline_biz = NormalizedBusinessRecord(
        business_name="Borderline Comfort",
        category="HVAC Contractor",
        city="Austin",
        region="Texas",
        website="https://borderline.example.com",
        phone="(512) 555-7766",
        rating=4.6,
        review_count=70,
        num_locations=2,
        years_in_business=7,
        is_commercial_and_residential=True,
        has_fleet_or_technicians=True,
        page_speed_issue=True,
        mobile_ux_issue=True
    )

    # Under strict thresholds (90/85), it should not make Priority
    strict_scored = scorer_strict.evaluate_prospect(borderline_biz)
    assert strict_scored.classification != ProspectClassification.PRIORITY_PROSPECT

    # Under lenient thresholds (55/50), the exact same business becomes Priority
    lenient_cfg = CommercialConfig(
        high_value_buyer_threshold=55.0,
        opportunity_score_threshold=50.0
    )
    scorer_lenient = HighValueBuyerScorer(lenient_cfg)
    lenient_scored = scorer_lenient.evaluate_prospect(borderline_biz)
    assert lenient_scored.classification == ProspectClassification.PRIORITY_PROSPECT
