from typing import Tuple, List, Optional
from app.lead_generation.schemas import (
    NormalizedBusinessRecord,
    HighValueBuyerScore,
    BuyerTier,
    ProspectClassification,
    ScoredProspect,
    EstimatedServiceValue,
    RealPipelineStage
)
from app.lead_generation.targeting import CommercialConfig

class HighValueBuyerScorer:
    """
    Evaluates observable business signals to compute an evidence-grounded
    High-Value Buyer Score and Opportunity Score, estimates explainable service value,
    and applies the strict $500+ commercial qualification filter.
    """

    def __init__(self, commercial_config: CommercialConfig):
        self.config = commercial_config

    def estimate_service_value(
        self,
        business: NormalizedBusinessRecord,
        buyer_score: float,
        opp_score: float
    ) -> EstimatedServiceValue:
        """
        Computes an explainable estimated service value (min/max range + rationale)
        grounded in business category, operational indicators, and digital gaps.
        """
        cat_lower = business.category.lower()
        base_min = 500
        base_max = 2000

        # Category-based base tier
        if any(k in cat_lower for k in ["solar", "renewable"]):
            base_min, base_max = 2000, 6000
        elif any(k in cat_lower for k in ["roofing", "commercial roof"]):
            base_min, base_max = 1500, 4500
        elif any(k in cat_lower for k in ["hvac", "heating", "cooling", "mechanical"]):
            base_min, base_max = 1200, 3500
        elif any(k in cat_lower for k in ["plumb"]):
            base_min, base_max = 750, 2500
        elif any(k in cat_lower for k in ["dental"]):
            base_min, base_max = 1000, 3000
        elif any(k in cat_lower for k in ["cleaning", "janitorial"]):
            base_min, base_max = 500, 2000

        # Observable scale adjustments
        if business.num_locations > 1:
            base_min += 500 * (business.num_locations - 1)
            base_max += 1000 * (business.num_locations - 1)
        if business.is_commercial_and_residential:
            base_min += 300
            base_max += 800
        if business.has_fleet_or_technicians:
            base_min += 200
            base_max += 500

        # Adjust for very small or solo operators
        if buyer_score < 40.0:
            base_min = max(250, base_min - 400)
            base_max = max(500, base_max - 800)

        reasoning = (
            f"Business category '{business.category}' in {business.city}, {business.country} "
            f"with detected operational characteristics (locations: {business.num_locations}, "
            f"commercial contracts: {business.is_commercial_and_residential}, "
            f"technician fleet: {business.has_fleet_or_technicians}) "
            f"supports an estimated ${base_min:,} - ${base_max:,} technical/automation engagement."
        )

        return EstimatedServiceValue(
            min_value=base_min,
            max_value=base_max,
            currency="USD",
            reasoning=reasoning
        )

    def evaluate_prospect(self, business: NormalizedBusinessRecord) -> ScoredProspect:
        """Evaluates a normalized business and assigns BuyerScore, OpportunityScore, and Classification."""
        buyer_score, opp_score = self.compute_scores(business)
        has_contact = bool(business.email or business.phone or business.source_url)
        est_val = self.estimate_service_value(business, buyer_score.score, opp_score)
        buyer_score.estimated_service_value = est_val

        is_high_buyer = buyer_score.score >= self.config.high_value_buyer_threshold
        is_high_opp = opp_score >= self.config.opportunity_score_threshold
        meets_commercial_val = est_val.min_value >= self.config.minimum_target_service_value_usd

        # Default stage progression
        p_stage = RealPipelineStage.AUDITED

        if not has_contact or (business.rating and business.rating < 3.0):
            classification = ProspectClassification.DISCARD
            rationale = "Discarded: Missing legitimate contact path or severe brand reputation penalty (<3.0 rating)."
            p_stage = RealPipelineStage.DISCOVERED
        elif not meets_commercial_val:
            classification = ProspectClassification.LOW_VALUE
            rationale = (
                f"Rejected from commercial pipeline: small solo operation unlikely to purchase a "
                f"${self.config.minimum_target_service_value_usd}+ service "
                f"(estimated service value ${est_val.min_value:,} is below the ${self.config.minimum_target_service_value_usd}+ commercial floor)."
            )
            p_stage = RealPipelineStage.AUDITED
        elif is_high_buyer and is_high_opp:
            classification = ProspectClassification.PRIORITY_PROSPECT
            rationale = (
                f"Strong evidence that this business is commercially suitable for a ${est_val.min_value:,}+ service "
                f"(${est_val.min_value:,} - ${est_val.max_value:,} estimated range), "
                "supported by observed multi-location / fleet signals and technical bottlenecks."
            )
            p_stage = RealPipelineStage.HIGH_VALUE
            if has_contact:
                p_stage = RealPipelineStage.CONTACTABLE
        elif is_high_buyer and not is_high_opp:
            classification = ProspectClassification.NURTURE
            rationale = "High purchasing capacity, but low immediate digital bottleneck. Nurture for seasonal/enterprise offerings."
            p_stage = RealPipelineStage.HIGH_VALUE
        elif not is_high_buyer and is_high_opp:
            if buyer_score.score >= 50.0:
                classification = ProspectClassification.NURTURE
                rationale = "High technical opportunity, but moderate estimated purchasing capacity. Retain in nurture pool."
                p_stage = RealPipelineStage.QUALIFIED
            else:
                classification = ProspectClassification.LOW_VALUE
                rationale = f"High technical opportunity, but small solo operation unlikely to purchase a ${self.config.minimum_target_service_value_usd}+ service."
                p_stage = RealPipelineStage.AUDITED
        else:
            classification = ProspectClassification.LOW_VALUE
            rationale = "Low estimated purchasing capacity and low immediate technical need."
            p_stage = RealPipelineStage.AUDITED

        return ScoredProspect(
            business=business,
            buyer_score=buyer_score,
            opportunity_score=opp_score,
            estimated_service_value=est_val,
            classification=classification,
            pipeline_stage=p_stage,
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
            buying_capacity_signals.append("Offers commercial contracts alongside residential services")
        if b.offers_emergency_service:
            capacity_score += 8.0
            buying_capacity_signals.append("Operates 24/7 or priority emergency dispatch")
        if b.authorized_dealer_or_financing:
            capacity_score += 10.0
            buying_capacity_signals.append("Authorized equipment dealer / offers consumer financing partnerships")

        capacity_score = min(capacity_score, 25.0)

        # ----------------------------------------------------------------------
        # 3. MARKET CHARACTERISTICS & POSITIONING (Max 25 pts)
        # ----------------------------------------------------------------------
        market_score = 0.0
        if b.hiring_active:
            market_score += 10.0
            buying_capacity_signals.append("Active recruitment/hiring indicators observed")
        if b.affluent_service_area:
            market_score += 8.0
            buying_capacity_signals.append("Servicing affluent / high average-ticket markets")
        if b.review_count and b.review_count >= 100:
            market_score += 10.0
            buying_capacity_signals.append(f"High customer transaction volume ({b.review_count}+ verified reviews)")
        elif b.review_count and b.review_count >= 30:
            market_score += 5.0
            buying_capacity_signals.append(f"Moderate transaction volume ({b.review_count} verified reviews)")

        market_score = min(market_score, 25.0)

        # ----------------------------------------------------------------------
        # 4. DIGITAL PRESENCE & COMMERCIAL READINESS (Max 25 pts)
        # ----------------------------------------------------------------------
        digital_score = 0.0
        if b.website:
            digital_score += 10.0
            buying_capacity_signals.append("Active standalone corporate web domain")
        if b.rating and b.rating >= 4.5:
            digital_score += 10.0
            buying_capacity_signals.append(f"Strong customer satisfaction rating ({b.rating}/5.0)")
        elif b.rating and b.rating >= 4.0:
            digital_score += 5.0

        if b.phone and b.email:
            digital_score += 5.0
            buying_capacity_signals.append("Multi-channel contact accessibility verified")

        digital_score = min(digital_score, 25.0)

        # ----------------------------------------------------------------------
        # 5. NEGATIVE SIGNALS DEDUCTION
        # ----------------------------------------------------------------------
        deductions = 0.0
        if b.num_locations == 1 and not b.has_fleet_or_technicians and not b.is_commercial_and_residential:
            deductions += 20.0
            negative_signals.append("Indicators suggest solo/single-van technician operation")
        if b.review_count is not None and b.review_count < 10:
            deductions += 15.0
            negative_signals.append(f"Very low review volume ({b.review_count} reviews)")
        if b.years_in_business is not None and b.years_in_business < 2:
            deductions += 10.0
            negative_signals.append(f"New business ({b.years_in_business} year in operation)")

        raw_buyer_score = (size_score + capacity_score + market_score + digital_score) - deductions
        final_buyer_score = max(0.0, min(100.0, round(raw_buyer_score, 1)))

        # Assign Tier
        if final_buyer_score >= 80.0:
            tier = BuyerTier.VERY_HIGH
            budget_range = "Estimated purchasing capacity range: $3,000 - $8,000+ (High-Scale Operation)"
        elif final_buyer_score >= 65.0:
            tier = BuyerTier.HIGH
            budget_range = "Estimated purchasing capacity range: $1,500 - $3,500 (Established Local Business)"
        elif final_buyer_score >= 45.0:
            tier = BuyerTier.MEDIUM
            budget_range = "Estimated purchasing capacity range: $800 - $1,500 (Moderate Capacity)"
        else:
            tier = BuyerTier.LOW
            budget_range = "Estimated purchasing capacity range: <$800 (Micro / Solo Operation)"

        # Transparent reasoning formulation
        reasoning = (
            f"Buyer Score computed at {final_buyer_score}/100 based on observable proxies: "
            f"Scale ({size_score:.0f}/25), Purchasing Capacity ({capacity_score:.0f}/25), "
            f"Market Volume ({market_score:.0f}/25), Digital Presence ({digital_score:.0f}/25). "
            f"Deductions: -{deductions:.0f} pts for solo/small operation signals. "
            f"This represents an observable indicator of scale, NOT a confirmed financial budget."
        )

        buyer_score_obj = HighValueBuyerScore(
            score=final_buyer_score,
            tier=tier,
            estimated_service_budget=budget_range,
            buying_capacity_signals=buying_capacity_signals,
            negative_signals=negative_signals,
            reasoning=reasoning,
            confidence=0.85
        )

        # ----------------------------------------------------------------------
        # 6. OPPORTUNITY SCORE COMPUTATION (Max 100 pts)
        # ----------------------------------------------------------------------
        opp_score = 0.0
        if b.page_speed_issue:
            opp_score += 30.0
            opportunity_signals.append("Core Web Vitals bottleneck (>4.0s mobile LCP)")
        if b.mobile_ux_issue:
            opp_score += 25.0
            opportunity_signals.append("Mobile layout or viewport rendering deficiencies")
        if b.seo_issue:
            opp_score += 25.0
            opportunity_signals.append("Missing LocalBusiness JSON-LD schema / meta tags")
        if b.lacks_lead_capture:
            opp_score += 20.0
            opportunity_signals.append("No prominent mobile click-to-call or booking capture")

        final_opp_score = max(0.0, min(100.0, round(opp_score, 1)))
        buyer_score_obj.opportunity_signals = opportunity_signals

        return buyer_score_obj, final_opp_score
