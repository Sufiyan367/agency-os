"""Prospect Selector Module for Client Intelligence.

Ranks prospective accounts using expected value math:
    Score = P(Win) * Expected Value
and produces transparent, empirical "WHY THIS BUSINESS?" justifications.
"""
from typing import Dict, Any, List, Optional
from app.client_intelligence.models import (
    BusinessProfile,
    BusinessSizeEstimate,
    BusinessSegment,
    ClientOffer,
    DetectedPainPoint,
    PricingRecommendation,
    ROIEstimate,
    ServiceMatch,
)


class ProspectSelector:
    """Calculates win probability, expected value ranking, and prioritization rationale."""

    def evaluate_prospect(
        self,
        profile: BusinessProfile,
        size_estimate: BusinessSizeEstimate,
        top_match: ServiceMatch,
        pricing: PricingRecommendation,
        pain_points: List[DetectedPainPoint],
        roi_estimate: Optional[ROIEstimate] = None,
    ) -> Dict[str, Any]:
        # 1. Compute P(Win)
        # Factor A: Service fit score (40%)
        p_fit = top_match.fit_score

        # Factor B: Pain point urgency & count (25%)
        avg_severity = sum(p.severity for p in pain_points) / len(pain_points) if pain_points else 0.4
        p_pain = avg_severity

        # Factor C: Segment sweet spot (20%)
        # Small and SMB have the highest close rates for automated agency services
        segment_weights = {
            BusinessSegment.MICRO: 0.6,
            BusinessSegment.SMALL: 0.85,
            BusinessSegment.SMB: 0.9,
            BusinessSegment.MID_MARKET: 0.7,
            BusinessSegment.ENTERPRISE: 0.4,
        }
        p_segment = segment_weights.get(size_estimate.segment, 0.7)

        # Factor D: Data completeness & contact channel (15%)
        channels = profile.contact_channels.value if isinstance(profile.contact_channels.value, list) else []
        has_email = any("email" in c for c in channels)
        p_channel = 0.85 if has_email else 0.5

        # Weighted combination of P(Win)
        p_win = (p_fit * 0.40) + (p_pain * 0.25) + (p_segment * 0.20) + (p_channel * 0.15)
        p_win = max(0.05, min(0.95, round(p_win, 3)))

        # 2. Expected Value
        expected_deal_value = pricing.recommended_price_usd
        selection_score = round(p_win * expected_deal_value, 2)

        # 3. Formulate "WHY THIS BUSINESS?" Explanation
        why_bullets = []
        if pain_points:
            sharpest = pain_points[0]
            why_bullets.append(
                f"Definitive operational bottleneck in {sharpest.category.value}: {sharpest.estimated_business_impact}"
            )
        else:
            why_bullets.append(
                "Unoptimized web presence with manual inquiry handling requiring systematic workflow triage."
            )
        why_bullets.append(
            f"Strong alignment with {top_match.service_name} (Fit Score: {int(top_match.fit_score * 100)}%), addressing manual workflows directly."
        )
        if roi_estimate and roi_estimate.monthly_value_expected_usd:
            why_bullets.append(
                f"Compelling economics: Projects ${roi_estimate.monthly_value_expected_usd:,.0f}/mo recoverable value against a ${pricing.recommended_price_usd:,.0f} turnkey deployment."
            )
        why_bullets.append(
            f"Favorable buyer profile: {size_estimate.segment.value.upper()} organization ({size_estimate.estimated_employee_range} staff) with high decision-maker accessibility."
        )

        return {
            "p_win": p_win,
            "expected_value_usd": expected_deal_value,
            "selection_score": selection_score,
            "why_this_business": why_bullets,
        }
