import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import (
    OutreachMessage, OutreachStatus, OutreachEvent,
    FollowupSequence, FollowupStatus, Business, PipelineStage, PipelineEvent
)
from app.core.config import settings
from app.core.logging import logger
from app.outreach.compliance import compliance_guard
from app.outreach.providers.factory import get_email_provider

class OutreachSenderAdapter:
    """
    Executes approved outreach.
    Respects DRY_RUN safety mode (default):
    - When DRY_RUN=True: Records simulated delivery events without opening external SMTP sockets.
    - When DRY_RUN=False: Transmits via configured SMTP provider.
    Schedules automated follow-up cadences upon successful transmission.
    """

    async def send_approved_message(self, session: AsyncSession, message_id: int) -> Dict[str, Any]:
        msg = await session.get(OutreachMessage, message_id)
        if not msg:
            raise ValueError(f"Message {message_id} not found.")

        if msg.status == OutreachStatus.SENT.value or msg.sent_at is not None:
            raise ValueError(f"Message {message_id} has already been sent at {msg.sent_at}. Duplicate dispatch is prohibited.")

        if msg.status != OutreachStatus.APPROVED.value:
            raise ValueError(f"Message {message_id} cannot be sent: status is '{msg.status}' (must be APPROVED).")

        # Check suppression
        if await compliance_guard.is_suppressed(session, msg.recipient_email):
            msg.status = OutreachStatus.FAILED.value
            await session.commit()
            raise ValueError(f"Send cancelled: {msg.recipient_email} is on suppression list.")

        # Check daily limits
        if not await compliance_guard.can_send_today(session):
            raise ValueError("Daily outreach limit (MAX_OUTREACH_PER_DAY) reached.")

        biz = await session.get(Business, msg.business_id)

        # 1. Execution via modular email provider (DryRun, Resend, SendGrid, SMTP)
        provider = get_email_provider()
        try:
            delivery_res = await provider.send_email(
                to_email=msg.recipient_email,
                subject=msg.subject,
                body=msg.body,
                from_email=settings.EMAIL_FROM,
                from_name=settings.OUTREACH_FROM_NAME,
                reply_to=settings.EMAIL_REPLY_TO
            )
        except Exception as e:
            msg.status = OutreachStatus.FAILED.value
            await session.commit()
            raise RuntimeError(f"Email delivery failed via {provider.__class__.__name__}: {e}")

        if delivery_res.get("status") != "SUCCESS":
            msg.status = OutreachStatus.FAILED.value
            await session.commit()
            raise RuntimeError(f"Email delivery failed via {provider.__class__.__name__}: {delivery_res}")

        event_type = delivery_res.get("event", "email_dispatched")
        details = delivery_res.get("details", {})

        # 2. Update status and log event
        msg.status = OutreachStatus.SENT.value
        msg.sent_at = datetime.utcnow()

        event_log = OutreachEvent(
            outreach_message_id=msg.id,
            event_type=event_type,
            details=details
        )
        session.add(event_log)

        # 3. Schedule 3-step follow-up sequence
        followup_templates = [
            (3, "Following up regarding my previous note", f"Hi there,\n\nJust wanted to make sure my previous note regarding {biz.domain if biz else 'your website'} didn't get buried.\n\nDid you have a chance to look at the diagnostic observation?"),
            (7, "Quick resource for your web team", f"Hello,\n\nI put together a quick checklist outlining how to resolve the mobile conversion issue on {biz.domain if biz else 'your site'}.\n\nWould you like me to send it over?"),
            (14, "Final follow-up regarding website optimization", f"Hi there,\n\nI haven't heard back, so I assume this isn't a priority right now. I won't follow up further, but feel free to reach out if you'd like to revisit your mobile conversion and SEO presence down the road.\n\nBest regards,\n{settings.OUTREACH_FROM_NAME}")
        ]

        for delay_days, f_subj, f_body in followup_templates:
            fu = FollowupSequence(
                initial_message_id=msg.id,
                step_number=len(followup_templates),
                delay_days=delay_days,
                scheduled_for=datetime.utcnow() + timedelta(days=delay_days),
                subject=f_subj,
                body=f_body,
                status=FollowupStatus.SCHEDULED.value
            )
            session.add(fu)

        # 4. Transition Pipeline Stage to CONTACTED
        if biz:
            old_stage = biz.pipeline_stage
            biz.pipeline_stage = PipelineStage.CONTACTED.value
            pevent = PipelineEvent(
                business_id=biz.id,
                from_stage=old_stage,
                to_stage=PipelineStage.CONTACTED.value,
                deal_value=0.0,
                note=f"Initial outreach transmitted ({'DRY_RUN simulated' if settings.DRY_RUN else 'Live SMTP'}). Follow-up sequence scheduled."
            )
            session.add(pevent)

        await session.commit()
        return {"status": "SUCCESS", "message_id": msg.id, "event": event_type, "details": details}

outreach_sender_adapter = OutreachSenderAdapter()
