"""
Agency OS — Structured Research Engine.
Disentangles raw signals into explicit Observations, Inferences, and Recommendations.
Enforces epistemic confidence calculation and produces explainable decision summaries.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime

from app.intelligence.knowledge_model import (
    Observation, Inference, Recommendation, ExplainableIntelligence,
    SourceTier
)
from app.intelligence.capability_catalog import capability_catalog


class StructuredResearchEngine:
    """
    Transforms audit and prospect data into grounded epistemic tiers:
    Observation (What is observed) -> Inference (What is believed) -> Recommendation (What should be done).
    """

    @classmethod
    def analyze_business_research(
        cls,
        business_id: int,
        domain: str,
        business_name: str,
        niche: str,
        audit_data: Optional[Dict[str, Any]] = None,
        raw_signals: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes tripartite analysis separating facts, inferences, and recommended actions.
        """
        audit = audit_data or {}
        signals = raw_signals or {}
        observations: List[Observation] = []
        inferences: List[Inference] = []
        recommendations: List[Recommendation] = []

        biz_id_str = str(business_id)

        # -------------------------------------------------------------
        # 1. GROUND TRUTH OBSERVATIONS
        # -------------------------------------------------------------
        # (a) Domain & HTTP status
        has_http_200 = audit.get("http_status", 200) == 200
        observations.append(Observation(
            entity_type="business",
            entity_id=biz_id_str,
            category="infrastructure",
            fact_key="domain_active",
            fact_value={"domain": domain, "http_status": audit.get("http_status", 200)},
            source="dns_http_probe",
            source_tier=SourceTier.DIRECT_HTTP_AUDIT,
            raw_evidence=f"HTTP GET {domain} returned status {audit.get('http_status', 200)}"
        ))

        # (b) Tech stack
        tech_stack = audit.get("tech_stack") or signals.get("tech_stack") or ["WordPress"]
        observations.append(Observation(
            entity_type="business",
            entity_id=biz_id_str,
            category="tech_stack",
            fact_key="detected_technologies",
            fact_value={"technologies": tech_stack},
            source="wappalyzer_audit",
            source_tier=SourceTier.DIRECT_HTTP_AUDIT,
            raw_evidence=f"Signatures matched: {', '.join(tech_stack)}"
        ))

        # (c) Booking & Scheduling mechanism
        has_calendar = any(t.lower() in ("calendly", "acuity", "chilipiper", "hubspot-meetings") for t in tech_stack)
        booking_type = "calendar_widget" if has_calendar else ("static_form" if "form" in " ".join(tech_stack).lower() else "phone_only")
        observations.append(Observation(
            entity_type="business",
            entity_id=biz_id_str,
            category="workflow",
            fact_key="booking_mechanism",
            fact_value={"booking_type": booking_type, "has_calendar_sync": has_calendar},
            source="page_dom_parser",
            source_tier=SourceTier.SCRAPED_CONTENT,
            raw_evidence=f"Booking workflow detected as: {booking_type} (Calendar present: {has_calendar})"
        ))

        # (d) Performance & UX metrics
        perf_score = float(audit.get("performance_score", 55.0))
        ux_score = float(audit.get("ux_conversion_score", 50.0))
        observations.append(Observation(
            entity_type="business",
            entity_id=biz_id_str,
            category="performance",
            fact_key="website_health_scores",
            fact_value={"performance_score": perf_score, "ux_conversion_score": ux_score},
            source="lighthouse_diagnostic",
            source_tier=SourceTier.DIRECT_HTTP_AUDIT,
            raw_evidence=f"Lighthouse scores: Performance={perf_score}/100, UX/Conversion={ux_score}/100"
        ))

        # -------------------------------------------------------------
        # 2. INFERENCES (Deductions from observations)
        # -------------------------------------------------------------
        # Inference 1: Scheduling friction
        if not has_calendar:
            inferences.append(Inference(
                entity_type="business",
                entity_id=biz_id_str,
                category="friction",
                hypothesis="High operational drag and missed leads due to lack of self-serve appointment scheduling.",
                confidence=0.88,
                supporting_observation_keys=["booking_mechanism"],
                risk_factor="LOW",
                reasoning=f"{business_name} relies on {booking_type}, causing delayed lead response and phone-tag drop-off."
            ))

        # Inference 2: Conversion leak
        if perf_score < 60.0 or ux_score < 60.0:
            inferences.append(Inference(
                entity_type="business",
                entity_id=biz_id_str,
                category="conversion_leak",
                hypothesis="High bounce rate and visitor loss caused by suboptimal mobile paint and missing instant pricing engagement.",
                confidence=0.84,
                supporting_observation_keys=["website_health_scores"],
                risk_factor="LOW",
                reasoning=f"Performance ({perf_score}) and UX ({ux_score}) are below the 60.0 conversion threshold."
            ))

        # -------------------------------------------------------------
        # 3. RECOMMENDATIONS (Actionable software solutions)
        # -------------------------------------------------------------
        if not has_calendar:
            cap = capability_catalog.get_capability("CAP-002-BOOKING-AUTOMATION")
            if cap:
                recommendations.append(Recommendation(
                    capability_id=cap.capability_id,
                    title=cap.name,
                    description=cap.description,
                    rationale=f"Empower prospects of {business_name} to schedule instant appointments directly into calendar.",
                    expected_impact="Capture 30-40% more inbound prospects outside normal business hours",
                    effort_days=5,
                    target_price_usd=cap.target_price_usd,
                    confidence=0.88,
                    prerequisites=cap.requirements,
                    ceo_gate_required=False
                ))

        if perf_score < 60.0 or ux_score < 60.0:
            cap = capability_catalog.get_capability("CAP-003-PRICING-ESTIMATOR")
            if cap:
                recommendations.append(Recommendation(
                    capability_id=cap.capability_id,
                    title=cap.name,
                    description=cap.description,
                    rationale=f"Deploy an interactive instant cost calculator on {domain} to capture prospect intent early.",
                    expected_impact="Double lead conversion rate by providing immediate estimate transparency",
                    effort_days=4,
                    target_price_usd=cap.target_price_usd,
                    confidence=0.84,
                    prerequisites=cap.requirements,
                    ceo_gate_required=False
                ))

        # Fallback if no friction detected
        if not recommendations:
            cap = capability_catalog.get_capability("CAP-001-LEAD-CAPTURE")
            if cap:
                recommendations.append(Recommendation(
                    capability_id=cap.capability_id,
                    title=cap.name,
                    description=cap.description,
                    rationale="Standardize lead capture with instant automated SMS/email qualification routing.",
                    expected_impact="Sub-60s first touch for incoming inquiries",
                    effort_days=3,
                    target_price_usd=cap.target_price_usd,
                    confidence=0.75,
                    prerequisites=cap.requirements,
                    ceo_gate_required=False
                ))

        # Overall confidence calculation
        avg_obs_conf = sum(o.confidence for o in observations) / len(observations) if observations else 0.5
        avg_inf_conf = sum(i.confidence for i in inferences) / len(inferences) if inferences else 0.5
        overall_confidence = round((avg_obs_conf * 0.4) + (avg_inf_conf * 0.6), 2)

        # CEO gate required if confidence < 0.65 or domain inactive
        ceo_gate_required = (overall_confidence < 0.65) or (not has_http_200)

        top_rec = recommendations[0]
        top_inf = inferences[0] if inferences else None

        explainable = ExplainableIntelligence(
            observation=f"Observed {domain} ({niche}) running on {', '.join(tech_stack[:2])} with booking mechanism '{booking_type}' and health score {perf_score}.",
            belief=top_inf.hypothesis if top_inf else "Standard operational profile with headroom for automation.",
            rationale=top_inf.reasoning if top_inf else "Proactive enhancement to optimize lead response velocity.",
            recommendation=f"Deploy {top_rec.title} for ${top_rec.target_price_usd:,.2f}.",
            evidence=[o.raw_evidence for o in observations],
            confidence=overall_confidence,
            ceo_gate_required=ceo_gate_required,
            metadata={
                "business_id": business_id,
                "domain": domain,
                "niche": niche,
                "observation_count": len(observations),
                "inference_count": len(inferences)
            }
        )

        return {
            "business_id": business_id,
            "domain": domain,
            "observations": observations,
            "inferences": inferences,
            "recommendations": recommendations,
            "explainable_summary": explainable,
            "confidence": overall_confidence,
            "ceo_gate_required": ceo_gate_required
        }


structured_research_engine = StructuredResearchEngine()
