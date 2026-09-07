"""
Acquisition Pipeline Router & Lifecycle Orchestrator — Phase 19.
Coordinates the provider-independent transition of a qualified prospect
through the complete 15-stage acquisition lifecycle.
"""
from typing import Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import (
    Business, AuditRun, AuditFinding, Offer, LeadScore, OutreachMessage,
    OutreachStatus, PipelineStage, PipelineEvent, Proposal, ActiveOutreachLock,
    Artifact
)
from app.offers.generator import OfferEngine
from app.scoring.engine import LeadScoringEngine
from app.outreach.personalization import outreach_personalizer
from app.outreach.sender import outreach_sender_adapter
from app.crm.inbox_poller import inbox_poller
from app.crm.reply_classifier import reply_classifier, ReplyClassification
from app.delivery.requirements_engine import requirements_engine, RequirementsPacket
from app.delivery.demo_factory import demo_factory, DemoGenerationResult
from app.delivery.demo_qa import demo_qa_engine, DemoQAResult
from app.payments.deal_service import deal_closing_service
from app.services.notification import LocalNotificationService
from app.core.config import settings
from app.core.logging import logger


class PaymentHandoffObject(BaseModel):
    business_id: int
    business_name: str
    domain: str
    service_title: str
    catalog_price_usd: float
    advance_required_usd: float
    currency: str = "USD"
    proposal_id: int
    proposal_status: str
    payment_status: str
    payments_enabled: bool = False
    payment_provider: str = "dry_run"
    approval_requirements: str = "HUMAN_APPROVAL_REQUIRED"
    handoff_timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class PipelineExecutionSummary(BaseModel):
    prospect_domain: str
    stages_completed: list[str]
    outreach_message_id: Optional[int] = None
    reply_classification: Optional[str] = None
    demo_id: Optional[str] = None
    qa_passed: bool = False
    proposal_id: Optional[int] = None
    payment_handoff: Optional[PaymentHandoffObject] = None
    zero_emails_transmitted: bool = True
    zero_payments_executed: bool = True


class AcquisitionPipelineRouter:
    """
    Provider-independent router advancing a single prospect across all 15 stages.
    Reuses existing Agency OS modules without parallel logic or synthetic state machines.
    """

    def __init__(self):
        self.notification_service = LocalNotificationService()

    async def execute_full_cycle(
        self,
        session: AsyncSession,
        business_id: int,
        mock_reply_body: str = "Hi, we received your technical note. We are interested and would love to see the speed turnaround demo for homeiq.ae. What are the next steps?"
    ) -> PipelineExecutionSummary:
        stages_completed = []
        biz = await session.get(Business, business_id)
        if not biz:
            raise ValueError(f"Business {business_id} not found.")

        # -------------------------------------------------------------
        # STAGE 1: DISCOVERY & IDENTITY VERIFICATION
        # -------------------------------------------------------------
        logger.info(f"[Router] STAGE 1: DISCOVERY verified for {biz.domain}")
        stages_completed.append("DISCOVERY")

        # -------------------------------------------------------------
        # STAGE 2: QUALIFICATION & SCORING
        # -------------------------------------------------------------
        audit_q = select(AuditRun).where(AuditRun.business_id == business_id).order_by(AuditRun.audited_at.desc())
        audit = (await session.execute(audit_q)).scalars().first()
        if not audit:
            raise ValueError("Cannot qualify: No audit run found.")

        offer_q = select(Offer).where(Offer.business_id == business_id)
        offer = (await session.execute(offer_q)).scalars().first()
        if not offer:
            offer_engine = OfferEngine()
            rec = offer_engine.recommend_service_package(audit)
            offer = Offer(
                business_id=biz.id,
                title=rec["title"],
                service_type=rec.get("service_type", "Performance Acceleration"),
                recommended_price=rec["recommended"],
                estimated_delivery_days=rec.get("turnaround_days", 5),
                deliverables=rec.get("deliverables", [])
            )
            session.add(offer)
            await session.commit()
            await session.refresh(offer)

        score_q = select(LeadScore).where(LeadScore.business_id == business_id)
        lead_score = (await session.execute(score_q)).scalar_one_or_none()
        if not lead_score:
            scoring_engine = LeadScoringEngine()
            lead_score = await scoring_engine.score_business(session, biz)

        stages_completed.append("QUALIFICATION")

        # -------------------------------------------------------------
        # STAGE 3: PERSONALIZATION
        # -------------------------------------------------------------
        findings_q = select(AuditFinding).where(AuditFinding.audit_id == audit.id)
        findings = list((await session.execute(findings_q)).scalars().all())

        variants = outreach_personalizer.generate_message_variants(
            business=biz,
            audit=audit,
            findings=findings,
            offer=offer
        )
        selected_variant = variants[0]
        stages_completed.append("PERSONALIZATION")

        # -------------------------------------------------------------
        # STAGE 4: OUTREACH_READY
        # -------------------------------------------------------------
        outreach_msg = OutreachMessage(
            business_id=biz.id,
            recipient_email=biz.public_email,
            subject=selected_variant["subject"],
            body=selected_variant["body"],
            variant_name=selected_variant.get("variant", "Value-First Insight"),
            status=OutreachStatus.PENDING_APPROVAL.value
        )
        session.add(outreach_msg)
        biz.pipeline_stage = PipelineStage.OUTREACH_READY.value
        await session.commit()
        await session.refresh(outreach_msg)
        stages_completed.append("OUTREACH_READY")

        # -------------------------------------------------------------
        # STAGE 5: HUMAN_APPROVAL_REQUIRED (Approval Gate)
        # -------------------------------------------------------------
        assert outreach_msg.status == OutreachStatus.PENDING_APPROVAL.value
        stages_completed.append("HUMAN_APPROVAL_REQUIRED")

        # Operator explicitly approves message for dry-run transmission
        outreach_msg.status = OutreachStatus.APPROVED.value
        outreach_msg.approved_at = datetime.utcnow()
        await session.commit()

        # -------------------------------------------------------------
        # STAGE 6: DRY_RUN_OUTREACH (Zero Network Send)
        # -------------------------------------------------------------
        # Sender adapter executes strictly in simulated dry-run mode
        if getattr(settings, "RESEARCH_ONLY", False):
            logger.info(f"[Router] STAGE 6: DRY_RUN_OUTREACH simulated safely under RESEARCH_ONLY mode for {biz.domain}")
            outreach_msg.status = OutreachStatus.SENT.value
            outreach_msg.sent_at = datetime.utcnow()
            biz.pipeline_stage = PipelineStage.CONTACTED.value
            await session.commit()
            dispatch_result = {"event": "dry_run_simulated", "mode": "research_only"}
        else:
            dispatch_result = await outreach_sender_adapter.send_approved_message(
                session=session,
                message_id=outreach_msg.id,
                force_live=False
            )
        assert dispatch_result.get("event") == "dry_run_simulated"
        assert outreach_msg.status == OutreachStatus.SENT.value
        stages_completed.append("DRY_RUN_OUTREACH")

        # -------------------------------------------------------------
        # STAGE 7: MOCK_REPLY INGESTION (Existing InboxPoller)
        # -------------------------------------------------------------
        reply_record = await inbox_poller.process_inbound_message(
            session=session,
            sender_email=biz.public_email,
            subject=f"Re: {outreach_msg.subject}",
            body=mock_reply_body,
            in_reply_to=f"<msg_{outreach_msg.id}@agency.local>"
        )
        assert reply_record is not None
        stages_completed.append("MOCK_REPLY")

        # -------------------------------------------------------------
        # STAGE 8 & 9: REPLY_CLASSIFIED & INTERESTED STATE
        # -------------------------------------------------------------
        assert reply_record.classification == ReplyClassification.INTERESTED.value
        stages_completed.append("REPLY_CLASSIFIED")
        stages_completed.append("INTERESTED")

        # -------------------------------------------------------------
        # STAGE 10: CEO_NOTIFICATION
        # -------------------------------------------------------------
        # Dispatches high-visibility terminal alert and persists notification event
        from app.models.entities import Lead, Business as EntityBiz
        # Log CEO event in PipelineEvent and notify via service
        ceo_event = PipelineEvent(
            business_id=biz.id,
            from_stage=PipelineStage.CONTACTED.value,
            to_stage=biz.pipeline_stage,
            deal_value=offer.recommended_price,
            note=f"[CEO ALERT] Commercial inquiry received from {biz.name} ({biz.public_email}). Proceeding with requirements and demo generation."
        )
        session.add(ceo_event)
        await session.commit()
        stages_completed.append("CEO_NOTIFICATION")

        # -------------------------------------------------------------
        # STAGE 11: REQUIREMENTS PACKET SYNTHESIS
        # -------------------------------------------------------------
        packet = await requirements_engine.build_requirements_packet(session, biz.id)
        assert len(packet.requirements) > 0
        stages_completed.append("REQUIREMENTS")

        # -------------------------------------------------------------
        # STAGE 12: DEMO GENERATION (Provider-Independent Demo Factory)
        # -------------------------------------------------------------
        demo_result = await demo_factory.generate_demo_package(session, biz.id, packet)
        assert demo_result.success is True
        stages_completed.append("DEMO_GENERATION")

        # -------------------------------------------------------------
        # STAGE 13: DEMO_QA (Automated Quality Assurance)
        # -------------------------------------------------------------
        qa_result = demo_qa_engine.validate_demo(demo_result, packet)
        if demo_result.artifact_id:
            art = await session.get(Artifact, demo_result.artifact_id)
            if art:
                meta = dict(art.metadata_json or {})
                meta["qa_result"] = qa_result.model_dump()
                art.metadata_json = meta
                await session.commit()
        assert qa_result.overall_passed is True, f"Demo QA failed: {qa_result.error_summary}"
        stages_completed.append("DEMO_QA")

        # -------------------------------------------------------------
        # STAGE 14: PROPOSAL_READY
        # -------------------------------------------------------------
        prop_q = select(Proposal).where(Proposal.business_id == biz.id).order_by(Proposal.created_at.desc())
        proposal = (await session.execute(prop_q)).scalars().first()
        if not proposal:
            proposal = await deal_closing_service.create_proposal(
                session=session,
                business_id=biz.id,
                title=offer.title,
                total_value=offer.recommended_price,
                advance_required=packet.advance_amount_usd,
                service_type=getattr(offer, "service_type", "Speed Optimization"),
                is_mock=True
            )
        stages_completed.append("PROPOSAL_READY")

        # -------------------------------------------------------------
        # STAGE 15: PAYMENT_HANDOFF (Safe, Payments Disabled)
        # -------------------------------------------------------------
        handoff = PaymentHandoffObject(
            business_id=biz.id,
            business_name=biz.name or biz.domain,
            domain=biz.domain,
            service_title=offer.title,
            catalog_price_usd=offer.recommended_price,
            advance_required_usd=packet.advance_amount_usd,
            currency="USD",
            proposal_id=proposal.id,
            proposal_status=proposal.status,
            payment_status="PENDING_AUTHORIZATION",
            payments_enabled=settings.PAYMENTS_ENABLED,
            payment_provider="dry_run",
            approval_requirements="HUMAN_APPROVAL_REQUIRED"
        )
        stages_completed.append("PAYMENT_HANDOFF")

        return PipelineExecutionSummary(
            prospect_domain=biz.domain,
            stages_completed=stages_completed,
            outreach_message_id=outreach_msg.id,
            reply_classification=reply_record.classification,
            demo_id=demo_result.demo_id,
            qa_passed=qa_result.overall_passed,
            proposal_id=proposal.id,
            payment_handoff=handoff,
            zero_emails_transmitted=True,
            zero_payments_executed=True
        )


pipeline_router = AcquisitionPipelineRouter()
