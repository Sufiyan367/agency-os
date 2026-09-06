"""Decision Traceability Module for Client Intelligence.

Maintains an auditable, step-by-step trace of every inference, evidence item,
calculation, and pricing recommendation for each prospective client.
"""
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.client_intelligence.models import (
    BusinessProfile,
    BusinessSizeEstimate,
    ClientOffer,
    DecisionTrace,
    DetectedPainPoint,
    OperationalWasteEstimate,
    PricingRecommendation,
    ROIEstimate,
    ServiceMatch,
)


class DecisionTraceManager:
    """Constructs auditable decision snapshots recording full analytical lineage."""

    def build_trace(
        self,
        business_id: int,
        domain: str,
        profile: BusinessProfile,
        size_estimate: BusinessSizeEstimate,
        pain_points: List[DetectedPainPoint],
        waste_estimate: OperationalWasteEstimate,
        service_matches: List[ServiceMatch],
        roi_estimate: ROIEstimate,
        pricing: PricingRecommendation,
        offer: ClientOffer,
        selection_data: Dict[str, Any],
        raw_inputs: Optional[Dict[str, Any]] = None,
    ) -> DecisionTrace:
        trace_id = f"trace_{uuid.uuid4().hex[:12]}"
        
        # Aggregate all unique evidence strings
        evidence_items: List[str] = []
        for p in pain_points:
            evidence_items.extend(p.evidence)
        for m in service_matches:
            evidence_items.extend(m.evidence)
        evidence_items.extend(waste_estimate.observed_inefficiencies)
        evidence_items.extend(roi_estimate.evidence)
        evidence_items = list(dict.fromkeys(evidence_items))

        # Check if human exception is needed (e.g. if zero verified channels or suspicious indicators)
        human_exception = False
        exception_reason = None
        if profile.industry.value == "UNKNOWN":
            human_exception = True
            exception_reason = "Industry/niche could not be reliably verified from records."
        elif pricing.recommended_price_usd < 500.0:
            human_exception = True
            exception_reason = "Commercial floor violation: pricing calculated below $500."

        return DecisionTrace(
            trace_id=trace_id,
            business_id=business_id,
            domain=domain,
            timestamp=datetime.utcnow(),
            input_snapshot=raw_inputs or {},
            feature_snapshot={
                "segment": size_estimate.segment.value,
                "booking_workflow": profile.booking_workflow.value,
                "website_quality": profile.website_quality.value,
                "contact_channels": profile.contact_channels.value,
                "visible_tooling": profile.visible_tooling.value,
            },
            evidence_items=evidence_items,
            inferred_profile=profile.model_dump(mode="json"),
            pain_points_detected=[p.model_dump(mode="json") for p in pain_points],
            service_ranking=[m.model_dump(mode="json") for m in service_matches],
            roi_calculation=roi_estimate.model_dump(mode="json"),
            pricing_determination=pricing.model_dump(mode="json"),
            selection_score=selection_data.get("selection_score", 0.0),
            selection_reasons=selection_data.get("why_this_business", []),
            human_exception_required=human_exception,
            exception_reason=exception_reason,
        )
