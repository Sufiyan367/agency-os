import sys
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

    async def send_approved_message(self, session: AsyncSession, message_id: int, force_live: bool = False) -> Dict[str, Any]:
        if getattr(settings, "RESEARCH_ONLY", False):
            raise ValueError("Outreach blocked: System is operating in RESEARCH_ONLY mode.")

        msg = await session.get(OutreachMessage, message_id)
        if not msg:
            raise ValueError(f"Message {message_id} not found.")

        if msg.status == OutreachStatus.SENT.value or msg.sent_at is not None:
            raise ValueError(f"Message {message_id} has already been sent at {msg.sent_at}. Duplicate dispatch is prohibited.")

        if msg.status != OutreachStatus.APPROVED.value:
            raise ValueError(f"Message {message_id} cannot be sent: status is '{msg.status}' (must be APPROVED).")

        # Phase 7 Outbound Safety Lock: Live outbound transmission requires explicit human CEO authorization
        if not getattr(settings, "EMAIL_DRY_RUN", True) and not force_live:
            raise ValueError("Live email transmission blocked: Explicit human CEO approval required.")

        # Check suppression
        if await compliance_guard.is_suppressed(session, msg.recipient_email):
            msg.status = OutreachStatus.FAILED.value
            await session.commit()
            raise ValueError(f"Send cancelled: {msg.recipient_email} is on suppression list.")

        # Check daily limits
        if not await compliance_guard.can_send_today(session):
            raise ValueError("Daily outreach limit (MAX_OUTREACH_PER_DAY) reached.")

        biz = await session.get(Business, msg.business_id)

        # 1. Execution via modular email provider (DryRun, Resend, SendGrid, SMTP, Gmail)
        provider_name = (settings.EMAIL_PROVIDER or "").lower().strip()
        if force_live:
            if provider_name in ("gmail", "gmail_oauth"):
                if not getattr(settings, "GMAIL_CLIENT_ID", None) or not getattr(settings, "GMAIL_REFRESH_TOKEN", None) or not getattr(settings, "GMAIL_CLIENT_SECRET", None):
                    raise ValueError("Cannot send live: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, or GMAIL_REFRESH_TOKEN is not configured in .env")
                from app.outreach.providers.gmail_oauth_provider import GmailOAuthEmailProvider
                provider = GmailOAuthEmailProvider()
            elif provider_name == "resend" or (provider_name == "dry_run" and settings.RESEND_API_KEY):
                if not settings.RESEND_API_KEY:
                    raise ValueError("Cannot send live: RESEND_API_KEY is not configured in .env")
                from app.outreach.providers.resend_provider import ResendEmailProvider
                provider = ResendEmailProvider()
            elif provider_name == "smtp" or (provider_name == "dry_run" and settings.SMTP_HOST):
                if not settings.SMTP_HOST or not settings.SMTP_USER:
                    raise ValueError("Cannot send live: SMTP_HOST and SMTP_USER are not configured in .env")
                from app.outreach.providers.smtp_provider import SMTPEmailProvider
                provider = SMTPEmailProvider()
            elif provider_name == "sendgrid":
                if not settings.SENDGRID_API_KEY:
                    raise ValueError("Cannot send live: SENDGRID_API_KEY is not configured in .env")
                from app.outreach.providers.sendgrid_provider import SendGridEmailProvider
                provider = SendGridEmailProvider()
            else:
                raise ValueError("Cannot send live: No live email credentials configured in .env (configure GMAIL OAuth, RESEND_API_KEY, or SMTP).")
        else:
            provider = get_email_provider()

        # Sender identity resolution: Never invent a persona for owner's real Gmail
        is_gmail = provider_name in ("gmail", "gmail_oauth") or isinstance(provider, getattr(sys.modules.get("app.outreach.providers.gmail_oauth_provider"), "GmailOAuthEmailProvider", ()))
        if is_gmail:
            from_email = getattr(settings, "GMAIL_SENDER_EMAIL", None) or settings.EMAIL_FROM
            # Do not use placeholder Elena Vance for personal Gmail
            from_name = None if "Elena Vance" in (settings.EMAIL_FROM_NAME or "") else settings.EMAIL_FROM_NAME
            reply_to = from_email
        else:
            from_email = settings.EMAIL_FROM
            from_name = settings.OUTREACH_FROM_NAME
            reply_to = settings.EMAIL_REPLY_TO

        try:
            delivery_res = await provider.send_email(
                to_email=msg.recipient_email,
                subject=msg.subject,
                body=msg.body,
                from_email=from_email,
                from_name=from_name,
                reply_to=reply_to
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
