from typing import Dict, Any, Optional
from app.ml.policy_engine import policy_engine
from app.core.logging import logger

class ExpectedRevenueModel:
    """
    Formulates commercial Expected Value (EV) and deal viability:
    expected_revenue = probability_of_conversion * predicted_deal_value
    Enforces non-negotiable $500.00 price floor and returns confidence & uncertainty metadata.
    """

    ESTIMATED_GROSS_MARGIN: float = 0.75  # Turnaround service gross margin (75%)
    COMMERCIAL_FLOOR_USD: float = 500.0

    def evaluate_deal_potential(
        self,
        probability_win: float,
        proposed_price_usd: float,
        niche_avg_deal_size: float = 750.0,
        data_source: str = "BASELINE"
    ) -> Dict[str, Any]:
        """
        Computes expected commercial revenue, uncertainty metadata, and risk-adjusted return.
        Never recommends an offer below the $500 commercial floor.
        """
        floor = policy_engine.get_commercial_floor() if policy_engine else self.COMMERCIAL_FLOOR_USD
        
        # Bounded probability in [0.0, 1.0]
        p_win = min(1.0, max(0.0, float(probability_win)))

        # Floor compliance
        is_floor_clamped = proposed_price_usd < floor
        clamped_price = max(proposed_price_usd, floor)
        # Minimum recommended price is NEVER below the commercial floor
        recommended_price = max(proposed_price_usd, floor, 500.0)

        # Expected Value Calculations
        expected_revenue = round(p_win * clamped_price, 2)
        expected_profit = round(expected_revenue * self.ESTIMATED_GROSS_MARGIN, 2)

        # Commercial Return on Effort (ROE) index (0-100 scale)
        benchmark_ev = 0.50 * max(niche_avg_deal_size, floor)
        roe_index = round(min(100.0, (expected_revenue / benchmark_ev) * 50.0), 1)

        # Confidence & Uncertainty Metadata
        # Baseline/cold-start has bounded confidence; trained model has higher confidence if calibrated
        if data_source == "COLD_START":
            confidence_score = 0.60
            is_uncertain = True
            uncertainty_reason = "Insufficient historical training data; falling back to deterministic baseline bounds."
        elif data_source == "BASELINE":
            confidence_score = 0.80
            is_uncertain = False
            uncertainty_reason = "Deterministic domain rules with calibrated sigmoid probability."
        elif data_source == "TRAINED_MODEL":
            # Confidence decreases as probability approaches 0.5 (maximum entropy)
            entropy_penalty = 1.0 - abs(p_win - 0.5) * 2.0  # 1.0 at 0.5, 0.0 at 0 or 1
            confidence_score = round(max(0.65, 0.95 - (entropy_penalty * 0.20)), 2)
            is_uncertain = entropy_penalty > 0.6
            uncertainty_reason = "Statistically trained scikit-learn pipeline inference."
        else:
            confidence_score = 0.70
            is_uncertain = True
            uncertainty_reason = f"Unknown model source: {data_source}."

        # Commercial Priority Tier & Recommendations
        if is_floor_clamped:
            tier = "DISQUALIFIED_BELOW_FLOOR"
            recommendation = (
                f"Proposed price (${proposed_price_usd:.0f}) violates the ${floor:.0f} commercial floor. "
                f"Repackaged to minimum viable service value of ${recommended_price:.0f}."
            )
        elif expected_revenue >= 450.0 or roe_index >= 75.0:
            tier = "TIER_1_HIGH_VALUE"
            recommendation = "High expected yield. Prioritize personalized direct multi-channel outreach immediately."
        elif expected_revenue >= 250.0 or roe_index >= 50.0:
            tier = "TIER_2_STANDARD"
            recommendation = "Standard commercial potential. Queue for automated value-first sequence."
        else:
            tier = "TIER_3_MARGINAL"
            recommendation = "Marginal expected return. Send low-touch automated diagnostic observation."

        return {
            "proposed_price_usd": proposed_price_usd,
            "commercial_price_usd": clamped_price,
            "recommended_price_usd": recommended_price,
            "probability_win": round(p_win, 3),
            "expected_revenue_usd": expected_revenue,
            "expected_profit_usd": expected_profit,
            "gross_margin_rate": self.ESTIMATED_GROSS_MARGIN,
            "roe_index": roe_index,
            "commercial_tier": tier,
            "recommendation": recommendation,
            "meets_commercial_floor": not is_floor_clamped,
            "confidence_metadata": {
                "confidence_score": confidence_score,
                "is_uncertain": is_uncertain,
                "data_source": data_source,
                "uncertainty_reason": uncertainty_reason
            }
        }

expected_revenue_model = ExpectedRevenueModel()
