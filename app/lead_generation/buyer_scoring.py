from typing import Tuple, List
from app.lead_generation.schemas import (
    NormalizedBusinessRecord,
    HighValueBuyerScore,
    BuyerTier,
    ProspectClassification,
    ScoredProspect
)
from app.lead_generation.targeting import CommercialConfig

class HighValueBuyerScorer:
    """
    Evaluates observable business signals to compute an evidence-grounded
    High-Value Buyer Score and Opportunity Score without presenting estimates as facts.
    """

    def __init__(self, commercial_config: CommercialConfig):
        self.config = commercial_config

    def evaluate_prospect(self, business: NormalizedBusinessRecord) -> ScoredProspect:
        """Evaluates a normalized business and assigns BuyerScore, OpportunityScore, and Classification."""
        buyer_score, opp_score = self.compute_scores(business)
        has_contact = bool(business.email or business.phone or business.source_url)

        is_high_buyer = buyer_score.score >= self.config.high_value_buyer_threshold
        is_high_opp = opp_score >= self.config.opportunity_score_threshold

        if not has_contact or (business.rating and business.rating < 3.0):
            classification = ProspectClassification.DISCARD
            rationale = "Discarded: Missing legitimate contact path or severe brand reputation penalty (<3.0 rating)."
        elif is_high_buyer and is_high_opp:
            classification = ProspectClassification.PRIORITY_PROSPECT
            rationale = (
                "Strong evidence that this business is commercially suitable for a $1,000+ service, "
                "but this is an estimate and must be validated during sales."
            )
        elif is_high_buyer and not is_high_opp:
            classification = ProspectClassification.NURTURE
            rationale = "High purchasing capacity, but low immediate digital bottleneck. Nurture for seasonal/enterprise offerings."
        elif not is_high_buyer and is_high_opp:
            if buyer_score.score >= 50.0:
                classification = ProspectClassification.NURTURE
                rationale = "High technical opportunity, but moderate estimated purchasing capacity. Retain in nurture pool."
            else:
                classification = ProspectClassification.LOW_VALUE
                rationale = "High technical opportunity, but small solo operation unlikely to purchase a $1,000+ service."
        else:
            classification = ProspectClassification.LOW_VALUE
            rationale = "Low estimated purchasing capacity and low immediate technical need."

        return ScoredProspect(
            business=business,
            buyer_score=buyer_score,
            opportunity_score=opp_score,
            classification=classification,
            has_contact_path=has_contact,
            classification_rationale=rationale
        )

    def compute_scores(self, b: NormalizedBusinessRecord) -> Tuple[HighValueBuyerScore, float]:
        """Calculates HighValueBuyerScore (0-100) and OpportunityScore (0-100)."""
        buying_capacity_signals: List[str] = []
        opportunity_signals: List[str] = []
        negative_signals: List[str] = []

        # ----------------------------------------------------------------------
        # 1. BUSINESS SIZE & OPERATIONAL SCALE (Max 25 pts)
        # ----------------------------------------------------------------------
        size_score = 0.0
        if b.num_locations > 1:
            size_score += 15.0
            buying_capacity_signals.append(f"Multi-location business ({b.num_locations} physical locations observed)")
        if b.has_fleet_or_technicians:
            size_score += 10.0
            buying_capacity_signals.append("Dedicated technician fleet / dispatch infrastructure observed")
        if b.years_in_business and b.years_in_business >= 10:
            size_score += 10.0
            buying_capacity_signals.append(f"Established operation ({b.years_in_business}+ years in business)")
        elif b.years_in_business and b.years_in_business >= 5:
            size_score += 5.0
            buying_capacity_signals.append(f"Established operation ({b.years_in_business} years in business)")

        size_score = min(size_score, 25.0)

        # ----------------------------------------------------------------------
        # 2. PURCHASING CAPACITY PROXIES & SERVICE BREADTH (Max 25 pts)
        # ----------------------------------------------------------------------
        capacity_score = 0.0
        if b.is_commercial_and_residential:
            capacity_score += 12.0
            buying_capacity_signals.append("Commercial + Residential contract scope (High ticket value)")
        if b.offers_emergency_service:
            capacity_score += 8.0
            buying_capacity_signals.append("24/7 Emergency dispatch service (Indicates round-the-clock staffing)")
        if b.authorized_dealer_or_financing:
            capacity_score += 10.0
            buying_capacity_signals.append("Authorized OEM dealer / customer financing available (Wells Fargo/GreenSky)")

        capacity_score = min(capacity_score, 25.0)

        # ----------------------------------------------------------------------
        # 3. MARKET & REPUTATION AUTHORITY (Max 25 pts)
        # ----------------------------------------------------------------------
        market_score = 0.0
        reviews = b.review_count or 0
        if reviews >= 150:
            market_score += 15.0
            buying_capacity_signals.append(f"High review volume ({reviews} verified reviews - active customer base)")
        elif reviews >= 50:
            market_score += 10.0
            buying_capacity_signals.append(f"Established review volume ({reviews} verified reviews)")
        elif reviews < 15:
            negative_signals.append(f"Low review volume ({reviews} reviews - potential nascent or low-volume operation)")

        if b.affluent_service_area:
            market_score += 10.0
            buying_capacity_signals.append("Servicing prime affluent residential/commercial territories")

        market_score = min(market_score, 25.0)

        # ----------------------------------------------------------------------
        # 4. DIGITAL PRESENCE & COMMERCIAL INTENT (Max 25 pts)
        # ----------------------------------------------------------------------
        intent_score = 0.0
        if b.website:
            intent_score += 10.0
            buying_capacity_signals.append("Active domain & established online web presence")
        else:
            negative_signals.append("No active official website found")

        if b.hiring_active:
            intent_score += 15.0
            buying_capacity_signals.append("Active hiring postings for technicians/installers (Expansion signal)")

        intent_score = min(intent_score, 25.0)

        # Total High-Value Buyer Score
        total_buyer = round(size_score + capacity_score + market_score + intent_score, 1)

        # Determine Tier
        if total_buyer >= 85.0:
            tier = BuyerTier.VERY_HIGH
            budget_range = "$2,500 - $5,000+ (Estimated purchasing capacity range based on multi-location/commercial scale)"
        elif total_buyer >= 70.0:
            tier = BuyerTier.HIGH
            budget_range = "$1,000 - $2,500 (Estimated purchasing capacity range based on established fleet and review volume)"
        elif total_buyer >= 45.0:
            tier = BuyerTier.MEDIUM
            budget_range = "$500 - $1,000 (Estimated purchasing capacity range for small local operation)"
        else:
            tier = BuyerTier.LOW
            budget_range = "< $500 (Estimated limited purchasing capacity for solo/new operator)"

        reasoning = (
            f"Observed Scale: {size_score:.0f}/25 pts, Service Breadth: {capacity_score:.0f}/25 pts, "
            f"Market Authority: {market_score:.0f}/25 pts, Commercial Intent: {intent_score:.0f}/25 pts. "
            f"Total Buyer Score: {total_buyer:.1f}/100."
        )

        # ----------------------------------------------------------------------
        # 5. OPPORTUNITY SCORE (Max 100 pts)
        # ----------------------------------------------------------------------
        opp_score = 15.0 # Base minimum technical discovery opportunity
        if b.page_speed_issue:
            opp_score += 25.0
            opportunity_signals.append("Mobile page speed bottlenecks (>4.5s LCP on cellular)")
        if b.mobile_ux_issue:
            opp_score += 25.0
            opportunity_signals.append("Mobile viewport issues & overlapping touch targets")
        if b.seo_issue:
            opp_score += 20.0
            opportunity_signals.append("Missing HVAC structured schema & local meta title tags")
        if b.lacks_lead_capture:
            opp_score += 20.0
            opportunity_signals.append("No immediate mobile click-to-call or after-hours form capture")

        opp_score = min(round(opp_score, 1), 100.0)

        buyer_result = HighValueBuyerScore(
            score=total_buyer,
            tier=tier,
            estimated_service_budget=budget_range,
            buying_capacity_signals=buying_capacity_signals,
            opportunity_signals=opportunity_signals,
            negative_signals=negative_signals,
            reasoning=reasoning,
            confidence=0.88
        )

        return buyer_result, opp_score
