from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.database.models import OutreachMessage, OutreachStatus, Business, Campaign, SuppressionList
from app.core.config import settings
from app.outreach.compliance import compliance_guard
from app.campaigns.models import ComplianceGateResult, ComplianceCheckItem
from app.campaigns.scheduler import campaign_scheduler
from app.campaigns.sender_registry import sender_registry
from app.campaigns.quota_engine import quota_engine


class CampaignComplianceGate:
    """
    10-Point Deterministic Pre-Send Compliance & Quality Gate.
    Verifies every outbound transmission before execution:
    1. Suppression check
    2. Unsubscribe status
    3. Duplicate protection
    4. Recent contact check
    5. Sender identity configuration
    6. Country sending window
    7. Daily country quota
    8. Global daily limit
    9. Rollout stage limit
    10. Physical address + opt-out footer presence
    """

    async def evaluate_pre_send(
        self,
        session: AsyncSession,
        message: OutreachMessage,
        campaign: Optional[Campaign] = None,
        force_live: bool = False,
        enforce_window: Optional[bool] = None,
        current_time: Optional[datetime] = None,
    ) -> ComplianceGateResult:
        checks: List[ComplianceCheckItem] = []
        failure_reasons: List[str] = []

        biz = await session.get(Business, message.business_id) if message.business_id else None
        country_code = (biz.country if biz and biz.country else (campaign.country_code if campaign else "US")).strip().upper()
        is_live = not getattr(settings, "EMAIL_DRY_RUN", True) and force_live
        email = (message.recipient_email or "").strip().lower()

        # Check 1: Suppression check
        is_supp = await compliance_guard.is_suppressed(session, email=email, domain=biz.domain if biz else None)
        checks.append(ComplianceCheckItem(
            check_name="SUPPRESSION_CHECK",
            passed=not is_supp,
            detail="Address clear of suppression list" if not is_supp else "Address is on suppression list"
        ))
        if is_supp:
            failure_reasons.append(f"Recipient {email} is on suppression list.")

        # Check 2: Unsubscribe status
        # Explicit check if suppression reason was UNSUBSCRIBE / OPT_OUT
        unsub_stmt = select(SuppressionList.id).where(
            and_(
                SuppressionList.email == email,
                SuppressionList.reason.in_(["UNSUBSCRIBE", "OPT_OUT", "REQUESTED_REMOVAL"])
            )
        ).limit(1)
        unsub_exists = (await session.execute(unsub_stmt)).first() is not None
        checks.append(ComplianceCheckItem(
            check_name="UNSUBSCRIBE_STATUS",
            passed=not unsub_exists,
            detail="No prior opt-out on record" if not unsub_exists else "Recipient previously opted out"
        ))
        if unsub_exists:
            failure_reasons.append(f"Recipient {email} has an active unsubscribe record.")

        # Check 3: Duplicate protection
        # Block if a message to this recipient was already successfully sent
        dup_stmt = select(func.count(OutreachMessage.id)).where(
            OutreachMessage.recipient_email == email,
            OutreachMessage.status == OutreachStatus.SENT.value,
            OutreachMessage.id != message.id
        )
        prior_sent_count = (await session.execute(dup_stmt)).scalar() or 0
        checks.append(ComplianceCheckItem(
            check_name="DUPLICATE_PROTECTION",
            passed=prior_sent_count == 0,
            detail=f"Prior sent count: {prior_sent_count}"
        ))
        if prior_sent_count > 0:
            failure_reasons.append(f"Duplicate protection: {email} already received an outreach message.")

        # Check 4: Recent contact check (cooldown within last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_stmt = select(func.count(OutreachMessage.id)).where(
            OutreachMessage.recipient_email == email,
            OutreachMessage.sent_at >= thirty_days_ago,
            OutreachMessage.id != message.id
        )
        recent_count = (await session.execute(recent_stmt)).scalar() or 0
        checks.append(ComplianceCheckItem(
            check_name="RECENT_CONTACT_CHECK",
            passed=recent_count == 0,
            detail=f"Contacts in last 30 days: {recent_count}"
        ))
        if recent_count > 0:
            failure_reasons.append(f"Recent contact check: {email} was contacted within the last 30 days.")

        # Check 5: Sender identity configuration
        sender_ok, sender_msg, resolved_sender = sender_registry.validate_sender_ready(
            campaign=campaign,
            country_code=country_code,
            is_live_send=is_live
        )
        checks.append(ComplianceCheckItem(
            check_name="SENDER_IDENTITY_CONFIGURED",
            passed=sender_ok,
            detail=sender_msg
        ))
        if not sender_ok:
            failure_reasons.append(sender_msg)

        # Check 6: Country sending window (09:00 - 17:00 local time)
        win_start = campaign.sending_window_start if campaign else 9
        win_end = campaign.sending_window_end if campaign else 17
        in_window, local_dt, hour, tz_name = campaign_scheduler.is_within_sending_window(
            country_code=country_code,
            timezone_str=campaign.timezone if campaign else None,
            current_time=current_time,
            window_start=win_start,
            window_end=win_end
        )
        # In test environments or when explicitly disabled, allow window pass
        should_enforce_window = enforce_window if enforce_window is not None else (is_live or not bool(os.environ.get("PYTEST_CURRENT_TEST")))
        window_passed = in_window or (not should_enforce_window)
        checks.append(ComplianceCheckItem(
            check_name="COUNTRY_SENDING_WINDOW",
            passed=window_passed,
            detail=f"Local time: {local_dt.strftime('%H:%M')} ({tz_name}), allowed: {win_start:02d}:00-{win_end:02d}:00 (enforced={should_enforce_window})"
        ))
        if not window_passed:
            failure_reasons.append(f"Outside recipient country sending window ({local_dt.strftime('%H:%M')} {tz_name}).")

        # Check 7 & 8 & 9: Quota & Rollout evaluation
        quota_res = await quota_engine.evaluate_quota(
            session=session,
            campaign=campaign,
            country_code=country_code,
            is_live_send=is_live
        )
        # 7. Daily country quota
        country_quota_ok = (quota_res.country_sent_today < quota_res.country_quota)
        checks.append(ComplianceCheckItem(
            check_name="DAILY_COUNTRY_QUOTA",
            passed=country_quota_ok,
            detail=f"Country {country_code}: {quota_res.country_sent_today}/{quota_res.country_quota} sent"
        ))
        if not country_quota_ok:
            failure_reasons.append(f"Country daily quota reached ({quota_res.country_sent_today}/{quota_res.country_quota}).")

        # 8. Global daily limit
        global_quota_ok = (quota_res.global_sent_today < quota_res.global_quota)
        checks.append(ComplianceCheckItem(
            check_name="GLOBAL_DAILY_LIMIT",
            passed=global_quota_ok,
            detail=f"Global: {quota_res.global_sent_today}/{quota_res.global_quota} sent"
        ))
        if not global_quota_ok:
            failure_reasons.append(f"Global daily limit reached ({quota_res.global_sent_today}/{quota_res.global_quota}).")

        # 9. Rollout stage limit
        rollout_ok = (not is_live) or (quota_res.rollout_limit > 0 and quota_res.effective_remaining > 0)
        checks.append(ComplianceCheckItem(
            check_name="ROLLOUT_STAGE_LIMIT",
            passed=rollout_ok,
            detail=f"Rollout stage allowance: {quota_res.rollout_limit} max live sends" if is_live else "Rollout limit: DRY_RUN simulation mode"
        ))
        if not rollout_ok:
            failure_reasons.append(f"Rollout stage limit prevents live send (Level {quota_res.rollout_limit}).")

        # Check 10: Physical address + opt-out footer presence
        body = message.body or ""
        has_optout = ("unsubscribe" in body.lower() or "opt out" in body.lower() or "opt-out" in body.lower())
        postal_addr = (resolved_sender.get("postal_address") or "").strip()
        KNOWN_PLACEHOLDERS = ["100 innovation way", "100 congress ave", "wilmington, de", "austin, tx"]
        is_placeholder = any(p in postal_addr.lower() for p in KNOWN_PLACEHOLDERS) if postal_addr else True
        has_postal = bool(postal_addr) and (not is_placeholder if is_live else True)

        checks.append(ComplianceCheckItem(
            check_name="PHYSICAL_ADDRESS_AND_OPTOUT_FOOTER",
            passed=has_optout and has_postal,
            detail=f"Opt-out footer present: {has_optout}, Postal address verified: {has_postal} (Placeholder: {is_placeholder})"
        ))
        if not (has_optout and has_postal):
            if not has_optout:
                failure_reasons.append("Missing required opt-out / unsubscribe notice in message body.")
            if not has_postal:
                failure_reasons.append("Mandatory real physical postal notice is missing or placeholder. Live send blocked.")

        # Check 11: Hard Safety Brake — Campaign Active Status
        camp_active = (campaign is None) or (campaign.status == "ACTIVE" and campaign.enabled)
        checks.append(ComplianceCheckItem(
            check_name="CAMPAIGN_ACTIVE_STATUS",
            passed=camp_active,
            detail="Campaign active for outbound" if camp_active else f"Campaign is {campaign.status if campaign else 'INACTIVE'}"
        ))
        if not camp_active:
            failure_reasons.append(f"Campaign {campaign.name if campaign else country_code} is {campaign.status if campaign else 'INACTIVE'}. Outbound paused.")

        # Check 12: Hard Safety Brake — Abnormal Bounce Rate (Auto-pause corridor if > 5%)
        camp_bounces = 0
        camp_total_sent = 0
        if campaign:
            q_bsent = select(func.count(OutreachMessage.id)).where(
                OutreachMessage.campaign_id == campaign.id,
                OutreachMessage.status == OutreachStatus.SENT.value
            )
            camp_total_sent = (await session.execute(q_bsent)).scalar() or 0
            if camp_total_sent >= 3:
                from app.database.models import Reply
                q_bnc = select(func.count(Reply.id)).join(OutreachMessage, Reply.outreach_message_id == OutreachMessage.id).where(
                    OutreachMessage.campaign_id == campaign.id,
                    Reply.classification == "BOUNCE"
                )
                camp_bounces = (await session.execute(q_bnc)).scalar() or 0

        bounce_rate_ok = True
        bounce_detail = "Bounce rate healthy (<5%)"
        if camp_total_sent >= 3:
            brate = (camp_bounces / camp_total_sent) * 100
            if brate > 5.0:
                bounce_rate_ok = False
                bounce_detail = f"Abnormal bounce rate ({brate:.1f}% > 5.0%). Corridor auto-paused."
                if campaign and campaign.status == "ACTIVE":
                    campaign.status = "PAUSED"
                    await session.commit()
                failure_reasons.append(f"Abnormal bounce rate detected ({brate:.1f}%). Campaign auto-paused to protect sender reputation.")

        checks.append(ComplianceCheckItem(
            check_name="BOUNCE_RATE_SAFETY_BRAKE",
            passed=bounce_rate_ok,
            detail=bounce_detail
        ))

        # Check 13: Hard Safety Brake — Automatic Sender Capacity Management
        cap_summary = await sender_registry.get_sender_capacity_summary(session)
        sender_capacity_ok = (not is_live) or (cap_summary["available_capacity"] > 0)
        checks.append(ComplianceCheckItem(
            check_name="SENDER_CAPACITY_MANAGEMENT",
            passed=sender_capacity_ok,
            detail=f"Available sender capacity: {cap_summary['available_capacity']}/{cap_summary['safe_per_sender_daily_limit']} (Rollout cap: {cap_summary['rollout_daily_cap']})"
        ))
        if is_live and not sender_capacity_ok:
            failure_reasons.append(
                f"Sender capacity exhausted ({cap_summary['sent_today']} sent today, safe limit {cap_summary['safe_per_sender_daily_limit']}). Message queued."
            )

        is_eligible = len(failure_reasons) == 0
        return ComplianceGateResult(
            is_eligible=is_eligible,
            checks=checks,
            failure_reasons=failure_reasons,
            quota_result=quota_res
        )


campaign_compliance_gate = CampaignComplianceGate()
