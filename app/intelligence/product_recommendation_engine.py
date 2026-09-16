"""
Agency OS — Product Recommendation Engine.
Provides epistemic separation (Observation -> Inference -> Recommendation)
to transform generalized client problems and industry signals into matched
commercial capabilities without developer manual mapping.
Integrates empirical telemetry to adjust recommendation confidence.
"""

from typing import Dict, Any, List, Optional
import uuid
import re
from datetime import datetime
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.intelligence.capability_catalog import capability_catalog, SolutionCapability
from app.intelligence.knowledge_model import Observation, Inference, SourceTier
from app.database.models import WorkflowExecutionLog, OutcomeTrace
from app.core.logging import logger


class MatchedCapabilityRecommendation(BaseModel):
    capability_id: str
    name: str
    category: str
    reason: str
    evidence: List[str] = Field(default_factory=list)
    confidence: float = 0.85
    required_integrations: List[str] = Field(default_factory=list)
    n8n_candidates: List[str] = Field(default_factory=list)
    n8n_implementation_status: str = "N8N_WORKFLOW_AVAILABLE"
    demo_available: bool = True
    demo_blueprint_type: str = "booking_flow"
    production_requirements: List[str] = Field(default_factory=list)
    estimated_complexity: str = "MODERATE"
    commercial_terms: Dict[str, Any] = Field(default_factory=dict)


class EpistemicRecommendationReport(BaseModel):
    report_id: str = Field(default_factory=lambda: f"rec_{uuid.uuid4().hex[:8]}")
    industry: str
    observed_problem: str
    observations: List[Observation] = Field(default_factory=list)
    inferences: List[Inference] = Field(default_factory=list)
    recommendations: List[MatchedCapabilityRecommendation] = Field(default_factory=list)
    commercial_policy: str = "DEMO / SCOPE -> PROPOSAL -> ADVANCE PAYMENT VERIFIED (40%) -> PRODUCTION AUTHORIZED"
    learning_signals_applied: int = 0
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ProductRecommendationEngine:
    """
    Reasoning engine that matches customer problem statements and industry context
    to Agency OS solution capabilities, strictly separating observations from inferences.
    """

    PROBLEM_KEYWORD_MAP = [
        (
            ["missed call", "miss calls", "losing calls", "unanswered phone", "phone rings", "missed inbound"],
            "AGY-AUTO-MISSED-CALL-TEXTBACK",
            "Inbound call leakage causing immediate prospect defection to competitors.",
            "Deploy sub-30s automated SMS text-back with suppression and business hours handling."
        ),
        (
            ["review", "google review", "rating", "trustpilot", "reputation", "social proof", "testimonials", "feedback"],
            "AGY-AUTO-REVIEW-REQUEST",
            "Customer satisfaction exists but is uncaptured, resulting in suboptimal search ranking.",
            "Deploy systematic post-completion review requests with duplicate suppression."
        ),
        (
            ["no-show", "no show", "appointment reminder", "missed appointment", "calendar delay", "cancellation", "confirm booking"],
            "AGY-AUTO-APPOINTMENT-REMINDER",
            "Capacity loss and unbilled tech hours caused by absent customer reminders.",
            "Deploy multi-stage 24h & 2h appointment reminder sequence with two-way confirmation."
        ),
        (
            ["dormant", "re-engage", "reengage", "inactive customer", "past client", "churn", "dead leads", "lost customer"],
            "AGY-AUTO-REENGAGEMENT",
            "Dormant customer database sits unmonetized without structured check-ins.",
            "Deploy frequency-capped re-engagement sequence with auto-cancel on response."
        ),
        (
            ["estimate", "quote", "proposal follow", "bids", "pricing sent", "quote pending", "follow up on quote"],
            "AGY-AUTO-ESTIMATE-FOLLOWUP",
            "Proposals go cold without consistent, respectful follow-up discipline.",
            "Deploy non-aggressive multi-stage estimate follow-up with status checking."
        ),
        (
            ["lead follow", "slow response", "form inquiry", "new lead", "reply delay", "web leads", "intake response"],
            "AGY-AUTO-LEAD-FOLLOWUP",
            "Inbound web inquiries lose conversion probability due to delayed rep response.",
            "Deploy sub-minute qualification and multi-stage follow-up cadence reusing Agency OS sender & classifier."
        ),
        (
            ["seasonal", "spring tune", "winter prep", "tax season", "end of year", "holiday promotion", "annual checkup"],
            "AGY-AUTO-SEASONAL-CAMPAIGN",
            "Seasonal demand spikes are missed due to lack of planned campaign batching.",
            "Deploy segmented lifecycle campaign engine with mandatory CEO approval gates."
        ),
        (
            ["cold outreach", "prospecting", "b2b outreach", "cold email", "outbound pipeline", "find new clients"],
            "AGY-AUTO-COLD-OUTREACH",
            "Manual prospecting is labor-intensive and risks deliverability without strict compliance.",
            "Deploy evidence-grounded cold outreach reusing Agency OS research, drafter, and sender."
        ),
        (
            ["ai receptionist", "voice receptionist", "phone receptionist", "virtual receptionist", "after-hours voice", "answer calls 24/7"],
            "AGY-AUTO-AI-RECEPTIONIST",
            "High phone inquiry volume cannot be answered by human staff around the clock.",
            "Integrate 24/7 AI Voice Receptionist (Integration Required: Third-party telephony provider credentials)."
        ),
        (
            ["crm", "pipeline software", "custom crm", "replace salesforce", "replace hubspot", "manage deals", "internal operations"],
            "AGY-AUTO-CRM-SYSTEM",
            "Generic commercial CRMs do not match bespoke company operations or carry heavy per-seat fees.",
            "Build custom commercial CRM & operations management software."
        ),
    ]

    @classmethod
    async def match_capabilities(
        cls,
        industry: str,
        observed_problem: str,
        customer_requirements: Optional[List[str]] = None,
        research_data: Optional[Dict[str, Any]] = None,
        session: Optional[AsyncSession] = None
    ) -> EpistemicRecommendationReport:
        """
        Executes tripartite reasoning:
        1. OBSERVATION: Extract grounded, verifiable facts.
        2. INFERENCE: Deduce operational bottlenecks and hypotheses (never presented as facts).
        3. RECOMMENDATION: Match solution capabilities from catalog, calculate confidence,
           and specify commercial path.
        """
        reqs = customer_requirements or []
        res_data = research_data or {}
        prob_lower = (observed_problem or "").lower()

        # -------------------------------------------------------------
        # STEP 1: GROUND-TRUTH OBSERVATIONS
        # -------------------------------------------------------------
        observations: List[Observation] = []
        entity_id = res_data.get("domain", f"lead_{uuid.uuid4().hex[:6]}")

        # Fact 1: Stated problem
        observations.append(Observation(
            entity_type="problem_statement",
            entity_id=entity_id,
            category="customer_intake",
            fact_key="stated_problem",
            fact_value={"problem_text": observed_problem},
            source="customer_dialogue",
            source_tier=SourceTier.DIRECT_HTTP_AUDIT,
            raw_evidence=f"Customer explicitly reported problem: '{observed_problem}'"
        ))

        # Fact 2: Industry niche
        observations.append(Observation(
            entity_type="business_profile",
            entity_id=entity_id,
            category="industry",
            fact_key="target_industry",
            fact_value={"industry": industry},
            source="intake_form",
            source_tier=SourceTier.DIRECT_HTTP_AUDIT,
            raw_evidence=f"Business operates in '{industry}' commercial vertical."
        ))

        # Fact 3: Customer requirements
        if reqs:
            observations.append(Observation(
                entity_type="requirements",
                entity_id=entity_id,
                category="specifications",
                fact_key="explicit_requirements",
                fact_value={"requirements_list": reqs},
                source="customer_brief",
                source_tier=SourceTier.DIRECT_HTTP_AUDIT,
                raw_evidence=f"Customer submitted {len(reqs)} specific requirements: {', '.join(reqs)}"
            ))

        # -------------------------------------------------------------
        # STEP 2: INFERENCES (Deductions from observations)
        # -------------------------------------------------------------
        inferences: List[Inference] = []
        matched_cap_ids: List[str] = []

        for keywords, cap_id, hypothesis, rationale in cls.PROBLEM_KEYWORD_MAP:
            if any(k in prob_lower for k in keywords):
                matched_cap_ids.append(cap_id)
                inferences.append(Inference(
                    entity_type="business",
                    entity_id=entity_id,
                    category="automation_opportunity",
                    hypothesis=hypothesis,
                    confidence=0.90,
                    supporting_observation_keys=["stated_problem", "target_industry"],
                    risk_factor="LOW" if "VOICE" not in cap_id else "MEDIUM",
                    reasoning=f"Based on client stating '{observed_problem}', we deduce that {rationale}"
                ))

        # Fallback if no direct keyword match
        if not matched_cap_ids:
            matched_cap_ids.append("AGY-AUTO-LEAD-FOLLOWUP")
            inferences.append(Inference(
                entity_type="business",
                entity_id=entity_id,
                category="automation_opportunity",
                hypothesis="General operational drag detected in lead handling or prospect conversion.",
                confidence=0.70,
                supporting_observation_keys=["stated_problem"],
                risk_factor="LOW",
                reasoning=f"No specialized single-vector keyword matched; inferring foundational lead follow-up need."
            ))

        # -------------------------------------------------------------
        # STEP 3: RECOMMENDATIONS (Catalog Grounded)
        # -------------------------------------------------------------
        recommendations: List[MatchedCapabilityRecommendation] = []
        learning_signals_count = 0

        for cap_id in matched_cap_ids:
            cap = capability_catalog.get_capability(cap_id)
            if not cap:
                continue

            # Query empirical learning signals if session provided
            base_confidence = 0.85
            if session:
                try:
                    for tmpl in cap.compatible_n8n_templates:
                        stmt = select(
                            WorkflowExecutionLog.execution_status,
                            func.count(WorkflowExecutionLog.id).label("cnt")
                        ).where(
                            WorkflowExecutionLog.template_id == tmpl
                        ).group_by(WorkflowExecutionLog.execution_status)
                        rows = (await session.execute(stmt)).all()
                        for st, cnt in rows:
                            learning_signals_count += cnt
                            if st == "SUCCESS" and cnt > 0:
                                base_confidence = min(0.98, base_confidence + 0.02 * cnt)
                            elif st == "FAILURE" and cnt > 0:
                                base_confidence = max(0.40, base_confidence - 0.05 * cnt)
                except Exception as db_err:
                    logger.warning(f"Failed to query empirical learning telemetry: {db_err}")

            evidence_items = [o.raw_evidence for o in observations]

            recommendations.append(MatchedCapabilityRecommendation(
                capability_id=cap.capability_id,
                name=cap.name,
                category=cap.category,
                reason=f"Directly resolves stated bottleneck for {industry}: {cap.problem}",
                evidence=evidence_items,
                confidence=round(base_confidence, 2),
                required_integrations=cap.integrations,
                n8n_candidates=cap.compatible_n8n_templates,
                n8n_implementation_status=cap.n8n_implementation_status,
                demo_available=bool(cap.demo_blueprint_type),
                demo_blueprint_type=cap.demo_blueprint_type,
                production_requirements=[
                    f"Verified {ing} credentials" for ing in cap.integrations
                ] + [
                    "40% Advance Payment Confirmed",
                    "Customer Discovery & Approval Sign-off"
                ],
                estimated_complexity=cap.complexity_level,
                commercial_terms={
                    "setup_fee_usd": cap.setup_fee_usd,
                    "monthly_management_usd": cap.monthly_management_usd,
                    "advance_deposit_rate": "40%",
                    "advance_deposit_usd": round(cap.setup_fee_usd * 0.40, 2),
                    "advance_payment_gate_required": True,
                    "production_authorization_rule": "NEVER unlock production implementation merely because a lead is INTERESTED."
                }
            ))

        return EpistemicRecommendationReport(
            industry=industry,
            observed_problem=observed_problem,
            observations=observations,
            inferences=inferences,
            recommendations=recommendations,
            learning_signals_applied=learning_signals_count
        )


product_recommendation_engine = ProductRecommendationEngine()
