import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.database.models import (
    OutreachMessage, OutreachStatus, Business, Offer,
    SuppressionList, PipelineEvent, PipelineStage, Contact,
    AuditRun
)
from app.core.config import settings
from app.core.logging import logger
from app.outreach.compliance import compliance_guard
from app.campaigns.sender_registry import sender_registry
from app.acquisition.controller import active_prospect_controller
from app.compliance.recipient_classifier import classify_recipient, RecipientClassification
from app.compliance.negative_disclaimer import contains_prohibited_contact_notice
from app.compliance.provenance import build_jurisdiction_provenance, STRICT_OPT_IN_JURISDICTIONS

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

PROHIBITED_CLAIMS = [
    "guarantee 100%",
    "guaranteed 10x",
    "guaranteed 5x",
    "zero risk",
    "guaranteed revenue",
    "risk-free guarantee",
    "100% money back guarantee",
    "guaranteed 300%",
    "guaranteed returns"
]

INTERNAL_LEAKAGE_PATTERNS = [
    "<system_message>",
    "</system_message>",
    "system prompt:",
    "ai assistant:",
    "[internal]",
    "[debug]",
    "raw prompt:",
    "ignore previous instructions"
]

class AutoApprovalResult:
    def __init__(
        self,
        message_id: int,
        is_eligible: bool,
        checks: List[Dict[str, Any]],
        blocking_reasons: List[str]
    ):
        self.message_id = message_id
        self.is_eligible = is_eligible
        self.checks = checks
        self.blocking_reasons = blocking_reasons

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "is_eligible": self.is_eligible,
            "checks": self.checks,
            "blocking_reasons": self.blocking_reasons
        }


class DeterministicAutoApprovalEngine:
    """
    Evaluates outbound messages for automated, deterministic approval.
    Follows zero-fake-approval invariant:
    - Never approves unless all 14 safety criteria pass.
    - Truthfully tags actor_type as 'SYSTEM_AUTO_APPROVAL'.
    - If any check fails, leaves in PENDING_APPROVAL and records blocking reasons.
    """

    async def evaluate_message_eligibility(
        self, session: AsyncSession, message: OutreachMessage
    ) -> AutoApprovalResult:
        checks: List[Dict[str, Any]] = []
        blocking_reasons: List[str] = []

        # 1. Valid recipient email syntax
        email = (message.recipient_email or "").strip().lower()
        is_valid_email = bool(email and EMAIL_REGEX.match(email))
        checks.append({
            "name": "VALID_RECIPIENT",
            "passed": is_valid_email,
            "detail": f"Recipient '{email}' format valid" if is_valid_email else "Invalid email address format"
        })
        if not is_valid_email:
            blocking_reasons.append(f"Invalid recipient email syntax: '{email}'")

        # 2. Valid business lead exists
        biz = await session.get(Business, message.business_id) if message.business_id else None
        has_business = biz is not None
        checks.append({
            "name": "VALID_BUSINESS_LEAD",
            "passed": has_business,
            "detail": f"Business #{biz.id} '{biz.name}' found" if has_business else "Linked business lead does not exist"
        })
        if not has_business:
            blocking_reasons.append("Linked business record does not exist in CRM.")

        # 3. Outreach policy: Suppression check
        is_supp = False
        if is_valid_email:
            is_supp = await compliance_guard.is_suppressed(session, email=email, domain=biz.domain if biz else None)
        checks.append({
            "name": "NOT_SUPPRESSED",
            "passed": not is_supp,
            "detail": "Address is not suppressed" if not is_supp else "Address is on suppression list"
        })
        if is_supp:
            blocking_reasons.append(f"Recipient '{email}' is actively suppressed (is on suppression list).")

        # 4. Explicit Opt-Out / Unsubscribe Check
        unsub_stmt = select(SuppressionList.id).where(
            and_(
                SuppressionList.email == email,
                SuppressionList.reason.in_(["UNSUBSCRIBE", "OPT_OUT", "REQUESTED_REMOVAL"])
            )
        ).limit(1)
        unsub_exists = (await session.execute(unsub_stmt)).first() is not None
        checks.append({
            "name": "NOT_OPTED_OUT",
            "passed": not unsub_exists,
            "detail": "No prior opt-out on record" if not unsub_exists else "Recipient previously opted out"
        })
        if unsub_exists:
            blocking_reasons.append(f"Recipient '{email}' has previously opted out.")

        # 5. Duplicate Send Prevention (prior sent outreach to this recipient)
        dup_stmt = select(func.count(OutreachMessage.id)).where(
            OutreachMessage.recipient_email == email,
            OutreachMessage.status == OutreachStatus.SENT.value,
            OutreachMessage.id != message.id
        )
        prior_sent_count = (await session.execute(dup_stmt)).scalar() or 0
        checks.append({
            "name": "NO_DUPLICATE_PRIOR_SEND",
            "passed": prior_sent_count == 0,
            "detail": "No prior outreach dispatched to this recipient" if prior_sent_count == 0 else f"Prior messages sent: {prior_sent_count}"
        })
        if prior_sent_count > 0:
            blocking_reasons.append(f"Recipient '{email}' has already received outreach.")

        # 6. Message not already in SENT state
        not_sent_yet = message.status != OutreachStatus.SENT.value and message.sent_at is None
        checks.append({
            "name": "MESSAGE_NOT_ALREADY_SENT",
            "passed": not_sent_yet,
            "detail": "Message has not been sent yet" if not_sent_yet else f"Message already marked SENT at {message.sent_at}"
        })
        if not not_sent_yet:
            blocking_reasons.append(f"Message #{message.id} is already SENT.")

        # 7. Prohibited Claims Check (Anti-Fraud / Anti-Hype)
        body_lower = (message.body or "").lower()
        subject_lower = (message.subject or "").lower()
        combined_text = f"{subject_lower} {body_lower}"
        found_prohibited = [c for c in PROHIBITED_CLAIMS if c in combined_text]
        checks.append({
            "name": "NO_PROHIBITED_CLAIMS",
            "passed": len(found_prohibited) == 0,
            "detail": "Clean copy without prohibited claims" if not found_prohibited else f"Prohibited claims detected: {', '.join(found_prohibited)}"
        })
        if found_prohibited:
            blocking_reasons.append(f"Message content contains prohibited claims: {', '.join(found_prohibited)}")

        # 8. Internal Leakage Check (Zero System Prompt / Debug Tokens)
        found_leaks = [p for p in INTERNAL_LEAKAGE_PATTERNS if p in combined_text]
        checks.append({
            "name": "NO_INTERNAL_LEAKAGE",
            "passed": len(found_leaks) == 0,
            "detail": "Copy clean of system tokens" if not found_leaks else f"Internal leaks detected: {', '.join(found_leaks)}"
        })
        if found_leaks:
            blocking_reasons.append(f"Message content contains internal prompt leaks: {', '.join(found_leaks)}")

        # 9. Commercial Floor Check ($500 minimum service value)
        offer = await session.get(Offer, message.offer_id) if message.offer_id else None
        deal_value = float(offer.recommended_price) if offer and offer.recommended_price is not None else float(getattr(settings, "COMMERCIAL_FLOOR_USD", 500.0))
        commercial_floor = float(getattr(settings, "COMMERCIAL_FLOOR_USD", 500.0))
        passed_floor = deal_value >= commercial_floor
        checks.append({
            "name": "COMMERCIAL_FLOOR_PASSED",
            "passed": passed_floor,
            "detail": f"Deal value ${deal_value:.2f} >= ${commercial_floor:.2f} floor" if passed_floor else f"Deal value ${deal_value:.2f} below ${commercial_floor:.2f} floor"
        })
        if not passed_floor:
            blocking_reasons.append(f"Offer value ${deal_value:.2f} is below commercial floor of ${commercial_floor:.2f}.")

        # 10. Provider Configuration Check
        provider_name = (settings.EMAIL_PROVIDER or "dry_run").lower().strip()
        provider_ready = True
        provider_detail = f"Provider '{provider_name}' active"
        if not getattr(settings, "EMAIL_DRY_RUN", True):
            if provider_name in ("gmail", "gmail_oauth"):
                if not getattr(settings, "GMAIL_CLIENT_ID", None) or not getattr(settings, "GMAIL_REFRESH_TOKEN", None):
                    provider_ready = False
                    provider_detail = "Gmail OAuth credentials missing in configuration."
            elif provider_name in ("titan", "titan_smtp"):
                titan_user = getattr(settings, "TITAN_SMTP_USER", None) or getattr(settings, "SMTP_USER", None)
                titan_pass = getattr(settings, "TITAN_SMTP_PASSWORD", None) or getattr(settings, "SMTP_PASSWORD", None)
                if not titan_user or not titan_pass:
                    provider_ready = False
                    provider_detail = "Titan SMTP credentials missing in configuration."
            elif provider_name == "smtp":
                if not getattr(settings, "SMTP_HOST", None) or not getattr(settings, "SMTP_USER", None):
                    provider_ready = False
                    provider_detail = "SMTP credentials missing in configuration."
        checks.append({
            "name": "PROVIDER_CONFIGURED",
            "passed": provider_ready,
            "detail": provider_detail
        })
        if not provider_ready:
            blocking_reasons.append(f"Outbound provider not ready: {provider_detail}")

        # 11. Daily Outbound Cap Capacity Check
        cap_summary = await sender_registry.get_sender_capacity_summary(session)
        available_cap = cap_summary.get("available_capacity", 0)
        has_capacity = available_cap > 0
        checks.append({
            "name": "DAILY_CAP_CAPACITY",
            "passed": has_capacity,
            "detail": f"Capacity available ({cap_summary.get('sent_today', 0)}/{cap_summary.get('rollout_daily_cap', 1)} sent today)" if has_capacity else f"Daily limit reached ({cap_summary.get('sent_today', 0)}/{cap_summary.get('rollout_daily_cap', 1)})"
        })
        if not has_capacity:
            blocking_reasons.append(f"Daily rollout capacity exhausted for today ({cap_summary.get('sent_today', 0)}/{cap_summary.get('rollout_daily_cap', 1)}).")

        # 12. ActiveOutreachLock Check
        lock = await active_prospect_controller.get_or_create_lock(session)
        lock_available = lock.status in ("IDLE", "RELEASED") or (lock.business_id == message.business_id)
        checks.append({
            "name": "OUTREACH_LOCK_AVAILABLE",
            "passed": lock_available,
            "detail": f"Lock status is {lock.status} (business #{lock.business_id})" if lock_available else f"Outreach lock is currently held by active process (status: {lock.status})"
        })
        if not lock_available:
            blocking_reasons.append(f"ActiveOutreachLock is currently held by another process ({lock.status}).")

        # 13. Message currently in PENDING_APPROVAL
        in_pending_state = message.status == OutreachStatus.PENDING_APPROVAL.value
        checks.append({
            "name": "PENDING_APPROVAL_STATE",
            "passed": in_pending_state,
            "detail": f"Status is {message.status}"
        })
        if not in_pending_state:
            blocking_reasons.append(f"Message status is '{message.status}' (expected PENDING_APPROVAL).")

        # 14. Auto-Approval Master Toggle
        auto_approval_enabled = getattr(settings, "AUTO_APPROVAL_ENABLED", True)
        checks.append({
            "name": "AUTO_APPROVAL_POLICY_ENABLED",
            "passed": auto_approval_enabled,
            "detail": "Auto-approval policy is enabled in settings" if auto_approval_enabled else "AUTO_APPROVAL_ENABLED is False in configuration"
        })
        if not auto_approval_enabled:
            blocking_reasons.append("Autonomous auto-approval is disabled in system configuration.")

        # 15. Jurisdiction Sanction Policy Check (DE, IT, ES, CH blocked)
        country_code = (biz.country if biz and biz.country else "US").strip().upper()
        is_strict_opt_in = country_code in STRICT_OPT_IN_JURISDICTIONS
        has_verified_consent = getattr(message, "has_verified_consent", False) or False
        jurisdiction_ok = (not is_strict_opt_in) or has_verified_consent
        checks.append({
            "name": "JURISDICTION_SANCTION_POLICY",
            "passed": jurisdiction_ok,
            "detail": f"Jurisdiction '{country_code}' compliant" if jurisdiction_ok else f"Jurisdiction '{country_code}' strictly prohibited without prior explicit consent (OUTBOUND_BLOCKED)"
        })
        if not jurisdiction_ok:
            blocking_reasons.append(f"OUTBOUND_BLOCKED / jurisdiction_requires_consent: Jurisdiction '{country_code}' strictly prohibits unsolicited commercial email without verifiable prior explicit consent.")

        # 16. Recipient Classification & Entity Discrimination
        contact = None
        if biz:
            c_stmt = select(Contact).where(
                and_(Contact.business_id == biz.id, Contact.email == email)
            ).limit(1)
            contact = (await session.execute(c_stmt)).scalar_one_or_none()

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
            blocking_reasons.append(
                f"OUTBOUND_BLOCKED / personal_webmail_ineligible: Recipient uses personal webmail in jurisdiction '{country_code}' which requires corporate subscriber or explicit opt-in."
            )
        elif recipient_class == RecipientClassification.SOLE_TRADER and country_code in ("UK", "FR", "NL", "SE", "IE"):
            recipient_class_ok = False
            recipient_class_detail = f"Sole trader in jurisdiction '{country_code}' requires prior opt-in under PECR/ePrivacy (OUTBOUND_BLOCKED)"
            blocking_reasons.append(
                f"OUTBOUND_BLOCKED / sole_trader_requires_consent: Recipient is a sole trader / natural person in jurisdiction '{country_code}', requiring prior opt-in under PECR/ePrivacy."
            )
        elif recipient_class == RecipientClassification.UNKNOWN and country_code != "US":
            recipient_class_ok = False
            recipient_class_detail = f"Cannot verify recipient domain matches business entity in jurisdiction '{country_code}' (OUTBOUND_BLOCKED)"
            blocking_reasons.append(
                f"OUTBOUND_BLOCKED / unverified_recipient_entity: Cannot verify recipient domain matches business entity in '{country_code}'."
            )

        checks.append({
            "name": "RECIPIENT_CLASSIFICATION_GATE",
            "passed": recipient_class_ok,
            "detail": recipient_class_detail
        })

        # 17. Negative Disclaimer Detection
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
        checks.append({
            "name": "NEGATIVE_DISCLAIMER_CHECK",
            "passed": not has_negative_disclaimer,
            "detail": "Clean contact page without anti-marketing disclaimers" if not has_negative_disclaimer else f"Prohibited contact disclaimer detected: '{matched_phrase}'"
        })
        if has_negative_disclaimer:
            blocking_reasons.append(
                f"OUTBOUND_BLOCKED / prohibited_contact_disclaimer: Source page contains explicit notice forbidding unsolicited commercial inquiries ('{matched_phrase}')."
            )

        # 18. Jurisdiction Provenance & Lawful Basis Tracking
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

        message.compliance_notes = f"Jurisdiction: {country_code} | Recipient: {recipient_class.value} | Lawful Basis: {provenance.lawful_basis} | Decision: {provenance.compliance_decision}"
        if message.auto_approval_eligibility is None or not isinstance(message.auto_approval_eligibility, dict):
            message.auto_approval_eligibility = {}
        message.auto_approval_eligibility["jurisdiction_provenance"] = provenance.to_dict()

        provenance_ok = provenance.compliance_decision == "PERMITTED" and (not has_negative_disclaimer) and jurisdiction_ok and recipient_class_ok
        checks.append({
            "name": "PROVENANCE_AND_LAWFUL_BASIS",
            "passed": provenance_ok,
            "detail": f"Statutory basis: {provenance.lawful_basis} (Decision: {provenance.compliance_decision})"
        })
        if not provenance_ok and provenance.blocking_reason:
            if not any(provenance.blocking_reason in br for br in blocking_reasons):
                blocking_reasons.append(f"OUTBOUND_BLOCKED / {provenance.blocking_reason}")

        is_eligible = len(blocking_reasons) == 0
        return AutoApprovalResult(
            message_id=message.id,
            is_eligible=is_eligible,
            checks=checks,
            blocking_reasons=blocking_reasons
        )

    async def evaluate_send_authorization(
        self, session: AsyncSession, message: OutreachMessage, force_live: bool = False
    ) -> AutoApprovalResult:
        """
        Evaluates whether an approved outreach message is deterministically authorized for transmission.
        Replaces blanket 'Explicit human CEO approval required' with deterministic policy gates:
        - Validates recipient, lead, suppression, opt-out, duplicate prevention, and content safety.
        - Verifies commercial floor ($500+).
        - Verifies provider configuration & daily rollout capacity.
        - Verifies ActiveOutreachLock.
        - Verifies authorization provenance (human CEO or autonomous system auto-approval).
        """
        checks: List[Dict[str, Any]] = []
        blocking_reasons: List[str] = []

        is_live_send = force_live or (not getattr(settings, "EMAIL_DRY_RUN", True) and not getattr(settings, "DRY_RUN", True))

        # 1. Valid recipient email syntax
        email = (message.recipient_email or "").strip().lower()
        is_valid_email = bool(email and EMAIL_REGEX.match(email))
        checks.append({
            "name": "VALID_RECIPIENT",
            "passed": is_valid_email,
            "detail": f"Recipient '{email}' format valid" if is_valid_email else "Invalid email address format"
        })
        if not is_valid_email:
            blocking_reasons.append(f"Invalid recipient email syntax: '{email}'")

        # 2. Valid business lead exists
        biz = await session.get(Business, message.business_id) if message.business_id else None
        has_business = biz is not None
        checks.append({
            "name": "VALID_BUSINESS_LEAD",
            "passed": has_business,
            "detail": f"Business #{biz.id} '{biz.name}' found" if has_business else "Linked business lead does not exist"
        })
        if not has_business:
            blocking_reasons.append("Linked business record does not exist in CRM.")

        # 3. Outreach policy: Suppression check
        is_supp = False
        if is_valid_email:
            is_supp = await compliance_guard.is_suppressed(session, email=email, domain=biz.domain if biz else None)
        checks.append({
            "name": "NOT_SUPPRESSED",
            "passed": not is_supp,
            "detail": "Address is not suppressed" if not is_supp else "Address is on suppression list"
        })
        if is_supp:
            blocking_reasons.append(f"Recipient '{email}' is actively suppressed (is on suppression list).")

        # 4. Explicit Opt-Out / Unsubscribe Check
        unsub_stmt = select(SuppressionList.id).where(
            and_(
                SuppressionList.email == email,
                SuppressionList.reason.in_(["UNSUBSCRIBE", "OPT_OUT", "REQUESTED_REMOVAL"])
            )
        ).limit(1)
        unsub_exists = (await session.execute(unsub_stmt)).first() is not None
        checks.append({
            "name": "NOT_OPTED_OUT",
            "passed": not unsub_exists,
            "detail": "No prior opt-out on record" if not unsub_exists else "Recipient previously opted out"
        })
        if unsub_exists:
            blocking_reasons.append(f"Recipient '{email}' has previously opted out.")

        # 5. Duplicate Send Prevention
        dup_stmt = select(func.count(OutreachMessage.id)).where(
            OutreachMessage.recipient_email == email,
            OutreachMessage.status == OutreachStatus.SENT.value,
            OutreachMessage.id != message.id
        )
        prior_sent_count = (await session.execute(dup_stmt)).scalar() or 0
        checks.append({
            "name": "NO_DUPLICATE_PRIOR_SEND",
            "passed": prior_sent_count == 0,
            "detail": "No prior outreach dispatched to this recipient" if prior_sent_count == 0 else f"Prior messages sent: {prior_sent_count}"
        })
        if prior_sent_count > 0:
            blocking_reasons.append(f"Recipient '{email}' has already received outreach.")

        # 6. Message not already in SENT state
        not_sent_yet = message.status != OutreachStatus.SENT.value and message.sent_at is None
        checks.append({
            "name": "MESSAGE_NOT_ALREADY_SENT",
            "passed": not_sent_yet,
            "detail": "Message has not been sent yet" if not_sent_yet else f"Message already marked SENT at {message.sent_at}"
        })
        if not not_sent_yet:
            blocking_reasons.append(f"Message #{message.id} is already SENT.")

        # 7. Prohibited Claims Check (Anti-Fraud / Anti-Hype)
        body_lower = (message.body or "").lower()
        subject_lower = (message.subject or "").lower()
        combined_text = f"{subject_lower} {body_lower}"
        found_prohibited = [c for c in PROHIBITED_CLAIMS if c in combined_text]
        checks.append({
            "name": "NO_PROHIBITED_CLAIMS",
            "passed": len(found_prohibited) == 0,
            "detail": "Clean copy without prohibited claims" if not found_prohibited else f"Prohibited claims detected: {', '.join(found_prohibited)}"
        })
        if found_prohibited:
            blocking_reasons.append(f"Message content contains prohibited claims: {', '.join(found_prohibited)}")

        # 8. Internal Leakage Check (Zero System Prompt / Debug Tokens)
        found_leaks = [p for p in INTERNAL_LEAKAGE_PATTERNS if p in combined_text]
        checks.append({
            "name": "NO_INTERNAL_LEAKAGE",
            "passed": len(found_leaks) == 0,
            "detail": "Copy clean of system tokens" if not found_leaks else f"Internal leaks detected: {', '.join(found_leaks)}"
        })
        if found_leaks:
            blocking_reasons.append(f"Message content contains internal prompt leaks: {', '.join(found_leaks)}")

        # 9. Commercial Floor Check ($500 minimum service value)
        offer = await session.get(Offer, message.offer_id) if message.offer_id else None
        deal_value = float(offer.recommended_price) if offer and offer.recommended_price is not None else float(getattr(settings, "COMMERCIAL_FLOOR_USD", 500.0))
        commercial_floor = float(getattr(settings, "COMMERCIAL_FLOOR_USD", 500.0))
        passed_floor = deal_value >= commercial_floor
        checks.append({
            "name": "COMMERCIAL_FLOOR_PASSED",
            "passed": passed_floor,
            "detail": f"Deal value ${deal_value:.2f} >= ${commercial_floor:.2f} floor" if passed_floor else f"Deal value ${deal_value:.2f} below ${commercial_floor:.2f} floor"
        })
        if not passed_floor:
            blocking_reasons.append(f"Offer value ${deal_value:.2f} is below commercial floor of ${commercial_floor:.2f}.")

        # 10. Provider Configuration Check
        provider_name = (settings.EMAIL_PROVIDER or "").lower().strip()
        provider_ready = True
        provider_detail = f"Provider '{provider_name}' active"
        if is_live_send:
            if provider_name in ("gmail", "gmail_oauth"):
                if not getattr(settings, "GMAIL_CLIENT_ID", None) or not getattr(settings, "GMAIL_REFRESH_TOKEN", None) or not getattr(settings, "GMAIL_CLIENT_SECRET", None):
                    provider_ready = False
                    provider_detail = "Gmail OAuth credentials missing in configuration."
            elif provider_name in ("titan", "titan_smtp"):
                titan_user = getattr(settings, "TITAN_SMTP_USER", None) or getattr(settings, "SMTP_USER", None)
                titan_pass = getattr(settings, "TITAN_SMTP_PASSWORD", None) or getattr(settings, "SMTP_PASSWORD", None)
                if not titan_user or not titan_pass:
                    provider_ready = False
                    provider_detail = "Titan SMTP credentials missing in configuration."
            elif provider_name == "smtp":
                if not getattr(settings, "SMTP_HOST", None) or not getattr(settings, "SMTP_USER", None):
                    provider_ready = False
                    provider_detail = "SMTP credentials missing in configuration."
        checks.append({
            "name": "PROVIDER_CONFIGURED",
            "passed": provider_ready,
            "detail": provider_detail
        })
        if not provider_ready:
            blocking_reasons.append(f"Outbound provider not ready: {provider_detail}")

        # 11. Daily Outbound Cap Capacity Check
        if is_live_send:
            cap_summary = await sender_registry.get_sender_capacity_summary(session)
            available_cap = cap_summary.get("available_capacity", 0)
            has_capacity = available_cap > 0
            checks.append({
                "name": "DAILY_CAP_CAPACITY",
                "passed": has_capacity,
                "detail": f"Capacity available ({cap_summary.get('sent_today', 0)}/{cap_summary.get('rollout_daily_cap', 1)} sent today)" if has_capacity else f"Daily limit reached ({cap_summary.get('sent_today', 0)}/{cap_summary.get('rollout_daily_cap', 1)})"
            })
            if not has_capacity:
                blocking_reasons.append(f"Daily rollout capacity exhausted for today ({cap_summary.get('sent_today', 0)}/{cap_summary.get('rollout_daily_cap', 1)}).")
        else:
            checks.append({
                "name": "DAILY_CAP_CAPACITY",
                "passed": True,
                "detail": "Simulated dry-run bypasses daily capacity check"
            })

        # 12. ActiveOutreachLock Check
        lock = await active_prospect_controller.get_or_create_lock(session)
        lock_available = lock.status in ("IDLE", "RELEASED") or (lock.business_id == message.business_id)
        checks.append({
            "name": "OUTREACH_LOCK_AVAILABLE",
            "passed": lock_available,
            "detail": f"Lock status is {lock.status} (business #{lock.business_id})" if lock_available else f"Outreach lock is currently held by active process (status: {lock.status})"
        })
        if not lock_available:
            blocking_reasons.append(f"ActiveOutreachLock is currently held by another process ({lock.status}).")

        # 13. Deterministic Authorization Policy Check (Cold external strictly requires CEO approval)
        from app.analytics.truth_engine import OPERATOR_EMAILS
        recip_lower = (message.recipient_email or "").lower().strip()
        msg_meta = getattr(message, "auto_approval_eligibility", None) or {}
        is_canary = (
            (isinstance(msg_meta, dict) and bool(msg_meta.get("is_canary")))
            or any(k in recip_lower for k in OPERATOR_EMAILS)
            or "canary" in recip_lower
        )
        is_cold_external = (not is_canary) and (getattr(message, "sequence_step", 1) == 1) and (not getattr(message, "is_followup", False))

        if is_live_send and is_cold_external:
            is_authorized = message.actor_type in ("HUMAN", "CEO_HUMAN", "OPERATOR")
            auth_detail = (
                f"Cold external send authorized by CEO/HUMAN ({message.actor_type})"
                if is_authorized
                else "Cold external outreach strictly requires explicit human CEO approval. AUTO_APPROVAL_ENABLED cannot authorize external cold outreach."
            )
        else:
            is_authorized = (
                not is_live_send
                or force_live
                or message.actor_type in ("HUMAN", "CEO_HUMAN", "OPERATOR")
                or (message.actor_type == "SYSTEM_AUTO_APPROVAL" and getattr(settings, "AUTO_APPROVAL_ENABLED", True))
            )
            auth_detail = f"Send authorized by {message.actor_type or 'POLICY'}" if is_authorized else "Message lacks valid authorization from CEO or autonomous policy"

        checks.append({
            "name": "SEND_AUTHORIZATION_POLICY",
            "passed": is_authorized,
            "detail": auth_detail
        })
        if not is_authorized:
            blocking_reasons.append(f"Message #{message.id} has not been authorized for live dispatch: {auth_detail}")

        # 14. Jurisdiction Sanction Policy Check (DE, IT, ES, CH blocked)
        country_code = (biz.country if biz and biz.country else "US").strip().upper()
        is_strict_opt_in = country_code in STRICT_OPT_IN_JURISDICTIONS
        has_verified_consent = getattr(message, "has_verified_consent", False) or False
        jurisdiction_ok = (not is_strict_opt_in) or has_verified_consent
        checks.append({
            "name": "JURISDICTION_SANCTION_POLICY",
            "passed": jurisdiction_ok,
            "detail": f"Jurisdiction '{country_code}' compliant" if jurisdiction_ok else f"Jurisdiction '{country_code}' strictly prohibited without prior explicit consent (OUTBOUND_BLOCKED)"
        })
        if not jurisdiction_ok:
            blocking_reasons.append(f"OUTBOUND_BLOCKED / jurisdiction_requires_consent: Jurisdiction '{country_code}' strictly prohibits unsolicited commercial email without verifiable prior explicit consent.")

        # 15. Recipient Classification & Entity Discrimination
        contact = None
        if biz:
            c_stmt = select(Contact).where(
                and_(Contact.business_id == biz.id, Contact.email == email)
            ).limit(1)
            contact = (await session.execute(c_stmt)).scalar_one_or_none()

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
            blocking_reasons.append(
                f"OUTBOUND_BLOCKED / personal_webmail_ineligible: Recipient uses personal webmail in jurisdiction '{country_code}' which requires corporate subscriber or explicit opt-in."
            )
        elif recipient_class == RecipientClassification.SOLE_TRADER and country_code in ("UK", "FR", "NL", "SE", "IE"):
            recipient_class_ok = False
            recipient_class_detail = f"Sole trader in jurisdiction '{country_code}' requires prior opt-in under PECR/ePrivacy (OUTBOUND_BLOCKED)"
            blocking_reasons.append(
                f"OUTBOUND_BLOCKED / sole_trader_requires_consent: Recipient is a sole trader / natural person in jurisdiction '{country_code}', requiring prior opt-in under PECR/ePrivacy."
            )
        elif recipient_class == RecipientClassification.UNKNOWN and country_code != "US":
            recipient_class_ok = False
            recipient_class_detail = f"Cannot verify recipient domain matches business entity in jurisdiction '{country_code}' (OUTBOUND_BLOCKED)"
            blocking_reasons.append(
                f"OUTBOUND_BLOCKED / unverified_recipient_entity: Cannot verify recipient domain matches business entity in '{country_code}'."
            )

        checks.append({
            "name": "RECIPIENT_CLASSIFICATION_GATE",
            "passed": recipient_class_ok,
            "detail": recipient_class_detail
        })

        # 16. Negative Disclaimer Detection
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
        checks.append({
            "name": "NEGATIVE_DISCLAIMER_CHECK",
            "passed": not has_negative_disclaimer,
            "detail": "Clean contact page without anti-marketing disclaimers" if not has_negative_disclaimer else f"Prohibited contact disclaimer detected: '{matched_phrase}'"
        })
        if has_negative_disclaimer:
            blocking_reasons.append(
                f"OUTBOUND_BLOCKED / prohibited_contact_disclaimer: Source page contains explicit notice forbidding unsolicited commercial inquiries ('{matched_phrase}')."
            )

        # 17. Jurisdiction Provenance & Lawful Basis Tracking
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

        message.compliance_notes = f"Jurisdiction: {country_code} | Recipient: {recipient_class.value} | Lawful Basis: {provenance.lawful_basis} | Decision: {provenance.compliance_decision}"
        if message.auto_approval_eligibility is None or not isinstance(message.auto_approval_eligibility, dict):
            message.auto_approval_eligibility = {}
        message.auto_approval_eligibility["jurisdiction_provenance"] = provenance.to_dict()

        provenance_ok = provenance.compliance_decision == "PERMITTED" and (not has_negative_disclaimer) and jurisdiction_ok and recipient_class_ok
        checks.append({
            "name": "PROVENANCE_AND_LAWFUL_BASIS",
            "passed": provenance_ok,
            "detail": f"Statutory basis: {provenance.lawful_basis} (Decision: {provenance.compliance_decision})"
        })
        if not provenance_ok and provenance.blocking_reason:
            if not any(provenance.blocking_reason in br for br in blocking_reasons):
                blocking_reasons.append(f"OUTBOUND_BLOCKED / {provenance.blocking_reason}")

        is_eligible = len(blocking_reasons) == 0
        return AutoApprovalResult(
            message_id=message.id,
            is_eligible=is_eligible,
            checks=checks,
            blocking_reasons=blocking_reasons
        )


    async def auto_approve_if_eligible(
        self, session: AsyncSession, message_id: int
    ) -> Tuple[bool, OutreachMessage, AutoApprovalResult]:
        """
        Evaluates and transitions a single message if eligible.
        Records truthful actor_type='SYSTEM_AUTO_APPROVAL'.
        """
        msg = await session.get(OutreachMessage, message_id)
        if not msg:
            raise ValueError(f"OutreachMessage {message_id} not found.")

        result = await self.evaluate_message_eligibility(session, msg)
        msg.auto_approval_eligibility = result.to_dict()

        if result.is_eligible:
            msg.status = OutreachStatus.APPROVED.value
            msg.approved_at = datetime.utcnow()
            msg.actor_type = "SYSTEM_AUTO_APPROVAL"

            biz = await session.get(Business, msg.business_id) if msg.business_id else None
            if biz:
                biz.pipeline_stage = PipelineStage.APPROVAL.value
                event = PipelineEvent(
                    business_id=biz.id,
                    from_stage=PipelineStage.QUALIFIED.value,
                    to_stage=PipelineStage.APPROVAL.value,
                    deal_value=0.0,
                    note="Outreach draft automatically approved by system (SYSTEM_AUTO_APPROVAL)."
                )
                session.add(event)

            await session.commit()
            logger.info(f"[AutoApprovalEngine] Message #{msg.id} to {msg.recipient_email} AUTO-APPROVED successfully.")
            return True, msg, result
        else:
            await session.commit()
            logger.info(f"[AutoApprovalEngine] Message #{msg.id} to {msg.recipient_email} not eligible for auto-approval: {'; '.join(result.blocking_reasons)}")
            return False, msg, result

    async def scan_and_auto_approve_pending(
        self, session: AsyncSession
    ) -> Dict[str, Any]:
        """
        Scans all pending messages and auto-approves eligible candidates.
        """
        q = select(OutreachMessage).where(
            OutreachMessage.status == OutreachStatus.PENDING_APPROVAL.value
        ).order_by(OutreachMessage.created_at.asc())
        pending_messages = list((await session.execute(q)).scalars().all())

        approved_count = 0
        blocked_count = 0
        results: List[Dict[str, Any]] = []

        for msg in pending_messages:
            eligible, updated_msg, eval_res = await self.auto_approve_if_eligible(session, msg.id)
            if eligible:
                approved_count += 1
            else:
                blocked_count += 1
            results.append({
                "message_id": msg.id,
                "recipient": msg.recipient_email,
                "auto_approved": eligible,
                "status": updated_msg.status,
                "reasons": eval_res.blocking_reasons
            })

        return {
            "total_pending_scanned": len(pending_messages),
            "auto_approved_count": approved_count,
            "blocked_count": blocked_count,
            "results": results
        }

auto_approval_engine = DeterministicAutoApprovalEngine()
