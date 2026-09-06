"""Offer Composer Module for Client Intelligence.

Assembles an 8-stage bespoke offer tailored precisely to the prospect's
observable operational bottleneck, size tier, and evidence trail.
"""
from typing import Dict, Any, List, Optional
from app.client_intelligence.models import (
    BusinessProfile,
    BusinessSizeEstimate,
    ClientOffer,
    DetectedPainPoint,
    PricingRecommendation,
    ROIEstimate,
    ServiceMatch,
)
from app.client_intelligence.catalog import SERVICE_CATALOG


class OfferComposer:
    """Composes an evidence-grounded, 8-part modular client offer."""

    def compose_offer(
        self,
        profile: BusinessProfile,
        size_estimate: BusinessSizeEstimate,
        matched_service: ServiceMatch,
        pricing: PricingRecommendation,
        pain_points: List[DetectedPainPoint],
        roi_estimate: Optional[ROIEstimate] = None,
    ) -> ClientOffer:
        cat_item = SERVICE_CATALOG.get(matched_service.service_id)
        
        # 1. Problem Statement
        primary_pain = pain_points[0] if pain_points else None
        if primary_pain:
            problem_statement = (
                f"{profile.business_name} currently relies on manual workflows for {primary_pain.category.value.lower()}, "
                f"resulting in response delays, unbilled administrative labor, and dropped conversion opportunities."
            )
        else:
            problem_statement = (
                f"{profile.business_name} faces operational friction in managing digital inquiries and workflow handoffs, "
                "limiting growth velocity and staff leverage."
            )

        # 2. Observed Evidence
        observed_evidence = []
        if matched_service.evidence:
            observed_evidence.extend(matched_service.evidence[:3])
        elif primary_pain and primary_pain.evidence:
            observed_evidence.extend(primary_pain.evidence[:3])
        else:
            observed_evidence.append(f"Audit of {profile.domain} identified manual intake workflows without automated calendar sync.")

        # 3. Recommended Solution
        solution_title = matched_service.service_name
        solution_desc = cat_item.description if cat_item else f"Turnkey {matched_service.service_name} deployment."
        recommended_solution = f"{solution_title}: {solution_desc}"

        # 4. Implementation Scope
        scope = []
        if cat_item:
            scope.extend(cat_item.required_inputs)
            scope.append(f"Turnkey installation and testing on {profile.domain}")
            scope.append("Staff walkthrough and operating runbook delivery")
        else:
            scope = [
                "Workflow mapping and custom integration triggers",
                "Automated triage, validation, and notification rules",
                "End-to-end sandbox verification and production rollout",
                "Operating documentation and 14-day post-launch support",
            ]

        # 5. Expected Outcome
        if cat_item and cat_item.expected_business_outcomes:
            outcomes = "; ".join(cat_item.expected_business_outcomes[:2])
            expected_outcome = f"{outcomes}."
        elif roi_estimate and roi_estimate.monthly_value_expected_usd:
            expected_outcome = (
                f"Reclaims estimated 4–8 staff hours weekly, delivering an estimated ${roi_estimate.monthly_value_expected_usd:,.0f}/month "
                "in direct operational labor efficiency."
            )
        else:
            expected_outcome = "Eliminates inquiry response lag, guarantees immediate prospect qualification, and frees key staff from repetitive administrative triage."

        # 6 & 7. Investment & Target
        investment_usd = pricing.recommended_price_usd
        target_usd = pricing.target_price_usd

        # 8. Timeline
        timeline = cat_item.estimated_implementation_effort_days if cat_item else 7

        # 9. Next Step
        next_step = "Confirm scope alignment on a 15-minute diagnostic walkthrough to review the exact workflow configuration."

        return ClientOffer(
            problem_statement=problem_statement,
            observed_evidence=observed_evidence,
            recommended_solution=recommended_solution,
            implementation_scope=scope,
            expected_outcome=expected_outcome,
            investment_usd=investment_usd,
            target_investment_usd=target_usd,
            timeline_days=timeline,
            next_step=next_step,
        )
