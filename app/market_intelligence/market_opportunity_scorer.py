from typing import Dict, Any, Tuple
from app.client_intelligence.catalog import SERVICE_CATALOG
from app.market_intelligence.config import SCORING_WEIGHTS, PENALTY_WEIGHTS

class MarketOpportunityScorer:
    """Calculates transparent market opportunity scores, expected deal values, and EV."""

    def calculate_opportunity(
        self,
        signals: Dict[str, Any],
        niche_meta: Dict[str, Any],
        country_meta: Dict[str, Any],
        service_id: str,
        compliance_risk_penalty: float = 0.05
    ) -> Dict[str, Any]:
        def _get_val(sig_name: str, fallback: float = 0.5) -> float:
            sig = signals.get(sig_name)
            if sig and getattr(sig, "value", None) is not None:
                return float(sig.value)
            return fallback

        # 1. Component scores (0.0 to 1.0)
        atp = _get_val("ABILITY_TO_PAY", niche_meta.get("atp", 0.8))
        demand = _get_val("SERVICE_DEMAND", 0.75)
        automation = niche_meta.get("automation", 0.80)
        ai_adoption = _get_val("AI_ADOPTION", 0.70)
        digital_mat = _get_val("DIGITAL_MATURITY", 0.75)
        biz_density = _get_val("BUSINESS_DENSITY", 0.70)
        pain_prob = niche_meta.get("pain", 0.80)
        growth = _get_val("MARKET_GROWTH", 0.70)
        contactability = _get_val("CONTACTABILITY", 0.80)

        # 2. Weighted positive sum
        positive_factors = (
            atp * SCORING_WEIGHTS["ability_to_pay"] +
            demand * SCORING_WEIGHTS["service_demand"] +
            automation * SCORING_WEIGHTS["automation_potential"] +
            ai_adoption * SCORING_WEIGHTS["ai_adoption"] +
            digital_mat * SCORING_WEIGHTS["digital_maturity"] +
            biz_density * SCORING_WEIGHTS["business_density"] +
            pain_prob * SCORING_WEIGHTS["pain_probability"] +
            growth * SCORING_WEIGHTS["market_growth"] +
            contactability * SCORING_WEIGHTS["contactability"]
        )

        # 3. Penalties
        competition = _get_val("COMPETITION", 0.35)
        competition_penalty = competition * PENALTY_WEIGHTS["competition_penalty"]
        compliance_penalty = compliance_risk_penalty * PENALTY_WEIGHTS["compliance_penalty"]

        # Uncertainty penalty if key signals are missing
        missing_count = sum(1 for s in ["AI_ADOPTION", "SERVICE_DEMAND", "ABILITY_TO_PAY"] if signals.get(s) and signals[s].value is None)
        uncertainty_penalty = (missing_count * 0.05) * PENALTY_WEIGHTS["uncertainty_penalty"]

        total_penalty = competition_penalty + compliance_penalty + uncertainty_penalty

        raw_score = (positive_factors - total_penalty) * 100.0
        market_score = round(max(10.0, min(100.0, raw_score)), 1)

        # 4. Target Service Pricing from Phase 7 catalog ($1,000+ target)
        catalog_item = SERVICE_CATALOG.get(service_id)
        if catalog_item:
            deal_val = max(1000.0, catalog_item.recommended_target_price_usd)
        else:
            deal_val = 1000.0

        # Adjust deal value based on country ability to pay (e.g., US/UAE can sustain premium packages)
        atp_multiplier = max(0.8, min(1.3, atp / 0.75))
        final_deal_val = round(deal_val * atp_multiplier, 2)

        # 5. Probabilities
        p_contact = round(max(0.4, min(0.95, contactability)), 2)
        p_fit = round(max(0.5, min(0.95, (automation + pain_prob) / 2)), 2)
        p_deal = round(max(0.1, min(0.4, (atp + demand) / 5)), 2)

        # 6. Expected Value Calculation
        market_multiplier = market_score / 50.0  # 1.0 at 50 score, 1.8 at 90 score
        raw_ev = p_contact * p_fit * p_deal * final_deal_val * market_multiplier

        # Confidence from signals
        known_conf = [s.confidence for s in signals.values() if hasattr(s, "confidence")]
        avg_confidence = round(sum(known_conf) / max(1, len(known_conf)), 2) if known_conf else 0.75

        expected_value_usd = round(raw_ev * avg_confidence, 2)

        return {
            "market_score": market_score,
            "demand_score": round(demand * 100, 1),
            "ability_to_pay_score": round(atp * 100, 1),
            "automation_score": round(automation * 100, 1),
            "ai_adoption_score": round(ai_adoption * 100, 1),
            "digital_maturity_score": round(digital_mat * 100, 1),
            "business_density_score": round(biz_density * 100, 1),
            "pain_probability_score": round(pain_prob * 100, 1),
            "growth_score": round(growth * 100, 1),
            "contactability_score": round(contactability * 100, 1),
            "competition_penalty": round(competition_penalty * 100, 2),
            "compliance_penalty": round(compliance_penalty * 100, 2),
            "uncertainty_penalty": round(uncertainty_penalty * 100, 2),
            "expected_deal_value_usd": final_deal_val,
            "p_contact": p_contact,
            "p_fit": p_fit,
            "p_deal": p_deal,
            "expected_value_usd": expected_value_usd,
            "confidence": avg_confidence,
            "scoring_weights": SCORING_WEIGHTS
        }

market_opportunity_scorer = MarketOpportunityScorer()
