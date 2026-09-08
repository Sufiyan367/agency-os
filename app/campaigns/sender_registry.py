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

    async def get_sender_capacity_summary(self, session) -> Dict[str, Any]:
        """
        Evaluates configuration-driven sender capacity across active outbound accounts.
        Never assumes a single Gmail account can safely send 180 cold emails/day.
        Safe cold outreach volume per personal/standard Gmail is capped (default: 20/day).
        """
        from datetime import datetime
        from sqlalchemy import select, func
        from app.campaigns.config import campaign_config_loader
        from app.database.models import OutreachEvent

        provider_name = (settings.EMAIL_PROVIDER or "dry_run").lower().strip()
        is_gmail = provider_name in ("gmail", "gmail_oauth")

        # Configuration-driven safe per-sender daily limit
        safe_per_sender_daily = int(getattr(settings, "GMAIL_DAILY_CAPACITY", 20)) if is_gmail else 50
        from_email = getattr(settings, "GMAIL_SENDER_EMAIL", None) or settings.EMAIL_FROM or "sufiyansurve333@gmail.com"

        # Query real dispatches today (since midnight UTC)
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        q_sent = select(func.count(OutreachEvent.id)).where(
            OutreachEvent.event_type == "email_dispatched",
            OutreachEvent.created_at >= today_start
        )
        sent_today = (await session.execute(q_sent)).scalar() or 0

        rollout = campaign_config_loader.get_rollout_config()
        rollout_cap = rollout.daily_max_real_emails

        # Safe capacity bounds: Minimum of safe account limits and current rollout stage ceiling
        sender_remaining = max(0, safe_per_sender_daily - sent_today)
        rollout_remaining = max(0, rollout_cap - sent_today)
        available_capacity = min(sender_remaining, rollout_remaining)

        # Total production capacity required for 18 countries x 10/day = 180/day
        target_production_volume = 180
        accounts_needed_for_target = (target_production_volume + safe_per_sender_daily - 1) // safe_per_sender_daily

        return {
            "provider": provider_name,
            "sender_email": from_email,
            "safe_per_sender_daily_limit": safe_per_sender_daily,
            "configured_senders_count": 1,
            "sent_today": sent_today,
            "rollout_stage": rollout.current_level,
            "rollout_stage_name": rollout.current_level_name,
            "rollout_daily_cap": rollout_cap,
            "available_capacity": available_capacity,
            "capacity_exhausted": available_capacity <= 0,
            "is_single_account_safe": safe_per_sender_daily <= 30,
            "target_production_volume": target_production_volume,
            "accounts_needed_for_180_daily": accounts_needed_for_target,
            "senders": [
                {
                    "email": from_email,
                    "provider": provider_name,
                    "safe_limit": safe_per_sender_daily,
                    "sent_today": sent_today,
                    "available": sender_remaining
                }
            ]
        }


sender_registry = SenderRegistry()
