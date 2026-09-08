"""
WhatsApp Compliance & Channel Eligibility Guard.

Enforces strict compliance for WhatsApp business-initiated outreach:
1. A public phone number alone MUST NOT be treated as WhatsApp marketing consent.
2. Unsolicited bulk WhatsApp messages are strictly forbidden.
3. Only dispatch WhatsApp outreach when the contact has verifiable opt-in consent
   AND all applicable platform/compliance requirements are satisfied.
4. Otherwise, contact is stored as WhatsApp-ineligible, and communications continue
   exclusively through permitted channels (e.g. Email).
"""

from typing import Dict, Any, Optional
from app.core.logging import logger


class WhatsAppEligibilityStatus:
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE_NO_CONSENT = "INELIGIBLE_NO_CONSENT"
    INELIGIBLE_NO_PHONE = "INELIGIBLE_NO_PHONE"
    SUPPRESSED_OPTED_OUT = "SUPPRESSED_OPTED_OUT"
    INELIGIBLE_NON_COMPLIANT = "INELIGIBLE_NON_COMPLIANT"


def evaluate_whatsapp_eligibility(
    phone: Optional[str],
    has_explicit_opt_in: bool = False,
    is_opted_out: bool = False,
    platform_compliant: bool = False
) -> Dict[str, Any]:
    """
    Evaluates whether a prospect contact is eligible for WhatsApp outreach.
    Enforces the non-negotiable rule:
    A public phone number alone NEVER confers marketing consent.
    """
    if not phone or not phone.strip():
        return {
            "eligible": False,
            "status": WhatsAppEligibilityStatus.INELIGIBLE_NO_PHONE,
            "reason": "No phone number available"
        }

    if is_opted_out:
        return {
            "eligible": False,
            "status": WhatsAppEligibilityStatus.SUPPRESSED_OPTED_OUT,
            "reason": "Contact has opted out or is in suppression list"
        }

    # Public phone number alone is NOT consent
    if not has_explicit_opt_in:
        return {
            "eligible": False,
            "status": WhatsAppEligibilityStatus.INELIGIBLE_NO_CONSENT,
            "reason": "Public phone number without explicit marketing opt-in consent"
        }

    if not platform_compliant:
        return {
            "eligible": False,
            "status": WhatsAppEligibilityStatus.INELIGIBLE_NON_COMPLIANT,
            "reason": "WhatsApp Business Platform template or verification requirements not satisfied"
        }

    return {
        "eligible": True,
        "status": WhatsAppEligibilityStatus.ELIGIBLE,
        "reason": "Explicit consent verified and platform compliant"
    }


def can_dispatch_whatsapp(contact: Any) -> bool:
    """
    Gate check before any WhatsApp dispatch.
    Returns True ONLY if contact is verified eligible.
    """
    if not contact:
        return False

    is_eligible = getattr(contact, "whatsapp_eligible", False)
    consent_status = getattr(contact, "whatsapp_consent_status", "")

    if not is_eligible or consent_status != WhatsAppEligibilityStatus.ELIGIBLE:
        logger.warning(
            f"[WhatsAppGuard] Blocked WhatsApp dispatch: Contact #{getattr(contact, 'id', 'unknown')} "
            f"is ineligible (Status: {consent_status or 'NO_CONSENT'}). Continuing through permitted channels."
        )
        return False

    return True
