import os
import re
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from app.core.config import settings
from app.outreach.providers.factory import get_email_provider
from app.outreach.contact_verifier import contactability_verifier

logger = logging.getLogger(__name__)

ENV_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")

class SettingsManager:
    """
    Manages runtime configuration, persistent .env updates, credential masking,
    test email verification gates, and production safety locks.
    Never exposes raw secrets through API responses.
    """

    _test_email_verified: bool = False
    _last_test_email_recipient: Optional[str] = None
    _last_test_email_timestamp: Optional[str] = None

    @classmethod
    def read_env_file(cls) -> Dict[str, str]:
        """Reads key-value pairs from .env if present."""
        env_dict = {}
        if os.path.exists(ENV_FILE_PATH):
            try:
                with open(ENV_FILE_PATH, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            env_dict[k.strip()] = v.strip().strip('"').strip("'")
            except Exception as e:
                logger.error(f"Error reading .env file: {e}")
        return env_dict

    @classmethod
    def write_env_key(cls, key: str, value: str):
        """Updates or appends a key in .env file safely."""
        lines = []
        key_found = False
        if os.path.exists(ENV_FILE_PATH):
            try:
                with open(ENV_FILE_PATH, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except Exception as e:
                logger.error(f"Error reading .env for update: {e}")

        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _ = stripped.split("=", 1)
                if k.strip() == key:
                    new_lines.append(f"{key}={value}\n")
                    key_found = True
                    continue
            new_lines.append(line)

        if not key_found:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            new_lines.append(f"{key}={value}\n")

        try:
            with open(ENV_FILE_PATH, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except Exception as e:
            logger.error(f"Error writing to .env file: {e}")

    @classmethod
    def mask_secret(cls, secret: Optional[str], prefix_len: int = 4) -> Optional[str]:
        if not secret:
            return None
        s = secret.strip()
        if len(s) <= prefix_len:
            return "••••••••"
        return f"{s[:prefix_len]}••••••••"

    @classmethod
    def get_email_status(cls) -> str:
        """
        Determines current email operational status:
        - LIVE: EMAIL_DRY_RUN is False and credentials exist.
        - CONFIGURED: Credentials exist, test verified, but EMAIL_DRY_RUN is True.
        - DRY RUN: Default safe mode.
        """
        if not settings.EMAIL_DRY_RUN:
            return "LIVE"
        
        provider = (settings.EMAIL_PROVIDER or "dry_run").lower()
        has_creds = False
        if provider == "resend" and settings.RESEND_API_KEY:
            has_creds = True
        elif provider == "sendgrid" and settings.SENDGRID_API_KEY:
            has_creds = True
        elif provider == "smtp" and settings.SMTP_HOST and settings.SMTP_USER:
            has_creds = True

        if has_creds and cls._test_email_verified:
            return "CONFIGURED"
        return "DRY RUN"

    @classmethod
    def get_payment_status(cls) -> str:
        """
        Determines current payment operational status:
        - NOT CONFIGURED: Missing RAZORPAY_KEY_ID
        - LIVE: RAZORPAY_MODE is 'live' and PAYMENT_DRY_RUN is False
        - TEST MODE: Configured with test credentials or running in test mode
        """
        key_id = getattr(settings, "RAZORPAY_KEY_ID", None)
        mode = getattr(settings, "RAZORPAY_MODE", "test").lower()
        dry_run = getattr(settings, "PAYMENT_DRY_RUN", True)

        if not key_id:
            return "NOT CONFIGURED"
        if mode == "live" and not dry_run:
            return "LIVE"
        return "TEST MODE"

    @classmethod
    def get_masked_settings(cls) -> Dict[str, Any]:
        """
        Returns complete sanitized configuration for operator UI.
        Strictly guarantees NO raw secrets are exposed in response.
        """
        email_status = cls.get_email_status()
        payment_status = cls.get_payment_status()

        return {
            "email": {
                "provider": settings.EMAIL_PROVIDER,
                "from_email": settings.EMAIL_FROM,
                "from_name": settings.OUTREACH_FROM_NAME,
                "reply_to": settings.EMAIL_REPLY_TO,
                "dry_run": settings.EMAIL_DRY_RUN,
                "status": email_status,
                "test_verified": cls._test_email_verified,
                "last_test_recipient": cls._last_test_email_recipient,
                "last_test_timestamp": cls._last_test_email_timestamp,
                "resend_configured": bool(settings.RESEND_API_KEY),
                "resend_key_masked": cls.mask_secret(settings.RESEND_API_KEY, prefix_len=3),
                "sendgrid_configured": bool(settings.SENDGRID_API_KEY),
                "sendgrid_key_masked": cls.mask_secret(settings.SENDGRID_API_KEY, prefix_len=3),
                "smtp_host": settings.SMTP_HOST or "",
                "smtp_port": settings.SMTP_PORT,
                "smtp_username": settings.SMTP_USER or "",
                "smtp_password_configured": bool(settings.SMTP_PASSWORD)
            },
            "payments": {
                "provider": settings.PAYMENT_PROVIDER,
                "mode": getattr(settings, "RAZORPAY_MODE", "test"),
                "status": payment_status,
                "key_id": settings.RAZORPAY_KEY_ID or "",
                "key_secret_configured": bool(settings.RAZORPAY_KEY_SECRET),
                "key_secret_masked": cls.mask_secret(settings.RAZORPAY_KEY_SECRET, prefix_len=2),
                "currency": getattr(settings, "RAZORPAY_CURRENCY", "USD"),
                "default_advance_percentage": getattr(settings, "DEFAULT_ADVANCE_PERCENTAGE", 40.0),
                "minimum_service_value_usd": settings.MINIMUM_SERVICE_VALUE_USD,
                "dry_run": settings.PAYMENT_DRY_RUN
            },
            "system": {
                "app_name": settings.APP_NAME,
                "env": settings.APP_ENV,
                "debug": settings.DEBUG,
                "human_approval_required": True,
                "minimum_commercial_gate": settings.MINIMUM_SERVICE_VALUE_USD
            }
        }

    @classmethod
    async def update_email_settings(
        cls,
        provider: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        resend_api_key: Optional[str] = None,
        sendgrid_api_key: Optional[str] = None,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_username: Optional[str] = None,
        smtp_password: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Updates email configuration in runtime settings and persists to .env.
        """
        if provider:
            prov_clean = provider.lower().strip()
            if prov_clean not in ("dry_run", "resend", "sendgrid", "smtp"):
                raise ValueError(f"Unsupported email provider: '{provider}'")
            settings.EMAIL_PROVIDER = prov_clean
            cls.write_env_key("EMAIL_PROVIDER", prov_clean)

        if from_email:
            settings.EMAIL_FROM = from_email.strip()
            settings.OUTREACH_FROM_EMAIL = from_email.strip()
            cls.write_env_key("EMAIL_FROM", from_email.strip())

        if from_name:
            settings.OUTREACH_FROM_NAME = from_name.strip()
            cls.write_env_key("OUTREACH_FROM_NAME", from_name.strip())

        if reply_to:
            settings.EMAIL_REPLY_TO = reply_to.strip()
            cls.write_env_key("EMAIL_REPLY_TO", reply_to.strip())

        # Update credentials only if provided and not masked placeholder
        if resend_api_key and not resend_api_key.startswith("••"):
            settings.RESEND_API_KEY = resend_api_key.strip()
            cls.write_env_key("RESEND_API_KEY", resend_api_key.strip())

        if sendgrid_api_key and not sendgrid_api_key.startswith("••"):
            settings.SENDGRID_API_KEY = sendgrid_api_key.strip()
            cls.write_env_key("SENDGRID_API_KEY", sendgrid_api_key.strip())

        if smtp_host:
            settings.SMTP_HOST = smtp_host.strip()
            cls.write_env_key("SMTP_HOST", smtp_host.strip())

        if smtp_port is not None:
            settings.SMTP_PORT = int(smtp_port)
            cls.write_env_key("SMTP_PORT", str(smtp_port))

        if smtp_username:
            settings.SMTP_USER = smtp_username.strip()
            cls.write_env_key("SMTP_USERNAME", smtp_username.strip())

        if smtp_password and not smtp_password.startswith("••"):
            settings.SMTP_PASSWORD = smtp_password.strip()
            cls.write_env_key("SMTP_PASSWORD", smtp_password.strip())

        logger.info(f"[SettingsManager] Email settings updated (Provider: {settings.EMAIL_PROVIDER})")
        return cls.get_masked_settings()

    @classmethod
    async def send_test_email(cls, recipient_email: str) -> Dict[str, Any]:
        """
        Transmits a diagnostic test email via the active provider to verify credentials.
        Required before Live Email mode can be unlocked.
        """
        # 1. Validate recipient format
        res = contactability_verifier.verify_contact_email(recipient_email, None, allow_free_mail=True)
        if not res.is_valid:
            raise ValueError(f"Invalid test recipient address: {res.reason}")

        provider = get_email_provider()
        subject = f"[JARVIS Diagnostics] Verification Test Email ({settings.EMAIL_PROVIDER.upper()})"
        body = (
            f"Hello,\n\n"
            f"This is a verified test dispatch from your JARVIS // AG Revenue Operations system.\n\n"
            f"Provider: {provider.__class__.__name__}\n"
            f"From: {settings.EMAIL_FROM}\n"
            f"Reply-To: {settings.EMAIL_REPLY_TO}\n"
            f"Mode: {'DRY_RUN (Simulated)' if settings.EMAIL_DRY_RUN else 'LIVE'}\n"
            f"Timestamp: {datetime.utcnow().isoformat()}Z\n\n"
            f"If you received this message, outbound delivery is functioning correctly."
        )

        try:
            delivery_res = await provider.send_email(
                to_email=recipient_email,
                subject=subject,
                body=body,
                from_email=settings.EMAIL_FROM,
                from_name=settings.OUTREACH_FROM_NAME,
                reply_to=settings.EMAIL_REPLY_TO
            )
        except Exception as e:
            logger.error(f"[SettingsManager] Test email failed: {e}")
            raise RuntimeError(f"Test email dispatch failed via {provider.__class__.__name__}: {str(e)}")

        if delivery_res.get("status") != "SUCCESS":
            raise RuntimeError(f"Provider returned error: {delivery_res}")

        cls._test_email_verified = True
        cls._last_test_email_recipient = recipient_email
        cls._last_test_email_timestamp = datetime.utcnow().isoformat()

        logger.info(f"[SettingsManager] Test email succeeded for {recipient_email} via {delivery_res.get('provider')}")
        return {
            "success": True,
            "provider": delivery_res.get("provider"),
            "message_id": delivery_res.get("message_id"),
            "recipient": recipient_email,
            "test_verified": True
        }

    @classmethod
    async def toggle_live_email(cls, enabled: bool) -> Dict[str, Any]:
        """
        Explicit operator action to toggle live email delivery.
        Strict Safety Invariant:
        Cannot enable live email unless credentials exist AND test email has succeeded.
        """
        if enabled:
            provider = (settings.EMAIL_PROVIDER or "dry_run").lower()
            if provider == "dry_run":
                raise ValueError("Cannot enable Live Email while provider is set to 'dry_run'. Select Resend, SendGrid, or SMTP.")

            # Verify credentials exist
            if provider == "resend" and not settings.RESEND_API_KEY:
                raise ValueError("Cannot enable Live Email: RESEND_API_KEY is not configured.")
            if provider == "sendgrid" and not settings.SENDGRID_API_KEY:
                raise ValueError("Cannot enable Live Email: SENDGRID_API_KEY is not configured.")
            if provider == "smtp" and (not settings.SMTP_HOST or not settings.SMTP_USER):
                raise ValueError("Cannot enable Live Email: SMTP_HOST and SMTP_USERNAME are not configured.")

            # Verify test email passed
            if not cls._test_email_verified:
                raise RuntimeError(
                    "Safety Lock Active: You must send a successful test email before live mode can be enabled."
                )

            settings.EMAIL_DRY_RUN = False
            cls.write_env_key("EMAIL_DRY_RUN", "False")
            logger.warning("[SettingsManager] ⚠️ LIVE EMAIL SENDING ACTIVATED BY OPERATOR ⚠️")
        else:
            settings.EMAIL_DRY_RUN = True
            cls.write_env_key("EMAIL_DRY_RUN", "True")
            logger.info("[SettingsManager] Email delivery returned to DRY_RUN mode.")

        return cls.get_masked_settings()

    @classmethod
    async def update_payment_settings(
        cls,
        key_id: Optional[str] = None,
        key_secret: Optional[str] = None,
        mode: Optional[str] = None,
        currency: Optional[str] = None,
        default_advance_percentage: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Updates Razorpay payment settings.
        Validates credentials before enabling Live mode.
        """
        if key_id is not None:
            clean_kid = key_id.strip()
            settings.RAZORPAY_KEY_ID = clean_kid
            cls.write_env_key("RAZORPAY_KEY_ID", clean_kid)

        if key_secret is not None and not key_secret.startswith("••"):
            clean_ksec = key_secret.strip()
            settings.RAZORPAY_KEY_SECRET = clean_ksec
            cls.write_env_key("RAZORPAY_KEY_SECRET", clean_ksec)

        if currency:
            clean_curr = currency.strip().upper()
            settings.RAZORPAY_CURRENCY = clean_curr
            cls.write_env_key("RAZORPAY_CURRENCY", clean_curr)

        if default_advance_percentage is not None:
            pct = float(default_advance_percentage)
            if pct <= 0 or pct > 100:
                raise ValueError("Advance percentage must be between 1% and 100%.")
            setattr(settings, "DEFAULT_ADVANCE_PERCENTAGE", pct)
            cls.write_env_key("DEFAULT_ADVANCE_PERCENTAGE", str(pct))

        if mode:
            mode_clean = mode.lower().strip()
            if mode_clean not in ("test", "live"):
                raise ValueError("RAZORPAY_MODE must be either 'test' or 'live'.")

            if mode_clean == "live":
                # Ensure credentials exist
                kid = getattr(settings, "RAZORPAY_KEY_ID", None)
                ksec = getattr(settings, "RAZORPAY_KEY_SECRET", None)
                if not kid or not ksec:
                    raise ValueError("Cannot switch to Live Mode: RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be configured first.")
                
                setattr(settings, "RAZORPAY_MODE", "live")
                settings.PAYMENT_DRY_RUN = False
                settings.PAYMENTS_ENABLED = True
                cls.write_env_key("RAZORPAY_MODE", "live")
                cls.write_env_key("PAYMENT_DRY_RUN", "false")
                cls.write_env_key("PAYMENTS_ENABLED", "true")
                logger.warning("[SettingsManager] ⚠️ RAZORPAY LIVE MODE ACTIVATED BY OPERATOR ⚠️")
            else:
                setattr(settings, "RAZORPAY_MODE", "test")
                settings.PAYMENT_DRY_RUN = True
                cls.write_env_key("RAZORPAY_MODE", "test")
                cls.write_env_key("PAYMENT_DRY_RUN", "true")
                logger.info("[SettingsManager] Razorpay set to TEST MODE.")

        return cls.get_masked_settings()

settings_manager = SettingsManager()
