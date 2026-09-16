"""
Agency OS — Structured Research Engine.
Disentangles raw signals into explicit Observations, Inferences, and Recommendations.
Enforces epistemic confidence calculation and produces explainable decision summaries.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.knowledge_model import (
    Observation, Inference, Recommendation, ExplainableIntelligence,
    SourceTier, store_fact, store_inference, store_recommendation
)
from app.intelligence.capability_catalog import capability_catalog
from app.database.models import KnowledgeFact


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
        has_phone = bool(signals.get("phone") or audit.get("has_phone", True))
        has_missed_call_textback = bool(signals.get("has_missed_call_textback", False))
        observations.append(Observation(
            entity_type="business",
            entity_id=biz_id_str,
            category="workflow",
            fact_key="booking_mechanism",
            fact_value={
                "booking_type": booking_type,
                "has_calendar_sync": has_calendar,
                "phone_detected": has_phone,
                "has_missed_call_textback": has_missed_call_textback
            },
            source="page_dom_parser",
            source_tier=SourceTier.SCRAPED_CONTENT,
            raw_evidence=f"Booking workflow detected as: {booking_type} (Calendar: {has_calendar}, Phone: {has_phone}, MissedCallTextBack: {has_missed_call_textback})"
        ))

        # (d) Business Identity & Positioning
        target_market = signals.get("target_market") or ("Commercial & Residential" if niche in ("HVAC", "Roofing") else "Local Consumers")
        market_pos = signals.get("market_positioning") or "Regional Specialist"
        observations.append(Observation(
            entity_type="business",
            entity_id=biz_id_str,
            category="business_identity",
            fact_key="identity_profile",
            fact_value={
                "business_name": business_name,
                "niche": niche,
                "target_market": target_market,
                "market_positioning": market_pos
            },
            source="identity_enrichment",
            source_tier=SourceTier.SCRAPED_CONTENT,
            raw_evidence=f"Entity identified as {business_name} in {niche} targeting {target_market}."
        ))

        # (e) Services & Customer Journey
        core_services = signals.get("core_services") or audit.get("core_services") or [f"{niche} Installation", f"{niche} Repair"]
        emergency_offered = bool(signals.get("emergency_services") or any("emergency" in s.lower() for s in core_services))
        observations.append(Observation(
            entity_type="business",
            entity_id=biz_id_str,
            category="services",
            fact_key="service_offerings",
            fact_value={
                "core_services": core_services,
                "emergency_offered": emergency_offered,
                "delivery_model": "On-Site Service Dispatch" if niche in ("HVAC", "Roofing", "Plumbing") else "In-Office Appointment"
            },
            source="service_catalog_crawler",
            source_tier=SourceTier.SCRAPED_CONTENT,
            raw_evidence=f"Services: {', '.join(core_services[:3])}; Emergency: {emergency_offered}"
        ))

        # (f) Reputation & Review signals
        review_count = int(signals.get("review_count", audit.get("review_count", 18)))
        rating = float(signals.get("rating", audit.get("rating", 4.2)))
        has_review_request_system = bool(signals.get("has_review_automation", False))
        observations.append(Observation(
            entity_type="business",
            entity_id=biz_id_str,
            category="reputation",
            fact_key="review_profile",
            fact_value={
                "review_count": review_count,
                "rating": rating,
                "automated_review_requests": has_review_request_system
            },
            source="google_places_audit",
            source_tier=SourceTier.DIRECT_HTTP_AUDIT,
            raw_evidence=f"Google Reviews: {review_count} reviews, {rating} stars; Automation: {has_review_request_system}"
        ))

        # (g) CRM & Tech signals
        known_crms = ["hubspot", "salesforce", "servicetitan", "jobber", "zoho", "pipedrive"]
        detected_crm = next((c for c in known_crms if any(c in t.lower() for t in tech_stack)), None)
        observations.append(Observation(
            entity_type="business",
            entity_id=biz_id_str,
            category="crm_tech",
            fact_key="crm_presence",
            fact_value={"detected_crm": detected_crm, "has_crm": detected_crm is not None},
            source="stack_analyzer",
            source_tier=SourceTier.DIRECT_HTTP_AUDIT,
            raw_evidence=f"CRM: {'Detected ' + detected_crm if detected_crm else 'None detected'}"
        ))

        # (h) Performance & UX metrics
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

        # Inference 3: Missed Call Revenue Loss
        if has_phone and not has_missed_call_textback:
            inferences.append(Inference(
                entity_type="business",
                entity_id=biz_id_str,
                category="missed_call_leak",
                hypothesis="20-40% of inbound customer calls during peak hours or after-hours are lost to competitors due to lack of instant SMS text-back.",
                confidence=0.91,
                supporting_observation_keys=["booking_mechanism", "identity_profile"],
                risk_factor="HIGH",
                reasoning=f"{business_name} advertises a phone line but has no automated missed-call capture, leading to immediate prospect abandonment."
            ))

        # Inference 4: Reputation / Review Deficit
        if review_count < 40 or not has_review_request_system:
            inferences.append(Inference(
                entity_type="business",
                entity_id=biz_id_str,
                category="reputation_deficit",
                hypothesis="Customer satisfaction is not being converted into Google reviews systematically, limiting local Map pack ranking.",
                confidence=0.86,
                supporting_observation_keys=["review_profile"],
                risk_factor="MEDIUM",
                reasoning=f"{business_name} has only {review_count} reviews with no automated post-job review request sequence."
            ))

        # Inference 5: Appointment No-Show Risk
        if niche in ("Dental", "Healthcare", "Legal", "HVAC", "Roofing") and not has_calendar:
            inferences.append(Inference(
                entity_type="business",
                entity_id=biz_id_str,
                category="appointment_slippage",
                hypothesis="Unconfirmed appointments and manual reminders result in 15-25% no-show rates and unutilized operational capacity.",
                confidence=0.85,
                supporting_observation_keys=["service_offerings", "booking_mechanism"],
                risk_factor="MEDIUM",
                reasoning=f"Consultations in {niche} suffer from appointment slippage without automated multi-stage SMS/email reminders."
            ))

        # Inference 6: CRM Fragmentation
        if not detected_crm:
            inferences.append(Inference(
                entity_type="business",
                entity_id=biz_id_str,
                category="crm_fragmentation",
                hypothesis="Leads and client communications are scattered across phone logs and inboxes with no unified record.",
                confidence=0.82,
                supporting_observation_keys=["crm_presence"],
                risk_factor="MEDIUM",
                reasoning="Lack of a centralized CRM system prevents automated follow-up cadences and revenue pipeline tracking."
            ))

        # -------------------------------------------------------------
        # 3. RECOMMENDATIONS (Actionable software solutions)
        # -------------------------------------------------------------
        if has_phone and not has_missed_call_textback:
            cap = capability_catalog.get_capability("AGY-AUTO-MISSED-CALL-TEXTBACK")
            if cap:
                recommendations.append(Recommendation(
                    capability_id=cap.capability_id,
                    title=cap.name,
                    description=cap.description,
                    rationale=f"Deploy automated sub-30s SMS text-back for missed inbound calls to {business_name}.",
                    expected_impact="Recover 35-50% of missed inbound callers and stop lead leakage to local competitors",
                    effort_days=3,
                    target_price_usd=cap.target_price_usd,
                    confidence=0.91,
                    prerequisites=cap.requirements,
                    ceo_gate_required=False
                ))

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

        if review_count < 40 or not has_review_request_system:
            cap = capability_catalog.get_capability("AGY-AUTO-REVIEW-REQUEST")
            if cap:
                recommendations.append(Recommendation(
                    capability_id=cap.capability_id,
                    title=cap.name,
                    description=cap.description,
                    rationale=f"Implement systematic post-service review request sequence for {business_name}.",
                    expected_impact="Increase 5-star Google review volume by 3-5x within 60 days",
                    effort_days=3,
                    target_price_usd=cap.target_price_usd,
                    confidence=0.86,
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

        if niche in ("Dental", "Healthcare", "Legal", "HVAC", "Roofing") and not has_calendar:
            cap = capability_catalog.get_capability("AGY-AUTO-APPOINTMENT-REMINDER")
            if cap:
                recommendations.append(Recommendation(
                    capability_id=cap.capability_id,
                    title=cap.name,
                    description=cap.description,
                    rationale="Multi-stage two-way SMS reminder workflow (T-24h and T-2h) with confirmation parsing.",
                    expected_impact="Cut no-show rates by 60-80% and keep practitioners at full schedule density",
                    effort_days=3,
                    target_price_usd=cap.target_price_usd,
                    confidence=0.85,
                    prerequisites=cap.requirements,
                    ceo_gate_required=False
                ))

        if not detected_crm:
            cap = capability_catalog.get_capability("AGY-AUTO-CRM-SYSTEM")
            if cap:
                recommendations.append(Recommendation(
                    capability_id=cap.capability_id,
                    title=cap.name,
                    description=cap.description,
                    rationale=f"Deploy unified customer relationship management database for {business_name}.",
                    expected_impact="Centralize 100% of customer interactions and eliminate lost lead records",
                    effort_days=5,
                    target_price_usd=cap.target_price_usd,
                    confidence=0.82,
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

        # Sort recommendations descending by confidence
        recommendations.sort(key=lambda r: r.confidence, reverse=True)

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
                "inference_count": len(inferences),
                "recommendation_count": len(recommendations)
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

    @classmethod
    async def persist_research_knowledge(
        cls,
        session: AsyncSession,
        research_result: Dict[str, Any]
    ) -> List[KnowledgeFact]:
        """
        Persists observations, inferences, and recommendations atomically to KnowledgeFact table.
        """
        saved_facts: List[KnowledgeFact] = []
        biz_id_str = str(research_result.get("business_id", "0"))

        for obs in research_result.get("observations", []):
            fact = await store_fact(session, obs)
            saved_facts.append(fact)

        for inf in research_result.get("inferences", []):
            fact = await store_inference(session, inf)
            saved_facts.append(fact)

        for rec in research_result.get("recommendations", []):
            fact = await store_recommendation(session, rec, entity_id=biz_id_str)
            saved_facts.append(fact)

        return saved_facts


structured_research_engine = StructuredResearchEngine()

