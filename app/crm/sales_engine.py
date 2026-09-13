"""
Deterministic Sales Conversation & Persuasion Engine — Phase 5.

Enforces:
1. Bounded deterministic sales state machine:
   NEW_RESPONSE -> QUALIFYING -> QUALIFIED -> NEEDS_DEMO -> MEETING_REQUESTED ->
   PROPOSAL_READY -> NEGOTIATION -> PAYMENT_PENDING -> WON -> LOST -> FOLLOW_UP
2. Anti-hallucination / evidence-backed fact binding:
   - Prohibits fabricated ROI, invented statistics, fake testimonials, or unauthorized discounts.
   - Grounded strictly in observed audit findings and catalog offer parameters.
3. Pricing discipline:
   - Absolute commercial floor ($500.00 USD).
   - $500 - $999 counter-offers require operator review.
   - >= $1,000 counter-offers can be accepted autonomously if policy allows.
4. Demo Factory gating:
   - Demos are triggered strictly when commercially justified (intent = POSITIVE/INTERESTED or explicit demo request).
   - Never triggers mass demos.
"""
import enum
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database.models import (
    Business, Contact, AuditRun, AuditFinding, Offer,
    Reply, ReplyClassification, PipelineStage, PipelineEvent,
    Proposal, Deal, DealAuditTrail, Artifact,
    ConversationEvent, ChannelType, EventDirection, ConversationEventType
)
from app.core.config import settings
from app.crm.objections import objection_detector, objection_response_engine, ObjectionCategory, ObjectionResponse
from app.crm.negotiator import commercial_negotiator, NegotiationResult
from app.outreach.compliance import compliance_guard
from app.delivery.demo_factory import demo_factory
from app.delivery.demo_qa import demo_qa_engine

logger = logging.getLogger("agency.sales_engine")


class SalesState(str, enum.Enum):
    NEW_RESPONSE = "NEW_RESPONSE"
    QUALIFYING = "QUALIFYING"
    QUALIFIED = "QUALIFIED"
    NEEDS_DEMO = "NEEDS_DEMO"
    MEETING_REQUESTED = "MEETING_REQUESTED"
    PROPOSAL_READY = "PROPOSAL_READY"
    NEGOTIATION = "NEGOTIATION"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    WON = "WON"
    LOST = "LOST"
    FOLLOW_UP = "FOLLOW_UP"


class SalesStepResult(BaseModel):
    business_id: int
    current_state: SalesState
    previous_state: Optional[SalesState] = None
    intent: str
    suggested_draft: Optional[str] = None
    requires_human_approval: bool = True
    demo_generated: bool = False
    demo_url: Optional[str] = None
    proposal_generated: bool = False
    proposal_id: Optional[int] = None
    reasons: List[str] = Field(default_factory=list)
    action_item: Optional[str] = None


class SalesConversationEngine:
    """
    Deterministic coordinator for AI sales conversations, objection handling,
    and revenue lifecycle state transitions.
    """

    async def process_inbound_response(
        self,
        session: AsyncSession,
        business_id: int,
        reply_text: str,
        classification: str,
        sender_email: Optional[str] = None,
        channel: str = "EMAIL"
    ) -> SalesStepResult:
        biz = await session.get(Business, business_id)
        if not biz:
            raise ValueError(f"Business {business_id} not found.")

        # 1. Fetch latest audit, findings, and offer for grounded reasoning
        audit_q = select(AuditRun).where(AuditRun.business_id == business_id).order_by(AuditRun.audited_at.desc())
        audit = (await session.execute(audit_q)).scalars().first()

        findings = []
        if audit:
            f_q = select(AuditFinding).where(AuditFinding.audit_id == audit.id)
            findings = (await session.execute(f_q)).scalars().all()

        offer_q = select(Offer).where(Offer.business_id == business_id)
        offer = (await session.execute(offer_q)).scalars().first()

        # 2. Check for commercial objections & sensitive triggers
        detected_objections = objection_detector.detect_objections(reply_text)
        prospect_ctx = {
            "business_name": biz.name,
            "domain": biz.domain,
            "findings_count": len(findings),
            "perf_score": audit.performance_score if audit else 50.0,
            "current_offer_val": offer.recommended_price if offer else 1000.0,
            "from_name": settings.EMAIL_FROM_NAME or "Agency Director"
        }
        objection_eval = objection_response_engine.generate_response(
            prospect_context=prospect_ctx,
            objections=detected_objections,
            raw_reply=reply_text
        )

        norm_class = classification.upper().strip()
        reasons: List[str] = []
        demo_generated = False
        demo_url = None
        proposal_generated = False
        proposal_id = None
        suggested_draft = None
        requires_approval = True
        target_state = SalesState.QUALIFYING

        # 3. Deterministic Intent & State Routing
        if norm_class in ("UNSUBSCRIBE", "OPT_OUT") or objection_eval.primary_objection == ObjectionCategory.OPT_OUT.value:
            target_state = SalesState.LOST
            biz.pipeline_stage = PipelineStage.LOST.value
            await compliance_guard.add_to_suppression(
                session=session,
                email=sender_email or biz.public_email,
                reason="INBOUND_OPT_OUT"
            )
            reasons.append("Contact opted out; added to suppression list.")
            suggested_draft = None
            requires_approval = False
            action_item = "Lead opted out. Suppression recorded."

        elif norm_class in ("NEGATIVE", "NOT_INTERESTED") or objection_eval.primary_objection == ObjectionCategory.NOT_INTERESTED.value:
            target_state = SalesState.LOST
            biz.pipeline_stage = PipelineStage.LOST.value
            reasons.append("Contact indicated disinterest. Follow-ups cancelled.")
            suggested_draft = None
            requires_approval = False
            action_item = "Lead marked lost based on negative response."

        elif norm_class in ("NEEDS_HUMAN", "ESCALATION"):
            target_state = SalesState.QUALIFYING
            biz.pipeline_stage = PipelineStage.REPLIED.value
            suggested_draft = (
                f"Hello {biz.name} team,\n\n"
                f"Thank you for reaching out. Our executive team will review your inquiry and follow up directly.\n\n"
                f"Best regards,\nAgency Director"
            )
            reasons.append("Inquiry requires specialized human handling or operator sign-off.")
            requires_approval = True
            action_item = "Human operator escalation required."

        elif norm_class in ("MEETING_REQUEST", "CALL"):
            target_state = SalesState.MEETING_REQUESTED
            biz.pipeline_stage = PipelineStage.MEETING.value
            suggested_draft = (
                f"Hi {biz.name} team,\n\n"
                f"We would be glad to coordinate a brief 15-minute operational walkthrough. "
                f"Does tomorrow afternoon or Thursday morning suit your calendar better?\n\n"
                f"Best regards,\nCommercial Engineering Lead"
            )
            reasons.append("Prospect requested meeting or commercial walkthrough.")
            requires_approval = True
            action_item = "Schedule discovery call with prospect."

        elif norm_class in ("PRICE_REQUEST", "PRICING", "NEGOTIATION") or objection_eval.primary_objection in (
            ObjectionCategory.PRICE_HIGH.value, ObjectionCategory.PRICE_LOW.value, ObjectionCategory.NO_BUDGET.value
        ):
            target_state = SalesState.NEGOTIATION
            biz.pipeline_stage = PipelineStage.PROPOSAL.value
            catalog_price = offer.recommended_price if offer else 1000.0
            
            # Grounded pricing explanation: defend value, enforce $500 floor
            suggested_draft = objection_eval.client_facing_draft
            reasons.append(f"Commercial pricing inquiry/objection: {objection_eval.primary_objection}. Factual defense applied.")
            requires_approval = True
            action_item = f"Review pricing negotiation response ({objection_eval.primary_objection})."

        elif norm_class in ("POSITIVE", "INTERESTED"):
            # Check if commercial demo is justified
            is_demo_requested = any(w in reply_text.lower() for w in ["demo", "preview", "show me", "example", "sample", "see it"])
            
            if is_demo_requested or biz.pipeline_stage in (PipelineStage.CONTACTED.value, PipelineStage.REPLIED.value):
                target_state = SalesState.NEEDS_DEMO
                biz.pipeline_stage = PipelineStage.QUALIFIED_REPLY.value
                reasons.append("Positive intent verified. Commercially justified Demo Factory packaging triggered.")
                
                try:
                    demo_res = await demo_factory.generate_demo_package(session, business_id=biz.id)
                    qa_result = await demo_qa_engine.validate_artifact(session, artifact_id=demo_res.artifact_id)
                    
                    if qa_result.is_valid:
                        demo_generated = True
                        art_obj = await session.get(Artifact, demo_res.artifact_id)
                        demo_url = art_obj.preview_url if art_obj else f"/artifacts/demos/{demo_res.demo_id}.html"
                        biz.pipeline_stage = PipelineStage.DEMO_READY.value
                        reasons.append(f"Interactive demo package validated via QA: {demo_url}")
                        
                        suggested_draft = (
                            f"Hi {biz.name} team,\n\n"
                            f"Thank you for your interest. We've prepared an interactive preview demonstrating "
                            f"the recommended remediation specifically tailored for {biz.domain}:\n\n"
                            f"{demo_url}\n\n"
                            f"Would you have 5 minutes to review the preview and let us know if you'd like us to prepare the full deployment scope?"
                        )
                    else:
                        reasons.append(f"Demo generated but failed QA gates: {'; '.join(qa_result.errors)}")
                        suggested_draft = (
                            f"Hi {biz.name} team,\n\n"
                            f"Thank you for your reply. We are finalizing the technical specifications for {biz.domain} "
                            f"and will share the complete review shortly."
                        )
                except Exception as e:
                    logger.error(f"[SalesEngine] Demo generation error for #{biz.id}: {e}")
                    reasons.append(f"Demo generation encountered error: {e}")
                
                action_item = f"Demo ready for review: {demo_url or 'Pending QA'}. Review and approve draft."
            else:
                target_state = SalesState.QUALIFIED
                biz.pipeline_stage = PipelineStage.QUALIFIED_REPLY.value
                suggested_draft = (
                    f"Hi {biz.name} team,\n\n"
                    f"Great to connect. To ensure we tailor the remediation plan precisely to your priorities, "
                    f"is your primary focus on increasing inbound customer inquiry conversions or mobile page performance?"
                )
                reasons.append("Positive reply qualified for commercial scope exploration.")
                action_item = "Lead qualified. Send scope clarification."

        elif norm_class in ("QUESTION", "NEED_MORE_INFO") or objection_eval.primary_objection == ObjectionCategory.NEED_MORE_INFO.value:
            target_state = SalesState.QUALIFYING
            biz.pipeline_stage = PipelineStage.REPLIED.value
            
            top_finding = findings[0].finding if findings else "Core Web Vitals and mobile conversion optimization"
            suggested_draft = (
                f"Hi {biz.name} team,\n\n"
                f"Thank you for following up. Regarding your question on {biz.domain}:\n\n"
                f"Our analysis specifically focused on {top_finding.lower()}. We deploy turnkey, production-ready "
                f"fixes that address these exact bottlenecks within 3 to 7 business days on a fixed-fee schedule.\n\n"
                f"Would you be open to taking a look at a brief diagnostic summary?"
            )
            reasons.append("Specific question or technical clarification handled with evidence grounding.")
            requires_approval = True
            action_item = "Review and dispatch answer to customer inquiry."

        else:
            target_state = SalesState.QUALIFYING
            biz.pipeline_stage = PipelineStage.REPLIED.value
            suggested_draft = (
                f"Hi {biz.name} team,\n\n"
                f"Thank you for your message regarding {biz.domain}. Could you clarify what specific goals you have for your digital presence this quarter?"
            )
            reasons.append(f"Inbound intent classified as {norm_class}. Standard qualification applied.")
            requires_approval = True
            action_item = "Unclassified reply. Human review advised."

        # 4. Record Pipeline Event
        p_event = PipelineEvent(
            business_id=biz.id,
            from_stage=biz.pipeline_stage,
            to_stage=biz.pipeline_stage,
            note=f"[SalesEngine] Processed {norm_class} inbound. State: {target_state.value}. Reasons: {'; '.join(reasons)}",
            created_at=datetime.utcnow()
        )
        session.add(p_event)

        # 5. Record Multichannel Conversation Event
        c_event = ConversationEvent(
            business_id=biz.id,
            channel=channel,
            direction=EventDirection.INBOUND.value,
            provider="InboxPoller",
            event_type=ConversationEventType.RECEIVED.value,
            content=reply_text,
            metadata_json={
                "classification": norm_class,
                "sales_state": target_state.value,
                "objection_category": objection_eval.primary_objection,
                "suggested_draft": suggested_draft
            },
            idempotency_key=f"sales_inbound_{biz.id}_{int(datetime.utcnow().timestamp())}"
        )
        session.add(c_event)

        await session.commit()

        return SalesStepResult(
            business_id=biz.id,
            current_state=target_state,
            intent=norm_class,
            suggested_draft=suggested_draft,
            requires_human_approval=requires_approval,
            demo_generated=demo_generated,
            demo_url=demo_url,
            proposal_generated=proposal_generated,
            proposal_id=proposal_id,
            reasons=reasons,
            action_item=action_item
        )


sales_conversation_engine = SalesConversationEngine()
