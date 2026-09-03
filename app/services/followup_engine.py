from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.entities import Lead, FollowupSchedule, LeadEvent, EventType, FollowupStatus, LeadStatus
from app.providers.base import BaseMessageProvider
from app.providers.factory import get_message_provider

class FollowUpEngine:
    """
    Configurable follow-up sequencing engine with time-compression test mode.
    Enforces auto-stop on reply, booking, opt-out, or human takeover.
    Guarantees duplicate prevention.
    """

    DEFAULT_CADENCE_DAYS = [2, 4, 7]

    def __init__(
        self,
        msg_provider: Optional[BaseMessageProvider] = None,
        cadence_days: Optional[List[int]] = None,
        time_compression_factor: float = 1.0
    ):
        """
        :param time_compression_factor: 1.0 for normal real-time.
               For test mode, e.g. 1440.0 compresses 1 day into 60 real seconds.
               Or 86400.0 compresses 1 day into 1 second.
        """
        self.msg_provider = msg_provider or get_message_provider()
        self.cadence_days = cadence_days or self.DEFAULT_CADENCE_DAYS
        self.time_compression_factor = max(1.0, time_compression_factor)

    def calculate_scheduled_time(self, base_time: datetime, days_delay: int) -> datetime:
        total_seconds = (days_delay * 86400) / self.time_compression_factor
        return base_time + timedelta(seconds=total_seconds)

    async def schedule_sequence_for_lead(
        self,
        db: AsyncSession,
        lead_id: int,
        base_time: Optional[datetime] = None
    ) -> List[FollowupSchedule]:
        # 1. Duplicate check: verify no active/pending followups already exist
        existing = await db.execute(
            select(FollowupSchedule).where(
                and_(
                    FollowupSchedule.lead_id == lead_id,
                    FollowupSchedule.status == FollowupStatus.PENDING.value
                )
            )
        )
        if existing.scalars().first() is not None:
            raise ValueError(f"Follow-up sequence already active for lead {lead_id} (duplicate prevented)")

        lead_res = await db.execute(select(Lead).where(Lead.id == lead_id))
        lead = lead_res.scalar_one_or_none()
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        start = base_time or datetime.utcnow()
        created_schedules: List[FollowupSchedule] = []

        templates = [
            (
                "Quick follow-up on your website diagnostic",
                f"Hi {lead.contact_name},\n\n"
                f"Just wanted to follow up on the technical diagnostic we prepared for {lead.business.name if lead.business else 'your business'}.\n"
                f"Did you have a chance to look over the site speed and SEO notes?\n\n"
                f"Happy to walk through the highest-impact fixes whenever convenient.\n\n"
                f"Best,\nElena Vance"
            ),
            (
                "Ideas to improve homeowner call conversion for your site",
                f"Hi {lead.contact_name},\n\n"
                f"Checking in briefly. We've seen local service businesses recover an extra 15-20% in customer inquiries "
                f"simply by resolving mobile viewport bottlenecks like the ones we spotted on your domain.\n\n"
                f"Let me know if you'd like the direct checklist.\n\n"
                f"Best,\nElena Vance"
            ),
            (
                "Closing your website diagnostic file",
                f"Hi {lead.contact_name},\n\n"
                f"I assume improving web conversion isn't a current priority right now, so I'll close out your file "
                f"and won't follow up again.\n\n"
                f"If you ever want to revisit the technical review in the future, feel free to reach back out.\n\n"
                f"Best of luck with business!\nElena Vance"
            )
        ]

        accumulated_days = 0
        for i, days_gap in enumerate(self.cadence_days):
            accumulated_days += days_gap
            target_time = self.calculate_scheduled_time(start, accumulated_days)
            subj, body = templates[min(i, len(templates) - 1)]

            schedule = FollowupSchedule(
                lead_id=lead.id,
                step_number=i + 1,
                scheduled_for=target_time,
                status=FollowupStatus.PENDING.value,
                subject=subj,
                body=body
            )
            db.add(schedule)
            created_schedules.append(schedule)

        event = LeadEvent(
            lead_id=lead.id,
            event_type=EventType.FOLLOWUP_SCHEDULED.value,
            payload={
                "steps_scheduled": len(created_schedules),
                "time_compression_factor": self.time_compression_factor,
                "first_scheduled_for": created_schedules[0].scheduled_for.isoformat()
            }
        )
        db.add(event)
        await db.commit()
        return created_schedules

    async def cancel_followups_for_lead(
        self,
        db: AsyncSession,
        lead_id: int,
        reason: str
    ) -> int:
        result = await db.execute(
            select(FollowupSchedule).where(
                and_(
                    FollowupSchedule.lead_id == lead_id,
                    FollowupSchedule.status == FollowupStatus.PENDING.value
                )
            )
        )
        pending = result.scalars().all()
        count = 0
        for item in pending:
            item.status = FollowupStatus.CANCELLED_TAKEOVER.value if "takeover" in reason.lower() else FollowupStatus.CANCELLED_REPLY.value
            item.cancel_reason = reason
            count += 1

        if count > 0:
            event = LeadEvent(
                lead_id=lead_id,
                event_type=EventType.FOLLOWUP_CANCELLED.value,
                payload={"cancelled_count": count, "reason": reason}
            )
            db.add(event)
            await db.commit()

        return count

    async def process_due_followups(
        self,
        db: AsyncSession,
        now: Optional[datetime] = None
    ) -> List[FollowupSchedule]:
        current_time = now or datetime.utcnow()
        result = await db.execute(
            select(FollowupSchedule).where(
                and_(
                    FollowupSchedule.status == FollowupStatus.PENDING.value,
                    FollowupSchedule.scheduled_for <= current_time
                )
            )
        )
        due_items = result.scalars().all()
        executed: List[FollowupSchedule] = []

        for item in due_items:
            lead_res = await db.execute(select(Lead).where(Lead.id == item.lead_id))
            lead = lead_res.scalar_one_or_none()
            if not lead:
                continue

            # Auto-stop Check 1: Human takeover active
            if lead.human_takeover:
                item.status = FollowupStatus.CANCELLED_TAKEOVER.value
                item.cancel_reason = f"Human takeover active: {lead.human_takeover_reason}"
                continue

            # Auto-stop Check 2: Lead replied, booked, or opted out
            if lead.status in (LeadStatus.REPLIED.value, LeadStatus.BOOKED.value, LeadStatus.OPT_OUT.value, LeadStatus.LOST.value):
                item.status = FollowupStatus.CANCELLED_REPLY.value
                item.cancel_reason = f"Lead lifecycle stage: {lead.status}"
                continue

            # Safe mock dispatch
            delivery = await self.msg_provider.send_message(
                recipient=lead.contact_email,
                subject=item.subject,
                body=item.body,
                lead_id=item.lead_id,
                channel="EMAIL",
                metadata={"step_number": item.step_number}
            )

            item.status = FollowupStatus.SENT.value
            item.sent_at = delivery.sent_at
            executed.append(item)

            event = LeadEvent(
                lead_id=lead.id,
                event_type=EventType.FOLLOWUP_EXECUTED.value,
                payload={
                    "followup_id": item.id,
                    "step_number": item.step_number,
                    "provider_message_id": delivery.message_id
                }
            )
            db.add(event)

        await db.commit()
        return executed
