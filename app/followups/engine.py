from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import (
    FollowupSequence, FollowupStatus, OutreachMessage, Business,
    PipelineStage, OutreachEvent
)
from app.core.config import settings
from app.core.logging import logger
from app.outreach.compliance import compliance_guard
from app.outreach.providers.factory import get_email_provider

class FollowupEngine:
    """
    Manages automated follow-up sequences.
    Enforces automatic cancellation when replies, unsubscribes, or bounces occur.
    Executes due follow-ups through the active email provider.
    """

    async def cancel_pending_followups(
        self, session: AsyncSession, business_id: int, reason_status: FollowupStatus
    ):
        """Cancels all scheduled follow-ups for a business upon reply, opt-out, or deal progression."""
        q = select(FollowupSequence).join(OutreachMessage).where(
            OutreachMessage.business_id == business_id,
            FollowupSequence.status == FollowupStatus.SCHEDULED.value
        )
        followups = (await session.execute(q)).scalars().all()
        for fu in followups:
            fu.status = reason_status.value
            logger.info(f"[FollowupEngine] Follow-up #{fu.id} (Step {fu.step_number}) auto-stopped with status: {reason_status.value}")
        await session.commit()

    async def process_due_followups(self, session: AsyncSession) -> List[FollowupSequence]:
        """
        Identifies and executes due follow-up messages.
        Validates suppression and pipeline stage before dispatching.
        """
        now = datetime.utcnow()
        q = select(FollowupSequence).where(
            FollowupSequence.status == FollowupStatus.SCHEDULED.value,
            FollowupSequence.scheduled_for <= now
        ).order_by(FollowupSequence.scheduled_for.asc())

        due = list((await session.execute(q)).scalars().all())
        sent_followups: List[FollowupSequence] = []
        provider = get_email_provider()

        for fu in due:
            msg = await session.get(OutreachMessage, fu.initial_message_id)
            if not msg:
                fu.status = FollowupStatus.CANCELLED_REPLY.value
                continue

            biz = await session.get(Business, msg.business_id)

            # Auto-stop Check 1: If business has replied or progressed past CONTACTED
            if biz and biz.pipeline_stage in (
                PipelineStage.REPLIED.value,
                PipelineStage.QUALIFIED_REPLY.value,
                PipelineStage.CALL.value,
                PipelineStage.PROPOSAL.value,
                PipelineStage.WON.value,
                PipelineStage.LOST.value
            ):
                fu.status = FollowupStatus.CANCELLED_REPLY.value
                logger.info(f"[FollowupEngine] Cancelled follow-up #{fu.id}: Business '{biz.name}' is already in stage {biz.pipeline_stage}")
                continue

            # Auto-stop Check 2: Compliance suppression list
            if await compliance_guard.is_suppressed(session, msg.recipient_email):
                fu.status = FollowupStatus.CANCELLED_UNSUB.value
                logger.info(f"[FollowupEngine] Cancelled follow-up #{fu.id}: Recipient {msg.recipient_email} is on suppression list")
                continue

            # Check daily rate limits
            if not await compliance_guard.can_send_today(session):
                logger.warning("[FollowupEngine] Daily outreach quota reached. Holding remaining follow-ups for tomorrow.")
                break

            # Dispatch follow-up email via provider
            try:
                res = await provider.send_email(
                    to_email=msg.recipient_email,
                    subject=fu.subject,
                    body=fu.body,
                    from_email=settings.OUTREACH_FROM_EMAIL,
                    from_name=settings.OUTREACH_FROM_NAME
                )
                fu.status = FollowupStatus.SENT.value
                fu.sent_at = now
                sent_followups.append(fu)

                event_log = OutreachEvent(
                    outreach_message_id=msg.id,
                    event_type=f"followup_{fu.step_number}_delivered",
                    details=res.get("details", {})
                )
                session.add(event_log)
                logger.info(f"[FollowupEngine] Follow-up #{fu.id} (Step {fu.step_number}) delivered to {msg.recipient_email}")
            except Exception as e:
                logger.error(f"[FollowupEngine] Failed sending follow-up #{fu.id}: {e}")

        await session.commit()
        return sent_followups

followup_engine = FollowupEngine()
