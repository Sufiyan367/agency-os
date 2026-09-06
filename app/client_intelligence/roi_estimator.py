"""ROI Estimator Module for Client Intelligence.

Calculates bounded, evidence-grounded ROI ranges based on labor time recovery
and conversion preservation, or explicitly reports INSUFFICIENT_DATA if ungrounded.
"""
from typing import Dict, Any, List, Optional
from app.client_intelligence.models import (
    BusinessProfile,
    BusinessSizeEstimate,
    BusinessSegment,
    OperationalWasteEstimate,
    ROIEstimate,
    ServiceMatch,
)


class ROIEstimator:
    """Computes conservative, bounded return-on-investment ranges for recommendations."""

    def estimate_roi(
        self,
        profile: BusinessProfile,
        size_estimate: BusinessSizeEstimate,
        waste_estimate: OperationalWasteEstimate,
        matched_service: Optional[ServiceMatch] = None,
    ) -> ROIEstimate:
        # Check sufficiency of data
        low_hours = waste_estimate.estimated_manual_hours_weekly_low
        high_hours = waste_estimate.estimated_manual_hours_weekly_high

        if high_hours <= 0.0 or not matched_service:
            return ROIEstimate(
                status="INSUFFICIENT_DATA",
                confidence=0.2,
                assumptions=["Insufficient observable workflow telemetry to ground an empirical ROI projection."],
                evidence=["No verifiable manual hours or service match provided."],
            )

        # Conservative hourly cost benchmarks by business segment
        hourly_rates = {
            BusinessSegment.MICRO: 35.0,
            BusinessSegment.SMALL: 45.0,
            BusinessSegment.SMB: 60.0,
            BusinessSegment.MID_MARKET: 85.0,
            BusinessSegment.ENTERPRISE: 110.0,
        }
        rate = hourly_rates.get(size_estimate.segment, 45.0)

        # Expected percentage of manual hours reclaimed by this automation
        # Most targeted single automations recover 50-75% of related manual friction
        recovery_pct_low = 0.45
        recovery_pct_expected = 0.65
        recovery_pct_high = 0.85

        reclaimed_hrs_low = low_hours * recovery_pct_low
        reclaimed_hrs_expected = ((low_hours + high_hours) / 2.0) * recovery_pct_expected
        reclaimed_hrs_high = high_hours * recovery_pct_high

        weeks_per_month = 4.33
        monthly_time_val_low = round(reclaimed_hrs_low * weeks_per_month * rate, 2)
        monthly_time_val_exp = round(reclaimed_hrs_expected * weeks_per_month * rate, 2)
        monthly_time_val_high = round(reclaimed_hrs_high * weeks_per_month * rate, 2)

        annual_time_val_exp = round(monthly_time_val_exp * 12.0, 2)

        assumptions = [
            f"Assumes conservative blended internal labor cost of ${rate:.0f}/hour for {size_estimate.segment.value} tier.",
            f"Projects recovering {int(recovery_pct_expected * 100)}% of the {low_hours}–{high_hours} observed weekly manual hours.",
            "Excludes speculative conversion upside or new revenue multiples to remain grounded strictly in operational savings.",
        ]

        evidence = list(waste_estimate.observed_inefficiencies[:3])
        evidence.append(f"Targeting automation scope defined by {matched_service.service_name}.")

        return ROIEstimate(
            status="ESTIMATED",
            monthly_value_low_usd=monthly_time_val_low,
            monthly_value_expected_usd=monthly_time_val_exp,
            monthly_value_high_usd=monthly_time_val_high,
            annual_value_expected_usd=annual_time_val_exp,
            confidence=0.75,
            assumptions=assumptions,
            evidence=evidence,
        )
