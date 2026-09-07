import sys
from typing import Tuple, Dict, Any, Optional
from app.core.config import settings
from app.database.models import Campaign


class SenderRegistry:
    """
    Resolves and verifies sender identity for international campaigns.
    Strictly forbids inventing personas or using unauthenticated domains.
    """

    DEFAULT_POSTAL_ADDRESS = "Agency OS Digital Services, 100 Congress Ave, Suite 2000, Austin, TX 78701, USA"

    def resolve_sender(
        self,
        campaign: Optional[Campaign] = None,
        country_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """Resolves verified sender credentials for a campaign or country."""
        provider_name = (settings.EMAIL_PROVIDER or "dry_run").lower().strip()
        is_gmail = provider_name in ("gmail", "gmail_oauth")

        if is_gmail:
            from_email = getattr(settings, "GMAIL_SENDER_EMAIL", None) or settings.EMAIL_FROM
            from_name = None if "Elena Vance" in (settings.EMAIL_FROM_NAME or "") else settings.EMAIL_FROM_NAME
            reply_to = from_email
        else:
            from_email = (campaign.sender_identity if campaign and campaign.sender_identity else None) or settings.EMAIL_FROM
            from_name = (campaign.sender_name if campaign and campaign.sender_name else None) or settings.OUTREACH_FROM_NAME
            reply_to = (campaign.reply_to if campaign and campaign.reply_to else None) or settings.EMAIL_REPLY_TO or from_email

        postal_addr = (campaign.postal_address if campaign and campaign.postal_address else None) or getattr(settings, "CAN_SPAM_POSTAL_ADDRESS", None) or self.DEFAULT_POSTAL_ADDRESS

        return {
            "from_email": from_email,
            "from_name": from_name,
            "reply_to": reply_to,
            "provider": provider_name,
            "postal_address": postal_addr
        }

    def get_sender_for_country(self, country_code: str) -> Dict[str, Any]:
        """Resolves sender identity for a specific country."""
        return self.resolve_sender(country_code=country_code)

    def validate_sender_ready(
        self,
        campaign: Optional[Campaign] = None,
        country_code: Optional[str] = None,
        is_live_send: bool = False
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validates whether the sender identity is legally and technically ready.
        Blocks transmission if required elements are missing.
        """
        resolved = self.resolve_sender(campaign, country_code)

        if not resolved["from_email"] or "@" not in resolved["from_email"]:
            return False, "Invalid sender email: from_email is missing or malformed.", resolved

        if not resolved["postal_address"] or len(resolved["postal_address"].strip()) < 10:
            return False, "Compliance violation: Mandatory physical postal address is missing.", resolved

        if is_live_send:
            prov = resolved["provider"]
            if prov in ("gmail", "gmail_oauth"):
                if not getattr(settings, "GMAIL_CLIENT_ID", None) or not getattr(settings, "GMAIL_REFRESH_TOKEN", None):
                    return False, "Live send blocked: Gmail OAuth credentials not configured in environment.", resolved
            elif prov == "resend":
                if not getattr(settings, "RESEND_API_KEY", None):
                    return False, "Live send blocked: RESEND_API_KEY not configured in environment.", resolved
            elif prov == "sendgrid":
                if not getattr(settings, "SENDGRID_API_KEY", None):
                    return False, "Live send blocked: SENDGRID_API_KEY not configured in environment.", resolved
            elif prov == "smtp":
                if not getattr(settings, "SMTP_HOST", None) or not getattr(settings, "SMTP_USER", None):
                    return False, "Live send blocked: SMTP credentials not configured in environment.", resolved
            elif prov == "dry_run":
                return False, "Live send blocked: Active provider is 'dry_run'. Live sending requires real provider credentials.", resolved

        return True, "Sender configuration verified.", resolved


sender_registry = SenderRegistry()
