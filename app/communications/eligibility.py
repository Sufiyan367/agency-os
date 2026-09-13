"""
Deterministic Channel Eligibility & Policy Routing Engine.

Evaluates prospect reachability across communication channels:
- Email
- WhatsApp
- Voice

CORE NON-NEGOTIABLE POLICIES:
1. Deterministic rules ONLY — zero LLM hallucinated policy decisions.
2. A public phone number alone NEVER confers WhatsApp marketing consent.
3. Cold outbound calling is prohibited without explicit authorization and system-wide feature enablement.
4. Suppressed or opted-out contacts are universally blocked on affected channels.
5. Missing or synthetic contact information results in immediate channel rejection.
"""
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from app.database.models import Business, Contact, ChannelType
from app.core.config import settings
from app.outreach.whatsapp_compliance import evaluate_whatsapp_eligibility, WhatsAppEligibilityStatus
from app.communications.voice_provider import format_e164_phone


class ChannelStatus(BaseModel):
    eligible: bool
    channel: str
    destination: Optional[str] = None
    reason: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EligibilityEvaluationResult(BaseModel):
    business_id: Optional[int] = None
    primary_channel: str
    channels: Dict[str, ChannelStatus]
    summary_reason: str


class ChannelEligibilityEngine:
    """
    Evaluates reachability and policy compliance for a given business and contact.
    """

    def evaluate_business(
        self,
        business: Business,
        contact: Optional[Contact] = None,
        suppressed_emails: Optional[set] = None,
        voice_authorized: bool = False
    ) -> EligibilityEvaluationResult:
        suppressed = suppressed_emails or set()
        results: Dict[str, ChannelStatus] = {}

        # 1. Evaluate Email Channel
        email = (contact.email if contact and contact.email else business.public_email or "").strip().lower()
        if not email or "@" not in email:
            results[ChannelType.EMAIL.value] = ChannelStatus(
                eligible=False,
                channel=ChannelType.EMAIL.value,
                destination=None,
                reason="No valid email address recorded."
            )
        elif email.endswith(("@example.com", "@test.com", "@placeholder.com")):
            results[ChannelType.EMAIL.value] = ChannelStatus(
                eligible=False,
                channel=ChannelType.EMAIL.value,
                destination=email,
                reason="Disallowed synthetic or placeholder email domain."
            )
        elif email in suppressed:
            results[ChannelType.EMAIL.value] = ChannelStatus(
                eligible=False,
                channel=ChannelType.EMAIL.value,
                destination=email,
                reason="Email is present in compliance suppression list (opted out or bounced)."
            )
        else:
            results[ChannelType.EMAIL.value] = ChannelStatus(
                eligible=True,
                channel=ChannelType.EMAIL.value,
                destination=email,
                reason="Verified business domain email available and clear of suppression."
            )

        # 2. Evaluate WhatsApp Channel
        phone = (contact.phone if contact and contact.phone else business.phone or "").strip()
        has_wa_opt_in = getattr(contact, "whatsapp_eligible", False) or getattr(business, "whatsapp_eligible", False)
        is_wa_opted_out = getattr(contact, "whatsapp_consent_status", "") == WhatsAppEligibilityStatus.SUPPRESSED_OPTED_OUT

        wa_eval = evaluate_whatsapp_eligibility(
            phone=phone,
            has_explicit_opt_in=has_wa_opt_in,
            is_opted_out=is_wa_opted_out,
            platform_compliant=True
        )

        results[ChannelType.WHATSAPP.value] = ChannelStatus(
            eligible=wa_eval["eligible"],
            channel=ChannelType.WHATSAPP.value,
            destination=phone if wa_eval["eligible"] else None,
            reason=wa_eval["reason"],
            metadata={"status": wa_eval["status"]}
        )

        # 3. Evaluate Voice Channel
        voice_enabled = getattr(settings, "VOICE_CALLING_ENABLED", False)
        formatted_phone = format_e164_phone(phone) if phone else ""

        if not phone or not formatted_phone:
            results[ChannelType.VOICE.value] = ChannelStatus(
                eligible=False,
                channel=ChannelType.VOICE.value,
                destination=None,
                reason="No valid phone number for voice calling."
            )
        elif not voice_enabled:
            results[ChannelType.VOICE.value] = ChannelStatus(
                eligible=False,
                channel=ChannelType.VOICE.value,
                destination=formatted_phone,
                reason="Voice calling feature is disabled by global system policy (VOICE_CALLING_ENABLED=False)."
            )
        elif not voice_authorized:
            results[ChannelType.VOICE.value] = ChannelStatus(
                eligible=False,
                channel=ChannelType.VOICE.value,
                destination=formatted_phone,
                reason="Outbound voice calls require explicit human operator authorization."
            )
        else:
            results[ChannelType.VOICE.value] = ChannelStatus(
                eligible=True,
                channel=ChannelType.VOICE.value,
                destination=formatted_phone,
                reason="Valid E.164 phone verified, voice calling enabled, and operator authorization granted."
            )

        # Determine Primary Channel
        # Default priority: Email > WhatsApp (opted-in) > Voice (authorized)
        primary = "NONE"
        summary = "No compliant communication channel available."

        if results[ChannelType.EMAIL.value].eligible:
            primary = ChannelType.EMAIL.value
            summary = "Email selected as primary verified outreach channel."
        elif results[ChannelType.WHATSAPP.value].eligible:
            primary = ChannelType.WHATSAPP.value
            summary = "WhatsApp selected as primary compliant channel with verified opt-in."
        elif results[ChannelType.VOICE.value].eligible:
            primary = ChannelType.VOICE.value
            summary = "Voice selected as primary authorized communication channel."

        return EligibilityEvaluationResult(
            business_id=business.id if hasattr(business, "id") else None,
            primary_channel=primary,
            channels=results,
            summary_reason=summary
        )


# Global singleton instance
channel_eligibility_engine = ChannelEligibilityEngine()
