import os
import logging
from typing import Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)

class FirstClientModeManager:
    """
    Manages operational safety gates for FIRST CLIENT MODE.
    Permits real discovery, technical auditing, opportunity scoring, and dossier generation,
    while strictly locking outbound delivery, real payment charges, and pricing negotiations
    behind human operator authorization.
    """

    @classmethod
    def get_mode_status(cls) -> Dict[str, Any]:
        email_live = not settings.EMAIL_DRY_RUN
        payment_live = (not settings.PAYMENT_DRY_RUN) and (getattr(settings, "RAZORPAY_MODE", "test").lower() == "live")

        return {
            "mode": "FIRST_CLIENT_MODE",
            "name": "First Client Preparation Mode",
            "description": (
                "Real discovery, website auditing, and high-value scoring are active. "
                "Outreach dispatch and payments remain locked in operator-verified simulation "
                "until explicit human approval and activation."
            ),
            "permissions": {
                "real_discovery_allowed": True,
                "real_audits_allowed": True,
                "real_scoring_allowed": True,
                "real_dossiers_allowed": True,
                "outreach_live_sending": email_live,
                "payment_live_charging": payment_live,
                "human_approval_mandatory": True,
                "autonomous_negotiation_allowed": False,
                "autonomous_contract_acceptance": False,
                "commercial_threshold_usd": settings.MINIMUM_SERVICE_VALUE_USD
            },
            "safeguards": {
                "email_dry_run": settings.EMAIL_DRY_RUN,
                "payment_dry_run": settings.PAYMENT_DRY_RUN,
                "razorpay_mode": getattr(settings, "RAZORPAY_MODE", "test"),
                "human_takeover_lock": "ACTIVE",
                "non_fabrication_policy": "STRICT_ENFORCED"
            }
        }

    @classmethod
    def verify_outreach_allowed(cls, is_operator_approved: bool) -> None:
        """Enforces that AI cannot autonomously send cold outreach."""
        if not is_operator_approved:
            raise RuntimeError(
                "[FIRST CLIENT MODE SAFEGUARD] Automated direct outreach dispatch is strictly blocked. "
                "Explicit operator sign-off in the Authorization Queue is mandatory."
            )

first_client_mode = FirstClientModeManager()
