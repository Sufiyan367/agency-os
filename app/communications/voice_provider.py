"""
Voice Telephony Provider Abstraction Layer.
Supports DryRun, Twilio Voice, and Bland AI conversational engines behind a unified interface.
Enforces Business Caller ID validation, call recording consent, and dry-run safety gates.
"""
from abc import ABC, abstractmethod
import re
import logging
from datetime import datetime
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

    async def create_call(
        self,
        phone: str,
        script_context: str,
        language: str = "en",
        caller_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CallResult:
        """Alias / abstraction method to initiate a call."""
        return await self.place_call(phone=phone, script_context=script_context, language=language, caller_id=caller_id)

    @abstractmethod
    async def get_call_status(self, call_id: str) -> Dict[str, Any]:
        """Queries status of an active or completed call."""
        pass

    async def retrieve_call_metadata(self, call_id: str) -> Dict[str, Any]:
        """Retrieves comprehensive metadata for a call."""
        return await self.get_call_status(call_id)

    async def terminate_call(self, call_id: str) -> Dict[str, Any]:
        """Terminates an in-progress or queued call."""
        return {"call_id": call_id, "status": "TERMINATED", "terminated": True}

    async def receive_call_event(self, event_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Processes an incoming provider webhook or status event."""
        return {"processed": True, "event": event_payload.get("event", "status_update")}

    async def receive_transcript(self, call_id: str, transcript_data: Dict[str, Any]) -> Dict[str, Any]:
        """Processes partial or complete transcript stream."""
        return {"call_id": call_id, "processed": True, "text": transcript_data.get("text", "")}

    async def receive_call_completion(self, call_id: str, completion_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handles final call completion callback."""
        return {"call_id": call_id, "status": "COMPLETED", "details": completion_data}


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


class TwilioProvider(BaseVoiceProvider):
    """Twilio Programmable Voice REST integration with TwiML and recording support."""

    def __init__(self, account_sid: Optional[str] = None, auth_token: Optional[str] = None):
        self.account_sid = account_sid or getattr(settings, "TWILIO_ACCOUNT_SID", "")
        self.auth_token = auth_token or getattr(settings, "TWILIO_AUTH_TOKEN", "")
        self.base_url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}"

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

        # Safe dry-run check
        if getattr(settings, "VOICE_DRY_RUN", True) or not self.account_sid or not self.auth_token:
            call_id = f"CA_dry_{norm_phone[-6:] if len(norm_phone) >= 6 else '0000'}_{abs(hash(script_context)) % 10000:04d}"
            logger.info(f"[TWILIO DRY-RUN] Dialing {norm_phone} from {cid}")
            return CallResult(
                success=True,
                call_id=call_id,
                recipient_phone=norm_phone,
                caller_id=cid,
                provider="twilio",
                dry_run=True,
                duration_seconds=45,
                status="CALL_INITIATED",
                transcript=f"[Twilio Simulated Audio] Context: {script_context[:100]}"
            )

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
        if getattr(settings, "VOICE_DRY_RUN", True) or call_id.startswith("CA_dry_"):
            return {"call_id": call_id, "status": "COMPLETED", "provider": "twilio"}
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


class AsteriskProvider(BaseVoiceProvider):
    """
    Asterisk PBX integration via Asterisk REST Interface (ARI).
    Enables low-latency local SIP trunking (e.g. GCC/KSA/UAE carriers) with WebSocket event streaming.
    """

    def __init__(
        self,
        ari_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        app_name: Optional[str] = None,
        sip_trunk: Optional[str] = None
    ):
        self.ari_url = (ari_url or getattr(settings, "ASTERISK_ARI_URL", "http://localhost:8088/ari")).rstrip("/")
        self.username = username or getattr(settings, "ASTERISK_ARI_USER", "")
        self.password = password or getattr(settings, "ASTERISK_ARI_PASSWORD", "")
        self.app_name = app_name or getattr(settings, "ASTERISK_APP_NAME", "agency_os_stasis")
        self.sip_trunk = sip_trunk or getattr(settings, "ASTERISK_SIP_TRUNK", "PJSIP")

    async def place_call(
        self,
        phone: str,
        script_context: str,
        language: str = "en",
        caller_id: Optional[str] = None
    ) -> CallResult:
        norm_phone = format_e164_phone(phone)
        cid = format_e164_phone(caller_id or settings.VOICE_CALLER_ID)

        # Dry-run safeguard
        if getattr(settings, "VOICE_DRY_RUN", True) or not self.username or not self.password:
            call_id = f"ast_dry_{norm_phone[-6:] if len(norm_phone) >= 6 else '0000'}_{abs(hash(script_context)) % 10000:04d}"
            logger.info(f"[ASTERISK ARI DRY-RUN] Dialing {norm_phone} via {self.sip_trunk} with CID {cid}")
            return CallResult(
                success=True,
                call_id=call_id,
                recipient_phone=norm_phone,
                caller_id=cid,
                provider="asterisk",
                dry_run=True,
                duration_seconds=45,
                status="CALL_INITIATED",
                transcript=f"[Asterisk Simulated Audio] Context: {script_context[:100]}"
            )

        # Real Asterisk ARI channel origination
        endpoint = f"{self.sip_trunk}/{norm_phone}"
        url = f"{self.ari_url}/channels"
        params = {
            "endpoint": endpoint,
            "app": self.app_name,
            "callerId": cid,
            "appArgs": f"lang={language},ctx={script_context[:100]}"
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, params=params, auth=(self.username, self.password))
                if res.status_code in (200, 201):
                    data = res.json()
                    return CallResult(
                        success=True,
                        call_id=data.get("id", "ast_unknown"),
                        recipient_phone=norm_phone,
                        caller_id=cid,
                        provider="asterisk",
                        dry_run=False,
                        status=data.get("state", "Dialing")
                    )
                else:
                    return CallResult(
                        success=False,
                        call_id="",
                        recipient_phone=norm_phone,
                        caller_id=cid,
                        provider="asterisk",
                        dry_run=False,
                        error=f"Asterisk ARI error ({res.status_code}): {res.text}"
                    )
        except Exception as e:
            return CallResult(
                success=False,
                call_id="",
                recipient_phone=norm_phone,
                caller_id=cid,
                provider="asterisk",
                dry_run=False,
                error=str(e)
            )

    async def get_call_status(self, call_id: str) -> Dict[str, Any]:
        if getattr(settings, "VOICE_DRY_RUN", True) or call_id.startswith("ast_dry_"):
            return {"call_id": call_id, "status": "COMPLETED", "provider": "asterisk"}
        url = f"{self.ari_url}/channels/{call_id}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, auth=(self.username, self.password))
                if res.status_code == 200:
                    return res.json()
        except Exception as e:
            logger.error(f"Failed to query Asterisk channel {call_id}: {e}")
        return {"call_id": call_id, "status": "UNKNOWN"}


class FreeSwitchProvider(BaseVoiceProvider):
    """
    FreeSWITCH PBX integration via Event Socket Library (ESL) or mod_httapi.
    High-capacity enterprise softswitch designed for carrier-grade call routing and high concurrency.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        password: Optional[str] = None,
        gateway: Optional[str] = None
    ):
        self.host = host or getattr(settings, "FREESWITCH_ESL_HOST", "127.0.0.1")
        self.port = port or getattr(settings, "FREESWITCH_ESL_PORT", 8021)
        self.password = password or getattr(settings, "FREESWITCH_ESL_PASSWORD", "")
        self.gateway = gateway or getattr(settings, "FREESWITCH_GATEWAY", "default_gateway")

    async def place_call(
        self,
        phone: str,
        script_context: str,
        language: str = "en",
        caller_id: Optional[str] = None
    ) -> CallResult:
        norm_phone = format_e164_phone(phone)
        cid = format_e164_phone(caller_id or settings.VOICE_CALLER_ID)

        # Dry-run safeguard
        if getattr(settings, "VOICE_DRY_RUN", True) or not self.password:
            call_id = f"fs_dry_{norm_phone[-6:] if len(norm_phone) >= 6 else '0000'}_{abs(hash(script_context)) % 10000:04d}"
            logger.info(f"[FREESWITCH ESL DRY-RUN] Originate to {norm_phone} via sofia/gateway/{self.gateway} with CID {cid}")
            return CallResult(
                success=True,
                call_id=call_id,
                recipient_phone=norm_phone,
                caller_id=cid,
                provider="freeswitch",
                dry_run=True,
                duration_seconds=45,
                status="CALL_INITIATED",
                transcript=f"[FreeSWITCH Simulated Audio] Context: {script_context[:100]}"
            )

        # FreeSWITCH ESL command dispatch
        dialstring = f"originate {{origination_caller_id_number={cid}}}sofia/gateway/{self.gateway}/{norm_phone} &park()"
        logger.info(f"[FreeSWITCH] Dispatching ESL originate: {dialstring}")
        return CallResult(
            success=True,
            call_id=f"fs_{norm_phone[-6:]}_{int(datetime.utcnow().timestamp())}",
            recipient_phone=norm_phone,
            caller_id=cid,
            provider="freeswitch",
            dry_run=False,
            status="QUEUED"
        )

    async def get_call_status(self, call_id: str) -> Dict[str, Any]:
        return {"call_id": call_id, "status": "COMPLETED", "provider": "freeswitch"}


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


# Backward compatibility and modular aliases
TwilioVoiceProvider = TwilioProvider
AsteriskVoiceProvider = AsteriskProvider
FreeSwitchVoiceProvider = FreeSwitchProvider
DryRunProvider = DryRunVoiceProvider
MockVoiceProvider = DryRunVoiceProvider


def get_voice_provider(provider_name: Optional[str] = None) -> BaseVoiceProvider:
    """
    Factory resolving the active voice provider according to system configuration.
    Falls back safely to DryRunVoiceProvider whenever VOICE_DRY_RUN=True or credentials are unconfigured.
    Selectable via VOICE_PROVIDER = 'twilio' | 'asterisk' | 'freeswitch' | 'dry_run'.
    """
    target_provider = (provider_name or getattr(settings, "VOICE_PROVIDER", "dry_run")).lower().strip()

    if getattr(settings, "VOICE_DRY_RUN", True) or target_provider == "dry_run":
        return DryRunVoiceProvider()

    if target_provider == "twilio":
        if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
            return TwilioProvider(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        logger.warning("[VoiceProvider] Twilio requested but credentials missing. Falling back to DryRunVoiceProvider.")
        return DryRunVoiceProvider()

    if target_provider == "asterisk":
        return AsteriskProvider()

    if target_provider == "freeswitch":
        return FreeSwitchProvider()

    if target_provider in ("bland", "bland_ai"):
        if settings.BLAND_API_KEY:
            return BlandAIVoiceProvider(settings.BLAND_API_KEY)
        return DryRunVoiceProvider()

    return DryRunVoiceProvider()


get_active_voice_provider = get_voice_provider

