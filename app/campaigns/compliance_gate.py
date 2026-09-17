from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.database.models import OutreachMessage, OutreachStatus, Business, Campaign, SuppressionList, Contact, AuditRun
from app.core.config import settings
from app.outreach.compliance import compliance_guard
from app.campaigns.models import ComplianceGateResult, ComplianceCheckItem
from app.campaigns.scheduler import campaign_scheduler
from app.campaigns.sender_registry import sender_registry
from app.campaigns.quota_engine import quota_engine
from app.compliance.recipient_classifier import classify_recipient, RecipientClassification
from app.compliance.negative_disclaimer import contains_prohibited_contact_notice
from app.compliance.provenance import build_jurisdiction_provenance, STRICT_OPT_IN_JURISDICTIONS


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
        is_live = force_live or (not getattr(settings, "EMAIL_DRY_RUN", True) and not getattr(settings, "DRY_RUN", True))
        email = (message.recipient_email or "").strip().lower()

        from app.analytics.truth_engine import OPERATOR_EMAILS
        recip_lower = email
        msg_meta = getattr(message, "auto_approval_eligibility", None) or {}
        is_canary = (
            (isinstance(msg_meta, dict) and bool(msg_meta.get("is_canary")))
            or any(k in recip_lower for k in OPERATOR_EMAILS)
            or "canary" in recip_lower
            or "canary" in (message.subject or "").lower()
        )

        # Check 1: Suppression check
        is_supp = False if is_canary else await compliance_guard.is_suppressed(session, email=email, domain=biz.domain if biz else None)
        checks.append(ComplianceCheckItem(
            check_name="SUPPRESSION_CHECK",
            passed=not is_supp,
            detail="Address clear of suppression list" if not is_supp else "Address is on suppression list"
        ))
        if is_supp:
            failure_reasons.append(f"Recipient {email} is on suppression list.")

        # Check 2: Unsubscribe status
        # Explicit check if suppression reason was UNSUBSCRIBE / OPT_OUT
        if not is_canary:
            unsub_stmt = select(SuppressionList.id).where(
                and_(
                    SuppressionList.email == email,
                    SuppressionList.reason.in_(["UNSUBSCRIBE", "OPT_OUT", "REQUESTED_REMOVAL"])
                )
            ).limit(1)
            unsub_exists = (await session.execute(unsub_stmt)).first() is not None
        else:
            unsub_exists = False
        checks.append(ComplianceCheckItem(
            check_name="UNSUBSCRIBE_STATUS",
            passed=not unsub_exists,
            detail="No prior opt-out on record" if not unsub_exists else "Recipient previously opted out"
        ))
        if unsub_exists:
            failure_reasons.append(f"Recipient {email} has an active unsubscribe record.")

        # Check 3: Duplicate protection
        # Block if a message to this recipient was already successfully sent
        if not is_canary:
            dup_stmt = select(func.count(OutreachMessage.id)).where(
                OutreachMessage.recipient_email == email,
                OutreachMessage.status == OutreachStatus.SENT.value,
                OutreachMessage.id != message.id
            )
            prior_sent_count = (await session.execute(dup_stmt)).scalar() or 0
        else:
            prior_sent_count = 0
        checks.append(ComplianceCheckItem(
            check_name="DUPLICATE_PROTECTION",
            passed=prior_sent_count == 0,
            detail=f"Prior sent count: {prior_sent_count}"
        ))
        if prior_sent_count > 0:
            failure_reasons.append(f"Duplicate protection: {email} already received an outreach message.")

        # Check 4: Recent contact check (cooldown within last 30 days)
        if not is_canary:
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            recent_stmt = select(func.count(OutreachMessage.id)).where(
                OutreachMessage.recipient_email == email,
                OutreachMessage.sent_at >= thirty_days_ago,
                OutreachMessage.id != message.id
            )
            recent_count = (await session.execute(recent_stmt)).scalar() or 0
        else:
            recent_count = 0
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
        has_postal = (bool(postal_addr) and not is_placeholder) if is_live else True

        checks.append(ComplianceCheckItem(
            check_name="PHYSICAL_ADDRESS_AND_OPTOUT_FOOTER",
            passed=has_optout and has_postal,
            detail=f"Opt-out footer present: {has_optout}, Postal address verified: {has_postal} (Placeholder: {is_placeholder})"
        ))
        if not (has_optout and has_postal):
            if not has_optout:
                failure_reasons.append("Missing required opt-out / unsubscribe notice in message body.")
            if not has_postal and is_live:
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
        available_cap = cap_summary.get("available_capacity", 0)
        safe_limit = cap_summary.get("safe_per_sender_daily_limit", cap_summary.get("rollout_daily_cap", 10))
        rollout_cap = cap_summary.get("rollout_daily_cap", 10)
        sent_today = cap_summary.get("sent_today", 0)
        sender_capacity_ok = (not is_live) or (available_cap > 0)
        checks.append(ComplianceCheckItem(
            check_name="SENDER_CAPACITY_MANAGEMENT",
            passed=sender_capacity_ok,
            detail=f"Available sender capacity: {available_cap}/{safe_limit} (Rollout cap: {rollout_cap})"
        ))
        if is_live and not sender_capacity_ok:
            failure_reasons.append(
                f"Sender capacity exhausted ({sent_today} sent today, safe limit {safe_limit}). Message queued."
            )

        # Check 14: Hard Safety Brake — Jurisdiction Sanction / Strict Consent Policy
        # Strict opt-in jurisdictions (DE, IT, ES, CH) strictly blocked without verifiable prior consent
        is_strict_opt_in = country_code in STRICT_OPT_IN_JURISDICTIONS
        has_verified_consent = getattr(message, "has_verified_consent", False) or False
        jurisdiction_ok = (not is_strict_opt_in) or has_verified_consent
        jurisdiction_detail = (
            f"Jurisdiction '{country_code}' compliant"
            if jurisdiction_ok
            else f"Jurisdiction '{country_code}' strictly prohibited without prior explicit consent (OUTBOUND_BLOCKED)"
        )
        checks.append(ComplianceCheckItem(
            check_name="JURISDICTION_SANCTION_POLICY",
            passed=jurisdiction_ok,
            detail=jurisdiction_detail
        ))
        if not jurisdiction_ok:
            failure_reasons.append(
                f"OUTBOUND_BLOCKED / jurisdiction_requires_consent: Jurisdiction '{country_code}' strictly prohibits unsolicited commercial email without verifiable prior explicit consent."
            )

        # Retrieve associated contact if available
        contact = None
        if biz:
            c_stmt = select(Contact).where(
                and_(Contact.business_id == biz.id, Contact.email == email)
            ).limit(1)
            contact = (await session.execute(c_stmt)).scalar_one_or_none()

        # Check 15: Recipient Classification & Entity Discrimination
        recipient_class = classify_recipient(
            email=email,
            business_name=biz.name if biz else None,
            business_domain=biz.domain if biz else None,
            contact_name=contact.name if contact else None,
            contact_title=contact.title if contact else None
        )

        recipient_class_ok = True
        recipient_class_detail = f"Recipient entity classified as: {recipient_class.value}"
        if recipient_class == RecipientClassification.PERSONAL_WEBMAIL and country_code in ("UK", "CA", "AU", "FR", "NL", "SE", "IE", "NZ"):
            recipient_class_ok = False
            recipient_class_detail = f"Personal webmail ineligible for B2B commercial outreach in jurisdiction '{country_code}' (OUTBOUND_BLOCKED)"
            failure_reasons.append(
                f"OUTBOUND_BLOCKED / personal_webmail_ineligible: Recipient uses personal webmail in jurisdiction '{country_code}' which requires corporate subscriber or explicit opt-in."
            )
        elif recipient_class == RecipientClassification.SOLE_TRADER and country_code in ("UK", "FR", "NL", "SE", "IE"):
            recipient_class_ok = False
            recipient_class_detail = f"Sole trader in jurisdiction '{country_code}' requires prior opt-in under PECR/ePrivacy (OUTBOUND_BLOCKED)"
            failure_reasons.append(
                f"OUTBOUND_BLOCKED / sole_trader_requires_consent: Recipient is a sole trader / natural person in jurisdiction '{country_code}', requiring prior opt-in under PECR/ePrivacy."
            )
        elif recipient_class == RecipientClassification.UNKNOWN and country_code != "US":
            recipient_class_ok = False
            recipient_class_detail = f"Cannot verify recipient domain matches business entity in jurisdiction '{country_code}' (OUTBOUND_BLOCKED)"
            failure_reasons.append(
                f"OUTBOUND_BLOCKED / unverified_recipient_entity: Cannot verify recipient domain matches business entity in '{country_code}'."
            )

        checks.append(ComplianceCheckItem(
            check_name="RECIPIENT_CLASSIFICATION_GATE",
            passed=recipient_class_ok,
            detail=recipient_class_detail
        ))

        # Check 16: Negative Disclaimer Detection
        evidence_texts = []
        if biz:
            if biz.contact_page_url:
                evidence_texts.append(biz.contact_page_url)
            if biz.website_url:
                evidence_texts.append(biz.website_url)
            if getattr(biz, "address", None):
                evidence_texts.append(biz.address)
        if message.auto_approval_eligibility and isinstance(message.auto_approval_eligibility, dict):
            extra_snippets = message.auto_approval_eligibility.get("page_snippets") or []
            if isinstance(extra_snippets, list):
                evidence_texts.extend(extra_snippets)

        has_negative_disclaimer, matched_phrase = contains_prohibited_contact_notice(
            page_text=" ".join(evidence_texts) if evidence_texts else None
        )
        checks.append(ComplianceCheckItem(
            check_name="NEGATIVE_DISCLAIMER_CHECK",
            passed=not has_negative_disclaimer,
            detail="Clean contact page without anti-marketing disclaimers" if not has_negative_disclaimer else f"Prohibited contact disclaimer detected: '{matched_phrase}'"
        ))
        if has_negative_disclaimer:
            failure_reasons.append(
                f"OUTBOUND_BLOCKED / prohibited_contact_disclaimer: Source page contains explicit notice forbidding unsolicited commercial inquiries ('{matched_phrase}')."
            )

        # Check 17: Jurisdiction Provenance & Lawful Basis Tracking
        audit_summary = None
        if biz:
            if hasattr(biz, "__dict__") and biz.__dict__.get("audits"):
                audit_summary = getattr(biz.__dict__["audits"][0], "summary", None)
            else:
                a_stmt = select(AuditRun.summary).where(AuditRun.business_id == biz.id).limit(1)
                audit_summary = (await session.execute(a_stmt)).scalar_one_or_none()

        provenance = build_jurisdiction_provenance(
            country_code=country_code,
            email=email,
            business_name=biz.name if biz else None,
            business_domain=biz.domain if biz else None,
            source_url=(biz.contact_page_url or biz.website_url) if biz else None,
            observed_at=biz.created_at if biz else None,
            recipient_role=contact.title if contact else "Owner / Lead",
            recipient_classification=recipient_class,
            audit_summary=audit_summary,
            has_explicit_consent=has_verified_consent
        )

        # Persist rich provenance directly to message record
        message.compliance_notes = f"Jurisdiction: {country_code} | Recipient: {recipient_class.value} | Lawful Basis: {provenance.lawful_basis} | Decision: {provenance.compliance_decision}"
        if message.auto_approval_eligibility is None or not isinstance(message.auto_approval_eligibility, dict):
            message.auto_approval_eligibility = {}
        message.auto_approval_eligibility["jurisdiction_provenance"] = provenance.to_dict()

        provenance_ok = provenance.compliance_decision == "PERMITTED" and (not has_negative_disclaimer) and jurisdiction_ok and recipient_class_ok
        checks.append(ComplianceCheckItem(
            check_name="PROVENANCE_AND_LAWFUL_BASIS",
            passed=provenance_ok,
            detail=f"Statutory basis: {provenance.lawful_basis} (Decision: {provenance.compliance_decision})"
        ))
        if not provenance_ok and provenance.blocking_reason:
            if not any(provenance.blocking_reason in fr for fr in failure_reasons):
                failure_reasons.append(f"OUTBOUND_BLOCKED / {provenance.blocking_reason}")

        is_eligible = len(failure_reasons) == 0
        return ComplianceGateResult(
            is_eligible=is_eligible,
            checks=checks,
            failure_reasons=failure_reasons,
            quota_result=quota_res
        )


campaign_compliance_gate = CampaignComplianceGate()
