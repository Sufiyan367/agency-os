"""Operational Waste Detector Module for Client Intelligence.

Estimates unbilled labor hours lost to manual workflows and computes
an automation opportunity score grounded in detected friction points.
"""
from typing import Dict, Any, List, Optional
from app.client_intelligence.models import (
    BusinessProfile,
    BusinessSizeEstimate,
    BusinessSegment,
    DetectedPainPoint,
    OperationalWasteEstimate,
    PainCategory,
)


class OperationalWasteDetector:
    """Calculates weekly operational waste and automation potential."""

    def estimate_waste(
        self,
        profile: BusinessProfile,
        size_estimate: BusinessSizeEstimate,
        pain_points: List[DetectedPainPoint],
    ) -> OperationalWasteEstimate:
        low_hours = 0.0
        high_hours = 0.0
        inefficiencies: List[str] = []

        categories = {p.category for p in pain_points}

        # Hours impact per category
        if PainCategory.APPOINTMENT_SCHEDULING in categories:
            low_hours += 2.5
            high_hours += 5.0
            inefficiencies.append("Manual back-and-forth scheduling coordination: ~2.5–5.0 hrs/week")

        if PainCategory.LEAD_RESPONSE in categories:
            low_hours += 2.0
            high_hours += 4.5
            inefficiencies.append("Ad-hoc manual email intake and initial screening: ~2.0–4.5 hrs/week")

        if PainCategory.LEAD_QUALIFICATION in categories:
            low_hours += 1.5
            high_hours += 3.5
            inefficiencies.append("Filtering unqualified submissions and spam: ~1.5–3.5 hrs/week")

        if PainCategory.CRM_DATA_ENTRY in categories:
            low_hours += 2.0
            high_hours += 4.0
            inefficiencies.append("Manual lead and contact transcription into spreadsheets/inbox: ~2.0–4.0 hrs/week")

        if PainCategory.FOLLOW_UP in categories:
            low_hours += 1.5
            high_hours += 3.0
            inefficiencies.append("Tracking and sending manual prospect reminder emails: ~1.5–3.0 hrs/week")

        if PainCategory.CUSTOMER_SUPPORT in categories:
            low_hours += 1.0
            high_hours += 3.0
            inefficiencies.append("Repeated answers to basic repetitive inquiries: ~1.0–3.0 hrs/week")

        # Scale by business segment
        multiplier = 1.0
        if size_estimate.segment == BusinessSegment.MICRO:
            multiplier = 0.8
        elif size_estimate.segment == BusinessSegment.SMALL:
            multiplier = 1.0
        elif size_estimate.segment == BusinessSegment.SMB:
            multiplier = 1.6
        elif size_estimate.segment == BusinessSegment.MID_MARKET:
            multiplier = 2.4
        elif size_estimate.segment == BusinessSegment.ENTERPRISE:
            multiplier = 3.5

        final_low = round(low_hours * multiplier, 1)
        final_high = round(high_hours * multiplier, 1)

        # Compute automation opportunity score (0 - 100)
        # Baseline 40 + severity-weighted sum of pain points + hours factor
        severity_sum = sum(p.severity for p in pain_points)
        raw_score = 30.0 + (severity_sum * 10.0) + (final_high * 1.5)
        score = max(10.0, min(95.0, round(raw_score, 1)))

        # Confidence based on evidence backing
        conf = 0.75 if len(pain_points) >= 3 else 0.6

        return OperationalWasteEstimate(
            estimated_manual_hours_weekly_low=final_low,
            estimated_manual_hours_weekly_high=final_high,
            automation_opportunity_score=score,
            confidence=conf,
            observed_inefficiencies=inefficiencies,
        )
