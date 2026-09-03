from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.entities import Lead, Audit, OutreachMessage, LeadEvent, EventType, MessageStatus, LeadStatus
from app.agents.outreach import PersonalizedOutreachWriter
from app.ai.base import BaseAIProvider
from app.ai.factory import get_ai_provider
from app.ai.schemas import LeadQualificationResult
from app.providers.base import BaseMessageProvider
from app.providers.factory import get_message_provider

class OutreachService:
    """
    Manages generation, human approval, and dispatch of outreach messages.
    Guarantees that human takeover halts all automated sends.
    """

    def __init__(
        self,
        ai_provider: Optional[BaseAIProvider] = None,
        msg_provider: Optional[BaseMessageProvider] = None
    ):
        self.ai = ai_provider or get_ai_provider()
        self.msg_provider = msg_provider or get_message_provider()
        self.writer = PersonalizedOutreachWriter(self.ai)

    async def draft_outreach_for_lead(
        self,
        db: AsyncSession,
        lead_id: int
    ) -> OutreachMessage:
        result = await db.execute(select(Lead).where(Lead.id == lead_id))
        lead = result.scalar_one_or_none()
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        biz = lead.business
        audit_res = await db.execute(
            select(Audit).where(Audit.business_id == lead.business_id).order_by(Audit.audited_at.desc())
        )
        audit = audit_res.scalars().first()

        business_info = {
            "name": biz.name if biz else "Business Owner",
            "domain": biz.domain if biz else "",
            "niche": biz.niche if biz else "Local Services",
            "booking_url": getattr(biz, "website_url", "https://cal.com/apexcomfort/diagnostic")
        }

        audit_info = {
            "overall_health_score": audit.overall_health_score if audit else 50.0,
            "performance_score": audit.performance_score if audit else 50.0,
            "seo_score": audit.seo_score if audit else 50.0,
            "findings": audit.findings if audit else []
        }

        qual = LeadQualificationResult(
            lead_score=lead.lead_score,
            qualification=lead.qualification,
            intent_level=lead.intent_level,
            pain_points=lead.pain_points or [],
            recommended_service=lead.recommended_service or "Diagnostic Review",
            reasoning=lead.reasoning or "",
            confidence=lead.confidence
        )

        draft_result = await self.writer.draft(business_info, audit_info, qual, channel="EMAIL")

        msg = OutreachMessage(
            lead_id=lead.id,
            channel="EMAIL",
            recipient=lead.contact_email,
            subject=draft_result.subject,
            body=draft_result.body,
            status=MessageStatus.PENDING_APPROVAL.value,
            is_mocked=True
        )
        db.add(msg)
        await db.flush()

        lead.status = LeadStatus.OUTREACH_PENDING.value

        event = LeadEvent(
            lead_id=lead.id,
            event_type=EventType.OUTREACH_GENERATED.value,
            payload={
                "message_id": msg.id,
                "subject": msg.subject,
                "recipient": msg.recipient,
                "status": msg.status
            }
        )
        db.add(event)
        await db.commit()
        await db.refresh(msg)
        return msg

    async def approve_and_send(
        self,
        db: AsyncSession,
        message_id: int
    ) -> OutreachMessage:
        result = await db.execute(select(OutreachMessage).where(OutreachMessage.id == message_id))
        msg = result.scalar_one_or_none()
        if not msg:
            raise ValueError(f"OutreachMessage {message_id} not found")

        lead = msg.lead
        # Human Takeover Check: If enabled, prevent automated sending!
        if lead and lead.human_takeover:
            raise RuntimeError(
                f"Cannot send outreach: Human takeover is ACTIVE for lead {lead.id} ({lead.human_takeover_reason})"
            )

        # Mark Approved
        now = datetime.utcnow()
        msg.status = MessageStatus.APPROVED.value
        msg.approved_at = now

        # Send via message provider (Mock/Safe)
        delivery = await self.msg_provider.send_message(
            recipient=msg.recipient,
            subject=msg.subject,
            body=msg.body,
            lead_id=msg.lead_id,
            channel=msg.channel
        )

        msg.status = MessageStatus.MOCKED_SENT.value if delivery.is_mocked else MessageStatus.SENT.value
        msg.sent_at = delivery.sent_at

        if lead:
            lead.status = LeadStatus.CONTACTED.value

        event = LeadEvent(
            lead_id=msg.lead_id,
            event_type=EventType.OUTREACH_SENT.value,
            payload={
                "message_id": msg.id,
                "provider_message_id": delivery.message_id,
                "status": msg.status,
                "sent_at": delivery.sent_at.isoformat()
            }
        )
        db.add(event)
        await db.commit()
        await db.refresh(msg)
        return msg
