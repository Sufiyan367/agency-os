"""Service Matcher Module for Client Intelligence.

Matches diagnosed business pain points, operational waste, and business profile
against the 10 catalog services with fit scores, contraindication checks, and evidence.
"""
from typing import Dict, Any, List, Optional
from app.client_intelligence.models import (
    BusinessProfile,
    BusinessSizeEstimate,
    BusinessSegment,
    DetectedPainPoint,
    OperationalWasteEstimate,
    PainCategory,
    ServiceMatch,
)
from app.client_intelligence.catalog import SERVICE_CATALOG, ServiceCatalogItem


# Mapping of service ID to relevant pain categories
SERVICE_PAIN_MAPPING: Dict[str, List[PainCategory]] = {
    "SERVICE_001": [PainCategory.LEAD_QUALIFICATION, PainCategory.LEAD_RESPONSE, PainCategory.WEBSITE_CONVERSION],
    "SERVICE_002": [PainCategory.CUSTOMER_SUPPORT, PainCategory.LEAD_RESPONSE],
    "SERVICE_003": [PainCategory.FOLLOW_UP, PainCategory.LEAD_RESPONSE],
    "SERVICE_004": [PainCategory.CRM_DATA_ENTRY, PainCategory.DATA_WORKFLOW_INTEGRATION],
    "SERVICE_005": [PainCategory.INVOICE_AP_PROCESSING, PainCategory.MANUAL_REPETITIVE_OPS],
    "SERVICE_006": [PainCategory.APPOINTMENT_SCHEDULING, PainCategory.LEAD_RESPONSE],
    "SERVICE_007": [PainCategory.REPORTING],
    "SERVICE_008": [PainCategory.MANUAL_REPETITIVE_OPS, PainCategory.DATA_WORKFLOW_INTEGRATION],
    "SERVICE_009": [PainCategory.KNOWLEDGE_RETRIEVAL],
    "SERVICE_010": [
        PainCategory.LEAD_RESPONSE,
        PainCategory.APPOINTMENT_SCHEDULING,
        PainCategory.FOLLOW_UP,
        PainCategory.CRM_DATA_ENTRY,
    ],
}


class ServiceMatcher:
    """Ranks and scores service catalog offerings against business intelligence."""

    def match_services(
        self,
        profile: BusinessProfile,
        size_estimate: BusinessSizeEstimate,
        pain_points: List[DetectedPainPoint],
        waste_estimate: OperationalWasteEstimate,
    ) -> List[ServiceMatch]:
        matches: List[ServiceMatch] = []
        pain_map = {p.category: p for p in pain_points}
        tooling = [t.lower() for t in (profile.visible_tooling.value if isinstance(profile.visible_tooling.value, list) else [])]
        booking_workflow = str(profile.booking_workflow.value).lower()

        for s_id, s_item in SERVICE_CATALOG.items():
            reasons: List[str] = []
            evidence: List[str] = []
            contraindicated = False

            # Check business size suitability
            if size_estimate.segment not in s_item.suitable_business_sizes:
                continue

            # Check specific contraindications
            if s_id == "SERVICE_006" and booking_workflow == "calendar_widget":
                contraindicated = True  # Already has scheduling software
            elif s_id == "SERVICE_010" and size_estimate.segment == BusinessSegment.MICRO:
                contraindicated = True  # Micro business too small for full enterprise transformation
            elif s_id == "SERVICE_005" and size_estimate.segment in (BusinessSegment.MICRO, BusinessSegment.SMALL):
                if not any(k in tooling for k in ["quickbooks", "xero", "stripe", "invoice"]):
                    contraindicated = True  # No digital billing system to automate

            if contraindicated:
                continue

            # Calculate match fit
            relevant_categories = SERVICE_PAIN_MAPPING.get(s_id, [])
            matched_pains = [pain_map[cat] for cat in relevant_categories if cat in pain_map]

            if not matched_pains and s_id != "SERVICE_010":
                continue

            base_score = 0.0
            if matched_pains:
                # Average severity of matched pain points
                avg_sev = sum(p.severity for p in matched_pains) / len(matched_pains)
                base_score = avg_sev * 0.7

                for p in matched_pains:
                    reasons.append(f"Addresses confirmed pain in '{p.category.value}' (Severity: {int(p.severity * 100)}%).")
                    evidence.extend(p.evidence[:2])

            # Special case for SERVICE_010 (Integrated System)
            if s_id == "SERVICE_010":
                if len(pain_points) >= 3 and size_estimate.segment in (BusinessSegment.SMALL, BusinessSegment.SMB, BusinessSegment.MID_MARKET):
                    base_score = 0.85
                    reasons.append(f"Multiple compounding friction points ({len(pain_points)} detected) warrant a consolidated end-to-end system.")
                    evidence.append("Comprehensive workflow transformation across lead intake, qualification, and scheduling.")
                else:
                    continue  # Only offer integrated system if multi-pain exists

            # Bonus for segment fit
            if size_estimate.segment in (BusinessSegment.SMALL, BusinessSegment.SMB):
                base_score += 0.15
            elif size_estimate.segment == BusinessSegment.MICRO and s_id in ("SERVICE_001", "SERVICE_003", "SERVICE_006"):
                base_score += 0.1

            # Bonus for high operational waste
            if waste_estimate.estimated_manual_hours_weekly_high > 10.0:
                base_score += 0.1
                reasons.append(f"Targets estimated {waste_estimate.estimated_manual_hours_weekly_low}–{waste_estimate.estimated_manual_hours_weekly_high} hours/week of manual operational waste.")

            final_fit = max(0.1, min(0.98, round(base_score, 2)))

            # Deduplicate evidence
            clean_evidence = list(dict.fromkeys(evidence))

            matches.append(
                ServiceMatch(
                    service_id=s_id,
                    service_name=s_item.name,
                    fit_score=final_fit,
                    reasons=reasons,
                    evidence=clean_evidence,
                    implementation_complexity=s_item.implementation_complexity,
                    estimated_effort_days=s_item.estimated_implementation_effort_days,
                )
            )

        # Sort by fit_score descending
        matches.sort(key=lambda m: m.fit_score, reverse=True)
        return matches
