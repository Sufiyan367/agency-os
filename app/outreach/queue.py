from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import OutreachMessage, OutreachStatus, PipelineStage, Business, PipelineEvent
from app.core.logging import logger

class OutreachApprovalQueue:
    """
    Manages the human-in-the-loop approval queue for outbound outreach.
    Enforces strict authorization: Only APPROVED messages can be sent.
    """

    async def list_pending(self, session: AsyncSession) -> List[OutreachMessage]:
        q = select(OutreachMessage).where(
            OutreachMessage.status == OutreachStatus.PENDING_APPROVAL.value
        ).order_by(OutreachMessage.created_at.desc())
        return list((await session.execute(q)).scalars().all())

    async def approve_message(self, session: AsyncSession, message_id: int, actor_type: str = "HUMAN") -> OutreachMessage:
        msg = await session.get(OutreachMessage, message_id)
        if not msg:
            raise ValueError(f"OutreachMessage {message_id} not found.")

        msg.status = OutreachStatus.APPROVED.value
        msg.approved_at = datetime.utcnow()
        msg.actor_type = actor_type

        # Update business pipeline stage to APPROVAL / OUTREACH_READY
        biz = await session.get(Business, msg.business_id)
        if biz:
            biz.pipeline_stage = PipelineStage.APPROVAL.value
            event = PipelineEvent(
                business_id=biz.id,
                from_stage=PipelineStage.QUALIFIED.value,
                to_stage=PipelineStage.APPROVAL.value,
                deal_value=0.0,
                note=f"Outreach draft approved by {actor_type}."
            )
            session.add(event)

        await session.commit()
        logger.info(f"Approved message {message_id} for recipient {msg.recipient_email} (actor={actor_type})")
        return msg

    async def reject_message(self, session: AsyncSession, message_id: int, reason: str = "") -> OutreachMessage:
        msg = await session.get(OutreachMessage, message_id)
        if not msg:
            raise ValueError(f"OutreachMessage {message_id} not found.")

        msg.status = OutreachStatus.REJECTED.value
        await session.commit()
        logger.info(f"Rejected message {message_id}: {reason}")
        return msg

    async def hold_message(self, session: AsyncSession, message_id: int) -> OutreachMessage:
        msg = await session.get(OutreachMessage, message_id)
        if not msg:
            raise ValueError(f"OutreachMessage {message_id} not found.")

        msg.status = OutreachStatus.HELD.value
        await session.commit()
        return msg

    async def edit_message(
        self, session: AsyncSession, message_id: int, new_subject: str, new_body: str
    ) -> OutreachMessage:
        msg = await session.get(OutreachMessage, message_id)
        if not msg:
            raise ValueError(f"OutreachMessage {message_id} not found.")

        msg.subject = new_subject
        msg.body = new_body
        await session.commit()
        return msg

    async def reset_to_pending(
        self, session: AsyncSession, message_id: int, reason: str = ""
    ) -> OutreachMessage:
        """
        Resets an outreach message back to PENDING_APPROVAL and clears approved_at.
        Ensures state consistency across OutreachMessage and PipelineEvent.
        """
        msg = await session.get(OutreachMessage, message_id)
        if not msg:
            raise ValueError(f"OutreachMessage {message_id} not found.")

        msg.status = OutreachStatus.PENDING_APPROVAL.value
        msg.approved_at = None

        biz = await session.get(Business, msg.business_id)
        if biz:
            biz.pipeline_stage = PipelineStage.APPROVAL.value
            event = PipelineEvent(
                business_id=biz.id,
                from_stage=biz.pipeline_stage,
                to_stage=PipelineStage.APPROVAL.value,
                deal_value=0.0,
                note=f"Outreach draft staged. Awaiting human CEO review and approval (PENDING_APPROVAL). {reason}".strip()
            )
            session.add(event)

        await session.commit()
        logger.info(f"Reset message {message_id} to PENDING_APPROVAL: {reason}")
        return msg

outreach_approval_queue = OutreachApprovalQueue()

