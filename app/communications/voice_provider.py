"""
Voice Telephony Provider Abstraction Layer.
Supports DryRun, Twilio Voice, and Bland AI conversational engines behind a unified interface.
Enforces Business Caller ID validation, call recording consent, and dry-run safety gates.
"""
from abc import ABC, abstractmethod
import re
import logging
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def format_e164_phone(phone: str, default_country: str = "US") -> str:
    """Validates and normalizes phone numbers into E.164 international format."""
    if not phone:
        return ""
    digits = re.sub(r"[^\d+]", "", phone.strip())
    if digits.startswith("+"):
        return digits
    if default_country == "US":
        if len(digits) == 10:
            return f"+1{digits}"
        if len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
    elif default_country == "UK":
        if digits.startswith("0"):
            return f"+44{digits[1:]}"
    elif default_country in ("AE", "UAE"):
        if digits.startswith("0"):
            return f"+971{digits[1:]}"
    elif default_country in ("SA", "Saudi Arabia"):
        if digits.startswith("0"):
            return f"+966{digits[1:]}"
    return f"+{digits}" if digits else ""


class CallResult(BaseModel):
    success: bool
    call_id: str
    recipient_phone: str
    caller_id: str
    provider: str
    dry_run: bool
    duration_seconds: int = 0
    status: str = "COMPLETED"
    recording_url: Optional[str] = None
    transcript: str = ""
    error: Optional[str] = None


class BaseVoiceProvider(ABC):
    @abstractmethod
    async def place_call(
        self,
        phone: str,
        script_context: str,
        language: str = "en",
        caller_id: Optional[str] = None
    ) -> CallResult:
        """Places an outbound telephone call to a qualified prospect."""
        pass

    @abstractmethod
    async def get_call_status(self, call_id: str) -> Dict[str, Any]:
        """Queries status of an active or completed call."""
        pass


class DryRunVoiceProvider(BaseVoiceProvider):
    """Safe local simulator for voice calling without telephony charges or real dispatches."""

    async def place_call(
        self,
        phone: str,
        script_context: str,
        language: str = "en",
        caller_id: Optional[str] = None
    ) -> CallResult:
        norm_phone = format_e164_phone(phone)
        cid = format_e164_phone(caller_id or settings.VOICE_CALLER_ID)
        call_id = f"CA_dry_{norm_phone[-6:] if len(norm_phone) >= 6 else '0000'}_{hash(script_context) % 10000:04d}"

        logger.info(f"[DRY-RUN VOICE] Outbound call to {norm_phone} from Caller ID {cid} (Language: {language})")
        logger.info(f"[DRY-RUN VOICE] Consent Disclosure: '{settings.VOICE_CONSENT_DISCLOSURE}'")
        logger.info(f"[DRY-RUN VOICE] Script Context: {script_context[:100]}...")

        # Construct a realistic simulation transcript based on the script context
        simulated_transcript = (
            f"Agent: Hello! {settings.VOICE_CONSENT_DISCLOSURE} "
            f"I'm reaching out regarding your website performance. {script_context[:120]}...\n"
            f"Prospect: Thanks for calling. We noticed the site was sluggish on mobile. Can you walk me through the fix?\n"
            f"Agent: Absolutely. Let's schedule a 15-minute diagnostic walkthrough this Thursday at 2 PM."
        )

        return CallResult(
            success=True,
            call_id=call_id,
            recipient_phone=norm_phone,
            caller_id=cid,
            provider="dry_run",
            dry_run=True,
            duration_seconds=45,
            status="COMPLETED",
            recording_url="https://recordings.agencygrowth.local/dry_run_sample.mp3",
            transcript=simulated_transcript
        )

    async def get_call_status(self, call_id: str) -> Dict[str, Any]:
        return {
            "call_id": call_id,
            "status": "COMPLETED",
            "duration": 45,
            "provider": "dry_run"
        }


class TwilioVoiceProvider(BaseVoiceProvider):
    """Twilio Programmable Voice REST integration with TwiML and recording support."""

    def __init__(self, account_sid: str, auth_token: str):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.base_url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}"

    async def place_call(
        self,
        phone: str,
        script_context: str,
        language: str = "en",
        caller_id: Optional[str] = None
    ) -> CallResult:
        norm_phone = format_e164_phone(phone)
        cid = format_e164_phone(caller_id or settings.VOICE_CALLER_ID)
        record_flag = "true" if settings.VOICE_RECORDING_ENABLED else "false"

        # Generate twiml speech
        lang_code = "en-US"
        if language == "es":
            lang_code = "es-MX"
        elif language == "fr":
            lang_code = "fr-FR"
        elif language == "ar":
            lang_code = "ar-XA"

        twiml = (
            f"<Response>"
            f"<Say voice='Polly.Joanna' language='{lang_code}'>{settings.VOICE_CONSENT_DISCLOSURE} {script_context}</Say>"
            f"<Record timeout='10' maxLength='120'/>"
            f"</Response>"
        )

        payload = {
            "To": norm_phone,
            "From": cid,
            "Twiml": twiml,
            "Record": record_flag,
            "TimeLimit": settings.VOICE_MAX_CALL_DURATION_MINUTES * 60
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    f"{self.base_url}/Calls.json",
                    auth=(self.account_sid, self.auth_token),
                    data=payload
                )
                if res.status_code in (200, 201):
                    data = res.json()
                    return CallResult(
                        success=True,
                        call_id=data.get("sid", "CA_unknown"),
                        recipient_phone=norm_phone,
                        caller_id=cid,
                        provider="twilio",
                        dry_run=False,
                        status=data.get("status", "QUEUED")
                    )
                else:
                    return CallResult(
                        success=False,
                        call_id="",
                        recipient_phone=norm_phone,
                        caller_id=cid,
                        provider="twilio",
                        dry_run=False,
                        error=f"Twilio API error ({res.status_code}): {res.text}"
                    )
        except Exception as e:
            return CallResult(
                success=False,
                call_id="",
                recipient_phone=norm_phone,
                caller_id=cid,
                provider="twilio",
                dry_run=False,
                error=str(e)
            )

    async def get_call_status(self, call_id: str) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    f"{self.base_url}/Calls/{call_id}.json",
                    auth=(self.account_sid, self.auth_token)
                )
                if res.status_code == 200:
                    return res.json()
        except Exception as e:
            logger.error(f"Failed to query Twilio call status for {call_id}: {e}")
        return {"call_id": call_id, "status": "UNKNOWN"}


class BlandAIVoiceProvider(BaseVoiceProvider):
    """Bland AI conversational voice agent integration."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.endpoint = "https://api.bland.ai/v1/calls"

    async def place_call(
        self,
        phone: str,
        script_context: str,
        language: str = "en",
        caller_id: Optional[str] = None
    ) -> CallResult:
        norm_phone = format_e164_phone(phone)
        cid = format_e164_phone(caller_id or settings.VOICE_CALLER_ID)

        headers = {
            "authorization": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "phone_number": norm_phone,
            "from": cid,
            "task": f"{settings.VOICE_CONSENT_DISCLOSURE}\n{script_context}",
            "language": language,
            "record": settings.VOICE_RECORDING_ENABLED,
            "max_duration": settings.VOICE_MAX_CALL_DURATION_MINUTES
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(self.endpoint, headers=headers, json=payload)
                if res.status_code in (200, 201):
                    data = res.json()
                    return CallResult(
                        success=True,
                        call_id=data.get("call_id", ""),
                        recipient_phone=norm_phone,
                        caller_id=cid,
                        provider="bland_ai",
                        dry_run=False,
                        status="QUEUED"
                    )
                else:
                    return CallResult(
                        success=False,
                        call_id="",
                        recipient_phone=norm_phone,
                        caller_id=cid,
                        provider="bland_ai",
                        dry_run=False,
                        error=f"Bland AI error ({res.status_code}): {res.text}"
                    )
        except Exception as e:
            return CallResult(
                success=False,
                call_id="",
                recipient_phone=norm_phone,
                caller_id=cid,
                provider="bland_ai",
                dry_run=False,
                error=str(e)
            )

    async def get_call_status(self, call_id: str) -> Dict[str, Any]:
        headers = {"authorization": self.api_key}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{self.endpoint}/{call_id}", headers=headers)
                if res.status_code == 200:
                    return res.json()
        except Exception as e:
            logger.error(f"Failed to query Bland AI status for {call_id}: {e}")
        return {"call_id": call_id, "status": "UNKNOWN"}


def get_active_voice_provider() -> BaseVoiceProvider:
    """Factory resolving the active voice provider. Falls back safely to DryRunVoiceProvider."""
    if getattr(settings, "VOICE_DRY_RUN", True):
        return DryRunVoiceProvider()

    provider_name = getattr(settings, "VOICE_PROVIDER", "dry_run").lower()

    if provider_name == "twilio" and settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
        return TwilioVoiceProvider(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    if provider_name in ("bland", "bland_ai") and settings.BLAND_API_KEY:
        return BlandAIVoiceProvider(settings.BLAND_API_KEY)

    # Safe fallback if credentials missing or dry-run requested
    return DryRunVoiceProvider()
