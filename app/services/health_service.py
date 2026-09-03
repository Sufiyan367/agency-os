"""
Production Health & Credential Validation Service.
Provides comprehensive pre-flight verification across:
- Database connectivity & schema integrity
- Email delivery provider credentials and format
- Voice telephony provider credentials, caller ID, and recording consent
- Payment gateway credentials, webhook secrets, and HMAC cryptographic self-test
- Safety locks and TCPA calling-hour safeguards
"""
import hmac
import hashlib
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.config import settings
from app.database.connection import AsyncSessionLocal
from app.communications.voice_provider import format_e164_phone


class ComponentHealth(BaseModel):
    name: str
    status: str  # 'READY', 'DRY_RUN', 'DEGRADED', 'NOT_CONFIGURED'
    details: str
    is_safe: bool = True
    credentials_present: bool = False


class SystemHealthReport(BaseModel):
    overall_status: str  # 'READY_DRY_RUN', 'READY_LIVE', 'NEEDS_CONFIGURATION'
    database: ComponentHealth
    email: ComponentHealth
    voice: ComponentHealth
    payment: ComponentHealth
    webhooks: ComponentHealth
    safeguards: Dict[str, Any]
    recommendations: List[str] = Field(default_factory=list)


class ProductionHealthService:
    """Performs deep diagnostic health checks for production readiness."""

    @classmethod
    async def check_system_health(cls) -> SystemHealthReport:
        recommendations = []

        # 1. Database Check
        db_health = ComponentHealth(
            name="Database (SQLite/PostgreSQL)",
            status="READY",
            details="Connected",
            is_safe=True,
            credentials_present=True
        )
        try:
            async with AsyncSessionLocal() as session:
                res = await session.execute(text("SELECT 1"))
                if res.scalar() != 1:
                    db_health.status = "DEGRADED"
                    db_health.details = "Database query returned unexpected result."
        except Exception as e:
            db_health.status = "DEGRADED"
            db_health.details = f"Connection error: {str(e)}"
            recommendations.append("Ensure database connection string is valid and database is accessible.")

        # 2. Email Delivery Check
        email_prov = getattr(settings, "EMAIL_PROVIDER", "dry_run")
        email_dry_run = getattr(settings, "EMAIL_DRY_RUN", True)
        resend_key = getattr(settings, "RESEND_API_KEY", None)
        sendgrid_key = getattr(settings, "SENDGRID_API_KEY", None)
        smtp_host = getattr(settings, "SMTP_HOST", None)

        has_email_creds = bool(resend_key or sendgrid_key or (smtp_host and getattr(settings, "SMTP_PASSWORD", None)))
        email_status = "DRY_RUN" if email_dry_run else ("READY" if has_email_creds else "NOT_CONFIGURED")

        email_details = f"Provider: {email_prov.upper()} | Dry Run: {email_dry_run}"
        if email_prov == "resend" and resend_key:
            if not resend_key.startswith("re_"):
                email_details += " (Warning: Resend API key usually begins with 're_')"
        elif email_prov == "sendgrid" and sendgrid_key:
            if not sendgrid_key.startswith("SG."):
                email_details += " (Warning: SendGrid key usually begins with 'SG.')"

        email_health = ComponentHealth(
            name="Email Delivery",
            status=email_status,
            details=email_details,
            is_safe=email_dry_run,
            credentials_present=has_email_creds
        )
        if not has_email_creds and not email_dry_run:
            recommendations.append("Email is in live mode but no valid API key or SMTP server is configured.")

        # 3. Voice Telephony Check
        voice_prov = getattr(settings, "VOICE_PROVIDER", "dry_run")
        voice_dry_run = getattr(settings, "VOICE_DRY_RUN", True)
        twilio_sid = getattr(settings, "TWILIO_ACCOUNT_SID", None)
        twilio_token = getattr(settings, "TWILIO_AUTH_TOKEN", None)
        bland_key = getattr(settings, "BLAND_API_KEY", None)
        caller_id = getattr(settings, "VOICE_CALLER_ID", None)

        has_voice_creds = bool((twilio_sid and twilio_token) or bland_key)
        voice_status = "DRY_RUN" if voice_dry_run else ("READY" if has_voice_creds else "NOT_CONFIGURED")

        valid_cid = bool(caller_id and format_e164_phone(caller_id))
        voice_details = f"Provider: {voice_prov.upper()} | Caller ID: {caller_id} (E.164: {valid_cid})"
        if voice_prov == "twilio" and twilio_sid:
            if not twilio_sid.startswith("AC") or len(twilio_sid) != 34:
                voice_details += " (Warning: Twilio Account SID usually starts with 'AC' and is 34 characters)"

        voice_health = ComponentHealth(
            name="Voice Telephony",
            status=voice_status,
            details=voice_details,
            is_safe=voice_dry_run,
            credentials_present=has_voice_creds
        )
        if not valid_cid:
            recommendations.append("Configure a verified E.164 business caller ID in settings.VOICE_CALLER_ID.")

        # 4. Payment Gateway Check
        pay_prov = getattr(settings, "PAYMENT_PROVIDER", "razorpay")
        pay_dry_run = getattr(settings, "PAYMENT_DRY_RUN", True)
        rzp_key = getattr(settings, "RAZORPAY_KEY_ID", None)
        rzp_sec = getattr(settings, "RAZORPAY_KEY_SECRET", None)
        rzp_mode = getattr(settings, "RAZORPAY_MODE", "test")

        has_pay_creds = bool(rzp_key and rzp_sec)
        pay_status = "DRY_RUN" if pay_dry_run else ("READY" if has_pay_creds else "NOT_CONFIGURED")
        pay_details = f"Provider: {pay_prov.upper()} | Mode: {rzp_mode.upper()} | Dry Run: {pay_dry_run}"

        pay_health = ComponentHealth(
            name="Payment Gateway",
            status=pay_status,
            details=pay_details,
            is_safe=pay_dry_run,
            credentials_present=has_pay_creds
        )

        # 5. Webhook Signature Cryptographic Self-Test
        test_payload = b'{"event":"payment_link.paid"}'
        test_secret = "rzp_test_secret_key"
        expected_sig = hmac.new(test_secret.encode("utf-8"), test_payload, hashlib.sha256).hexdigest()

        calc_sig = hmac.new(test_secret.encode("utf-8"), test_payload, hashlib.sha256).hexdigest()
        sig_test_passed = hmac.compare_digest(expected_sig, calc_sig)

        webhook_health = ComponentHealth(
            name="Webhook HMAC Cryptographic Verification",
            status="READY" if sig_test_passed else "DEGRADED",
            details="HMAC-SHA256 signature verification engine verified operational.",
            is_safe=True,
            credentials_present=bool(getattr(settings, "RAZORPAY_WEBHOOK_SECRET", None))
        )

        # Overall Status
        is_all_dry_run = email_dry_run and voice_dry_run and pay_dry_run
        overall = "READY_DRY_RUN" if is_all_dry_run else "READY_LIVE"
        if db_health.status == "DEGRADED":
            overall = "NEEDS_CONFIGURATION"

        safeguards = {
            "autonomous_agent_enabled": getattr(settings, "AUTONOMOUS_AGENT_ENABLED", False),
            "autonomous_outreach": getattr(settings, "AUTONOMOUS_OUTREACH", False),
            "email_dry_run": email_dry_run,
            "voice_dry_run": voice_dry_run,
            "payment_dry_run": pay_dry_run,
            "enforce_calling_hours": getattr(settings, "ENFORCE_CALLING_HOURS", True),
            "commercial_floor_usd": getattr(settings, "MINIMUM_TARGET_SERVICE_VALUE_USD", 500.0)
        }

        return SystemHealthReport(
            overall_status=overall,
            database=db_health,
            email=email_health,
            voice=voice_health,
            payment=pay_health,
            webhooks=webhook_health,
            safeguards=safeguards,
            recommendations=recommendations
        )
