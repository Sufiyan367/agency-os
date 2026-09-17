from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import OutreachMessage, OutreachStatus, PipelineStage, Business, PipelineEvent
from app.core.logging import logger

class OutreachApprovalQueue:
    """
    Manages the human-in-the-loop approval queue for outbound outreach.
    Enforces strict authorization and idempotent canonical state transitions:
    PENDING_APPROVAL -> APPROVED -> OUTREACH_QUEUED.
    Guarantees REJECTED or SENT messages can never be queued.
    """

    async def list_pending(self, session: AsyncSession) -> List[OutreachMessage]:
        from app.core.safety_filters import get_synthetic_outreach_filter_clauses
        filters = get_synthetic_outreach_filter_clauses(OutreachMessage)
        q = select(OutreachMessage).where(
            OutreachMessage.status == OutreachStatus.PENDING_APPROVAL.value,
            *filters
        ).order_by(OutreachMessage.created_at.desc())
        return list((await session.execute(q)).scalars().all())

    async def list_queued(self, session: AsyncSession) -> List[OutreachMessage]:
        from app.core.safety_filters import get_synthetic_outreach_filter_clauses
        filters = get_synthetic_outreach_filter_clauses(OutreachMessage)
        q = select(OutreachMessage).where(
            OutreachMessage.status.in_([
                OutreachStatus.OUTREACH_QUEUED.value,
                OutreachStatus.APPROVED.value
            ]),
            *filters
        ).order_by(OutreachMessage.created_at.asc())
        return list((await session.execute(q)).scalars().all())

    async def approve_message(self, session: AsyncSession, message_id: int, actor_type: str = "CEO_HUMAN") -> OutreachMessage:
        """
        Canonical single approval operation:
        1. Verifies message exists.
        2. Guards against illegal transitions (SENT or REJECTED).
        3. Idempotently handles already APPROVED or OUTREACH_QUEUED states without duplicate side effects.
        4. Persists approval metadata.
        5. Atomically transitions PENDING_APPROVAL -> APPROVED -> OUTREACH_QUEUED.
        6. Emits OUTREACH_APPROVED and OUTREACH_QUEUED telemetry events.
        """
        msg = await session.get(OutreachMessage, message_id)
        if not msg:
            raise ValueError(f"OutreachMessage {message_id} not found.")

        # Permanently protect SENT and REJECTED messages
        if msg.status == OutreachStatus.SENT.value or msg.sent_at is not None:
            raise ValueError(f"OutreachMessage #{message_id} has already been sent (SENT). Duplicate dispatch is prohibited.")

        if msg.status == OutreachStatus.REJECTED.value:
            raise ValueError(f"OutreachMessage #{message_id} is REJECTED. Rejected messages cannot be approved or dispatched.")

        # Idempotency check: Already queued or approved
        if msg.status == OutreachStatus.OUTREACH_QUEUED.value:
            logger.info(f"[ApprovalQueue] Idempotent approval: message #{message_id} is already in OUTREACH_QUEUED state.")
            return msg

        # Transition: PENDING_APPROVAL / APPROVED -> OUTREACH_QUEUED
        msg.actor_type = actor_type
        if not msg.approved_at:
            msg.approved_at = datetime.utcnow()

        msg.status = OutreachStatus.OUTREACH_QUEUED.value

        # Update business pipeline stage to APPROVAL / OUTREACH_READY
        biz = await session.get(Business, msg.business_id) if msg.business_id else None
        if biz:
            biz.pipeline_stage = PipelineStage.APPROVAL.value
            event = PipelineEvent(
                business_id=biz.id,
                from_stage=PipelineStage.QUALIFIED.value,
                to_stage=PipelineStage.APPROVAL.value,
                deal_value=0.0,
                note=f"Outreach draft approved by {actor_type} and queued for dispatch (OUTREACH_QUEUED)."
            )
            session.add(event)

        # Broadcast telemetry events for real-time dashboard observation
        try:
            from app.agents.activity_broadcaster import activity_broadcaster
            await activity_broadcaster.record_event(
                session=session,
                run_id="outreach_approval",
                event_type="OUTREACH_APPROVED",
                message=f"Outreach message #{msg.id} approved by {actor_type} ({msg.recipient_email})",
                business_id=msg.business_id,
                domain=biz.domain if biz else None,
                status="SUCCESS",
                metadata_json={"message_id": msg.id, "actor": actor_type, "recipient": msg.recipient_email}
            )
            await activity_broadcaster.record_event(
                session=session,
                run_id="outreach_queue",
                event_type="OUTREACH_QUEUED",
                message=f"Outreach message #{msg.id} placed in durable dispatch queue",
                business_id=msg.business_id,
                domain=biz.domain if biz else None,
                status="SUCCESS",
                metadata_json={"message_id": msg.id, "recipient": msg.recipient_email}
            )
        except Exception as tel_err:
            logger.debug(f"[ApprovalQueue] Telemetry broadcast skipped: {tel_err}")

        await session.commit()
        await session.refresh(msg)
        logger.info(f"Approved and queued message #{message_id} for recipient {msg.recipient_email} (actor={actor_type})")
        return msg

    async def reject_message(self, session: AsyncSession, message_id: int, reason: str = "") -> OutreachMessage:
        msg = await session.get(OutreachMessage, message_id)
        if not msg:
            raise ValueError(f"OutreachMessage {message_id} not found.")

        if msg.status == OutreachStatus.SENT.value or msg.sent_at is not None:
            raise ValueError(f"OutreachMessage #{message_id} has already been sent (SENT). Sent messages cannot be rejected.")

        msg.status = OutreachStatus.REJECTED.value

        biz = await session.get(Business, msg.business_id) if msg.business_id else None
        if biz:
            old_stage = biz.pipeline_stage
            biz.pipeline_stage = PipelineStage.REJECTED.value
            pevent = PipelineEvent(
                business_id=biz.id,
                from_stage=old_stage,
                to_stage=PipelineStage.REJECTED.value,
                deal_value=0.0,
                note=f"Outreach message #{msg.id} rejected by operator. Reason: {reason or 'Manual operator rejection'}"
            )
            session.add(pevent)

        try:
            from app.agents.activity_broadcaster import activity_broadcaster
            await activity_broadcaster.record_event(
                session=session,
                run_id="outreach_rejection",
                event_type="OUTREACH_REJECTED",
                message=f"Outreach message #{msg.id} rejected. Reason: {reason or 'Manual operator rejection'}",
                business_id=msg.business_id,
                domain=biz.domain if biz else None,
                status="WARNING",
                metadata_json={"message_id": msg.id, "reason": reason}
            )
        except Exception:
            pass

        await session.commit()
        await session.refresh(msg)
        logger.info(f"Rejected message #{message_id}: {reason}")
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

