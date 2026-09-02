from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import FollowupSequence, FollowupStatus, OutreachMessage, Business
from app.core.logging import logger

class FollowupEngine:
    """
    Manages automated follow-up sequences.
    Enforces automatic cancellation when replies, unsubscribes, or bounces occur.
    """

    async def cancel_pending_followups(
        self, session: AsyncSession, business_id: int, reason_status: FollowupStatus
    ):
        """Cancels all scheduled follow-ups for a business upon reply or opt-out."""
        q = select(FollowupSequence).join(OutreachMessage).where(
            OutreachMessage.business_id == business_id,
            FollowupSequence.status == FollowupStatus.SCHEDULED.value
        )
        followups = (await session.execute(q)).scalars().all()
        for fu in followups:
            fu.status = reason_status.value
            logger.info(f"Follow-up ID {fu.id} cancelled with status: {reason_status.value}")
        await session.commit()

    async def process_due_followups(self, session: AsyncSession) -> List[FollowupSequence]:
        """Identifies and processes due follow-up messages."""
        now = datetime.utcnow()
        q = select(FollowupSequence).where(
            FollowupSequence.status == FollowupStatus.SCHEDULED.value,
            FollowupSequence.scheduled_for <= now
        )
        due = list((await session.execute(q)).scalars().all())
        # In actual scheduler, sends due items. In dry-run, marks sent.
        for item in due:
            item.status = FollowupStatus.SENT.value
            item.sent_at = now
        await session.commit()
        return due

followup_engine = FollowupEngine()
