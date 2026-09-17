import sys
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database.models import (
    OutreachMessage, OutreachStatus, OutreachEvent,
    FollowupSequence, FollowupStatus, Business, PipelineStage, PipelineEvent,
    ConversationEvent, ChannelType, EventDirection, ConversationEventType
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

    async def send_approved_message(self, session: AsyncSession, message_id: int, force_live: bool = False, enforce_window: Optional[bool] = None) -> Dict[str, Any]:
        if getattr(settings, "RESEARCH_ONLY", False):
            raise ValueError("Outreach blocked: System is operating in RESEARCH_ONLY mode.")

        msg = await session.get(OutreachMessage, message_id)
        if not msg:
            raise ValueError(f"Message {message_id} not found.")

        if msg.status == OutreachStatus.SENT.value or msg.sent_at is not None:
            raise ValueError(f"Message {message_id} has already been sent at {msg.sent_at}. Duplicate dispatch is prohibited.")

        if msg.status == OutreachStatus.REJECTED.value:
            raise ValueError(f"Message {message_id} is REJECTED and cannot be dispatched.")

        valid_send_statuses = (
            OutreachStatus.OUTREACH_QUEUED.value,
            OutreachStatus.APPROVED.value,
            OutreachStatus.SEND_ATTEMPTED.value
        )
        if msg.status not in valid_send_statuses:
            raise ValueError(f"Message {message_id} cannot be sent: status is '{msg.status}' (must be APPROVED or OUTREACH_QUEUED).")

        # Record atomic transition to SEND_ATTEMPTED
        msg.status = OutreachStatus.SEND_ATTEMPTED.value
        await session.commit()
        try:
            from app.agents.activity_broadcaster import activity_broadcaster
            await activity_broadcaster.record_event(
                session=session,
                run_id="outreach_dispatch",
                event_type="OUTREACH_SEND_ATTEMPTED",
                message=f"Dispatch attempted for message #{msg.id} to {msg.recipient_email}",
                business_id=msg.business_id,
                status="INFO",
                metadata_json={"message_id": msg.id, "recipient": msg.recipient_email}
            )
        except Exception:
            pass

        # Deterministic Outbound Authorization & Policy Gates
        is_live_send = force_live or (not getattr(settings, "EMAIL_DRY_RUN", True) and not getattr(settings, "DRY_RUN", True))
        if is_live_send:
            is_authorized = (
                force_live
                or msg.actor_type == "HUMAN"
                or (msg.actor_type == "SYSTEM_AUTO_APPROVAL" and getattr(settings, "AUTO_APPROVAL_ENABLED", True))
            )
            if not is_authorized:
                msg.status = OutreachStatus.OUTREACH_BLOCKED.value
                await session.commit()
                raise ValueError("Live email transmission blocked: Explicit human CEO approval or autonomous auto-approval policy required.")

        # Comprehensive 14-Point Pre-Send Safety Evaluation
        from app.outreach.auto_approval import auto_approval_engine
        send_eval = await auto_approval_engine.evaluate_send_authorization(session, msg, force_live=force_live)
        if not send_eval.is_eligible:
            msg.status = OutreachStatus.OUTREACH_BLOCKED.value
            await session.commit()
            try:
                from app.agents.activity_broadcaster import activity_broadcaster
                await activity_broadcaster.record_event(
                    session=session,
                    run_id="outreach_dispatch",
                    event_type="OUTREACH_BLOCKED",
                    message=f"Outbound message #{msg.id} blocked by safety policy: {'; '.join(send_eval.blocking_reasons)}",
                    business_id=msg.business_id,
                    status="WARNING",
                    metadata_json={"message_id": msg.id, "reasons": send_eval.blocking_reasons}
                )
            except Exception:
                pass
            raise ValueError(f"Outbound dispatch blocked by safety policy: {'; '.join(send_eval.blocking_reasons)}")

        # 1. Execution via modular email provider (Titan primary, Resend, SendGrid, SMTP, Gmail)
        primary_provider = (getattr(settings, "PRIMARY_EMAIL_PROVIDER", None) or "titan").lower().strip()
        provider_name = (settings.EMAIL_PROVIDER or primary_provider).lower().strip()
        fallback_provider = (getattr(settings, "FALLBACK_EMAIL_PROVIDER", None) or "").lower().strip()

        if is_live_send:
            if provider_name in ("titan", "titan_smtp"):
                titan_user = getattr(settings, "TITAN_SMTP_USER", None) or getattr(settings, "SMTP_USER", None) or "hello@automatedagencyos.tech"
                titan_pass = getattr(settings, "TITAN_SMTP_PASSWORD", None) or getattr(settings, "SMTP_PASSWORD", None)
                if not titan_user or not titan_pass:
                    raise ValueError(
                        "REAL EMAIL SENDING IS NOT CONFIGURED: Titan SMTP configuration incomplete (TITAN_SMTP_PASSWORD is missing in configuration). "
                        "Primary business outbound is BLOCKED."
                    )
                from app.outreach.providers.titan_provider import TitanEmailProvider
                provider = TitanEmailProvider(smtp_user=titan_user, smtp_password=titan_pass)
            elif provider_name in ("gmail", "gmail_oauth"):
                if fallback_provider not in ("gmail", "gmail_oauth"):
                    raise ValueError(
                        "Outbound dispatch blocked: Gmail OAuth cannot be selected as primary business outbound. "
                        "Normal production business outreach must route via Titan (hello@automatedagencyos.tech). "
                        "Gmail is only permissible if explicitly enabled in FALLBACK_EMAIL_PROVIDER."
                    )
                if not getattr(settings, "GMAIL_CLIENT_ID", None) or not getattr(settings, "GMAIL_REFRESH_TOKEN", None) or not getattr(settings, "GMAIL_CLIENT_SECRET", None):
                    raise ValueError("REAL EMAIL SENDING IS NOT CONFIGURED: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, or GMAIL_REFRESH_TOKEN is not configured in .env")
                from app.outreach.providers.gmail_oauth_provider import GmailOAuthEmailProvider
                provider = GmailOAuthEmailProvider()
            elif provider_name == "resend" or (provider_name == "dry_run" and settings.RESEND_API_KEY):
                if not settings.RESEND_API_KEY:
                    raise ValueError("REAL EMAIL SENDING IS NOT CONFIGURED: RESEND_API_KEY is not configured in .env")
                from app.outreach.providers.resend_provider import ResendEmailProvider
                provider = ResendEmailProvider()
            elif provider_name == "smtp" or (provider_name == "dry_run" and settings.SMTP_HOST):
                if not settings.SMTP_HOST or not settings.SMTP_USER:
                    raise ValueError("REAL EMAIL SENDING IS NOT CONFIGURED: SMTP_HOST and SMTP_USER are not configured in .env")
                from app.outreach.providers.smtp_provider import SMTPEmailProvider
                provider = SMTPEmailProvider()
            elif provider_name == "sendgrid":
                if not settings.SENDGRID_API_KEY:
                    raise ValueError("REAL EMAIL SENDING IS NOT CONFIGURED: SENDGRID_API_KEY is not configured in .env")
                from app.outreach.providers.sendgrid_provider import SendGridEmailProvider
                provider = SendGridEmailProvider()
            else:
                raise ValueError("REAL EMAIL SENDING IS NOT CONFIGURED: No live email credentials configured in .env (configure TITAN_SMTP_PASSWORD, RESEND_API_KEY, or SMTP).")
        else:
            provider = get_email_provider()


        # Stage 1 Canary Outbound Governance: Strictly capacity-governed by daily rollout cap
        if is_live_send:
            from app.campaigns.sender_registry import sender_registry
            cap_summary = await sender_registry.get_sender_capacity_summary(session)
            if cap_summary.get("available_capacity", 0) <= 0:
                raise ValueError(
                    f"Outbound dispatch blocked: Daily sender capacity exhausted for today "
                    f"({cap_summary.get('sent_today', 0)}/{cap_summary.get('rollout_daily_cap', 1)} sent today under {cap_summary.get('rollout_stage_name', 'Canary')}). "
                    f"Sender capacity will reset on next daily window."
                )

        biz = await session.get(Business, msg.business_id) if msg.business_id else None

        # Deterministic Entity Resolution Pre-Send Check
        if biz:
            from app.core.security import normalize_domain
            from app.outreach.composer import CanonicalProspect, EntityResolver
            canon_domain = normalize_domain(biz.domain or "")
            prospect = CanonicalProspect(
                prospect_id=biz.id,
                company_name=biz.name or biz.domain,
                website=biz.domain,
                canonical_company_domain=canon_domain,
                recipient_email=msg.recipient_email,
                recipient_name=getattr(biz, "contact_name", None),
                industry=biz.niche or "Commercial Services",
                city=biz.city,
                country=biz.country or "US",
                phone=biz.phone
            )
            ent_res = EntityResolver.resolve_and_validate(prospect)
            if not ent_res.is_valid:
                raise ValueError(f"Outbound dispatch blocked: {'; '.join(ent_res.errors)}")

        # Resolve matching campaign by country
        from app.campaigns.service import campaign_service
        from app.campaigns.compliance_gate import campaign_compliance_gate

        country_identifier = (biz.country if biz and biz.country else "US").strip()
        campaign = await campaign_service.get_campaign_by_country(session, country_identifier)
        if campaign:
            msg.campaign_id = campaign.id

        # Ensure mandatory CAN-SPAM / international opt-out notice is present on outbound transmission
        if msg.body and not ("unsubscribe" in msg.body.lower() or "opt out" in msg.body.lower() or "opt-out" in msg.body.lower()):
            camp_postal = campaign.postal_address if campaign else None
            if camp_postal and compliance_guard.is_placeholder_address(camp_postal):
                camp_postal = None

            footer_text = compliance_guard.format_compliance_footer(
                business_name=biz.name if biz else "Business",
                recipient_email=msg.recipient_email,
                postal_address=camp_postal,
                force=True
            )
            if footer_text:
                msg.body = msg.body + footer_text

        # Strict 10-Point Deterministic Pre-Send Gate
        gate_res = await campaign_compliance_gate.evaluate_pre_send(
            session=session,
            message=msg,
            campaign=campaign,
            force_live=force_live,
            enforce_window=enforce_window
        )
        if not gate_res.is_eligible:
            msg.status = OutreachStatus.OUTREACH_BLOCKED.value
            if biz and biz.pipeline_stage == PipelineStage.APPROVAL.value:
                biz.pipeline_stage = PipelineStage.LOST.value
                pevent = PipelineEvent(
                    business_id=biz.id,
                    from_stage=PipelineStage.APPROVAL.value,
                    to_stage=PipelineStage.LOST.value,
                    deal_value=0.0,
                    note=f"Outreach blocked by compliance gate: {'; '.join(gate_res.failure_reasons)}"
                )
                session.add(pevent)
            await session.commit()
            try:
                from app.agents.activity_broadcaster import activity_broadcaster
                await activity_broadcaster.record_event(
                    session=session,
                    run_id="outreach_dispatch",
                    event_type="OUTREACH_BLOCKED",
                    message=f"Outreach message #{msg.id} blocked: {'; '.join(gate_res.failure_reasons)}",
                    business_id=msg.business_id,
                    status="WARNING",
                    metadata_json={"message_id": msg.id, "reasons": gate_res.failure_reasons}
                )
            except Exception:
                pass
            raise ValueError(f"Send cancelled: {'; '.join(gate_res.failure_reasons)}")

        # Sender identity resolution: Never invent a persona for owner's real Gmail or Titan
        is_gmail = provider_name in ("gmail", "gmail_oauth") or isinstance(provider, getattr(sys.modules.get("app.outreach.providers.gmail_oauth_provider"), "GmailOAuthEmailProvider", ()))
        is_titan = provider_name in ("titan", "titan_smtp") or isinstance(provider, getattr(sys.modules.get("app.outreach.providers.titan_provider"), "TitanEmailProvider", ()))
        if is_gmail:
            from_email = getattr(settings, "GMAIL_SENDER_EMAIL", None) or settings.EMAIL_FROM
            from_name = None if "Elena Vance" in (settings.EMAIL_FROM_NAME or "") else settings.EMAIL_FROM_NAME
            reply_to = from_email
        elif is_titan:
            from_email = getattr(settings, "TITAN_SMTP_USER", None) or getattr(settings, "SMTP_USER", None) or settings.EMAIL_FROM
            from_name = settings.OUTREACH_FROM_NAME
            reply_to = getattr(settings, "TITAN_SMTP_USER", None) or getattr(settings, "SMTP_USER", None) or getattr(settings, "EMAIL_REPLY_TO", None) or from_email
        else:
            from_email = settings.EMAIL_FROM
            from_name = settings.OUTREACH_FROM_NAME
            reply_to = getattr(settings, "EMAIL_REPLY_TO", None) or from_email

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
            msg.status = OutreachStatus.SEND_FAILED.value
            safe_err = str(e)
            for s in [getattr(settings, "TITAN_SMTP_PASSWORD", None), getattr(settings, "SMTP_PASSWORD", None), getattr(settings, "GMAIL_CLIENT_SECRET", None)]:
                if s and len(s) > 2 and s in safe_err:
                    safe_err = safe_err.replace(s, "[REDACTED]")
            if biz and biz.pipeline_stage == PipelineStage.APPROVAL.value:
                biz.pipeline_stage = PipelineStage.LOST.value
                pevent = PipelineEvent(
                    business_id=biz.id,
                    from_stage=PipelineStage.APPROVAL.value,
                    to_stage=PipelineStage.LOST.value,
                    deal_value=0.0,
                    note=f"Outreach send failed: {safe_err}"
                )
                session.add(pevent)
            await session.commit()
            try:
                from app.agents.activity_broadcaster import activity_broadcaster
                await activity_broadcaster.record_event(
                    session=session,
                    run_id="outreach_dispatch",
                    event_type="OUTREACH_FAILED",
                    message=f"Dispatch failed for message #{msg.id}: {safe_err}",
                    business_id=msg.business_id,
                    status="ERROR",
                    metadata_json={"message_id": msg.id, "error": safe_err}
                )
            except Exception:
                pass
            logger.error(
                f"[LIVE_SEND_FAILURE] message_id={msg.id} lead_id={msg.business_id} "
                f"provider={provider_name} error_class={e.__class__.__name__} "
                f"safe_error_message={safe_err} timestamp={datetime.utcnow().isoformat()}"
            )
            raise RuntimeError(f"Email delivery failed via {provider.__class__.__name__}: {safe_err}")

        if delivery_res.get("status") != "SUCCESS":
            msg.status = OutreachStatus.SEND_FAILED.value
            if biz and biz.pipeline_stage == PipelineStage.APPROVAL.value:
                biz.pipeline_stage = PipelineStage.LOST.value
                pevent = PipelineEvent(
                    business_id=biz.id,
                    from_stage=PipelineStage.APPROVAL.value,
                    to_stage=PipelineStage.LOST.value,
                    deal_value=0.0,
                    note=f"Outreach delivery status unsuccessful: {delivery_res.get('status')}"
                )
                session.add(pevent)
            await session.commit()
            logger.error(
                f"[LIVE_SEND_FAILURE] message_id={msg.id} lead_id={msg.business_id} "
                f"provider={provider_name} error_class=DeliveryStatusError "
                f"safe_error_message={delivery_res} timestamp={datetime.utcnow().isoformat()}"
            )
            raise RuntimeError(f"Email delivery failed via {provider.__class__.__name__}: {delivery_res}")

        if is_live_send:
            event_type = "email_dispatched"
            details = {
                "recipient": msg.recipient_email,
                "sender": from_email,
                "timestamp": datetime.utcnow().isoformat(),
                "provider": provider.__class__.__name__,
                "message_id": delivery_res.get("message_id"),
                "thread_id": delivery_res.get("details", {}).get("gmail_thread_id") or delivery_res.get("details", {}).get("thread_id"),
                "delivery_status": delivery_res.get("delivery_status") or "PROVIDER_ACCEPTED",
                "campaign_id": msg.campaign_id,
                "compliance_result": gate_res.is_eligible,
                "approval_record": {
                    "approved_at": msg.approved_at.isoformat() if msg.approved_at else datetime.utcnow().isoformat(),
                    "authorized_by": "CEO",
                    "explicit_authorization": True
                },
                "dry_run": False
            }
        else:
            event_type = "dry_run_simulated"
            details = dict(delivery_res.get("details", {}))
            details["dry_run"] = True
            details["simulated"] = True

        # 2. Update status and log event
        msg.status = OutreachStatus.SENT.value
        msg.sent_at = datetime.utcnow()
        if delivery_res.get("message_id"):
            msg.provider_message_id = delivery_res.get("message_id")
        msg.provider = provider_name
        if reply_to:
            msg.reply_to = reply_to

        event_log = OutreachEvent(
            outreach_message_id=msg.id,
            event_type=event_type,
            details=details
        )
        session.add(event_log)

        try:
            from app.agents.activity_broadcaster import activity_broadcaster
            await activity_broadcaster.record_event(
                session=session,
                run_id="outreach_dispatch",
                event_type="OUTREACH_SENT",
                message=f"Outreach message #{msg.id} dispatched successfully to {msg.recipient_email} via {provider.__class__.__name__}",
                business_id=msg.business_id,
                domain=biz.domain if biz else None,
                status="SUCCESS",
                metadata_json={
                    "message_id": msg.id,
                    "recipient": msg.recipient_email,
                    "provider": provider.__class__.__name__,
                    "provider_message_id": delivery_res.get("message_id")
                }
            )
        except Exception:
            pass

        conv_event = ConversationEvent(
            business_id=msg.business_id,
            channel=ChannelType.EMAIL.value,
            direction=EventDirection.OUTBOUND.value,
            provider=provider.__class__.__name__,
            provider_event_id=str(delivery_res.get("message_id") or f"outreach_{msg.id}"),
            event_type=ConversationEventType.SENT.value,
            content=f"Subject: {msg.subject}\n\n{msg.body}",
            idempotency_key=f"email_send_{msg.id}_{delivery_res.get('message_id') or int(datetime.utcnow().timestamp())}",
            metadata_json={
                "outreach_message_id": msg.id,
                "recipient_email": msg.recipient_email,
                "subject": msg.subject,
                "provider": provider.__class__.__name__,
                "is_live_send": is_live_send,
                "delivery_res": delivery_res
            }
        )
        session.add(conv_event)

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

        # 4. Transition Pipeline Stage to CONTACTED and update ProspectMemory
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

            # Sync ProspectMemory with real threadId, provider message ID, and status
            try:
                from app.crm.memory_service import memory_service
                real_thread_id = details.get("thread_id") or delivery_res.get("details", {}).get("gmail_thread_id")
                await memory_service.save_memory(
                    session=session,
                    business_id=biz.id,
                    domain=biz.domain,
                    contact_email=msg.recipient_email,
                    thread_id=real_thread_id,
                    channel_used="EMAIL",
                    pipeline_stage=PipelineStage.CONTACTED.value,
                    outreach_message={
                        "message_id": msg.id,
                        "provider_message_id": delivery_res.get("message_id"),
                        "thread_id": real_thread_id,
                        "recipient": msg.recipient_email,
                        "subject": msg.subject,
                        "body": msg.body,
                        "sent_at": msg.sent_at.isoformat() if msg.sent_at else datetime.utcnow().isoformat(),
                        "provider": provider.__class__.__name__
                    },
                    last_interaction=f"Outreach email dispatched to {msg.recipient_email} (Msg ID: {delivery_res.get('message_id')})",
                    next_expected_action="AWAITING_REPLY"
                )
            except Exception as mem_err:
                logger.warning(f"[OutreachSender] Note updating ProspectMemory for #{biz.id}: {mem_err}")

        await session.commit()
        return {"status": "SUCCESS", "message_id": msg.id, "event": event_type, "details": details}

outreach_sender_adapter = OutreachSenderAdapter()
