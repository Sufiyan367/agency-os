"""
Voice Telephony & Conversational AI Adapter.

Integrates telephony signaling (Twilio / Mock), Speech-to-Text (STT),
Voicebox audio synthesis boundary (https://github.com/jamiepine/voicebox),
and conversation event normalization into the CRM timeline.

HARD SAFETY BOUNDARIES:
- Cold calling is disabled by default (VOICE_CALLING_ENABLED = False).
- Unrestricted cold calling is strictly prohibited.
- Calls require explicit human authorization or inbound callback request.
- Zero live telephony network calls or carrier charges during automated testing (DRY_RUN safe).
"""
import os
import re
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import logger
from app.communications.voicebox_client import voicebox_client, VoiceSynthesisResult
from app.communications.voice_provider import format_e164_phone
from app.database.models import (
    ChannelType,
    EventDirection,
    ConversationEventType
)


class VoiceCallResult(BaseModel):
    success: bool
    call_id: str
    recipient_phone: str
    caller_id: str
    status: str
    dry_run: bool = True
    duration_seconds: int = 0
    recording_url: Optional[str] = None
    transcript: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VoiceAdapter:
    """
    Adapter orchestrating voice telephony events, STT transcripts,
    and Voicebox TTS generation.
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        caller_id: Optional[str] = None,
        dry_run: Optional[bool] = None
    ):
        self.account_sid = account_sid or os.getenv("TWILIO_ACCOUNT_SID", "")
        self.auth_token = auth_token or os.getenv("TWILIO_AUTH_TOKEN", "")
        self.caller_id = caller_id or os.getenv("TWILIO_CALLER_ID", "+18005550199")
        self.dry_run = dry_run if dry_run is not None else getattr(settings, "VOICE_DRY_RUN", True)
        self.voice_calling_enabled = getattr(settings, "VOICE_CALLING_ENABLED", False)

    def can_initiate_call(self, phone: str, is_authorized: bool = False) -> Dict[str, Any]:
        """
        Safety gate: verifies phone number validity and checks calling authorization.
        """
        if not phone or not phone.strip():
            return {"allowed": False, "reason": "No valid phone number provided"}

        formatted = format_e164_phone(phone)
        if not formatted:
            return {"allowed": False, "reason": f"Phone number '{phone}' cannot be formatted to E.164"}

        if not self.voice_calling_enabled:
            return {
                "allowed": False,
                "reason": "Voice calling is disabled globally by system policy (VOICE_CALLING_ENABLED=False)"
            }

        if not is_authorized:
            return {
                "allowed": False,
                "reason": "Outbound voice call requires explicit operator authorization"
            }

        return {"allowed": True, "phone": formatted}

    async def initiate_call(
        self,
        recipient_phone: str,
        script_context: str,
        business_id: Optional[int] = None,
        caller_id: Optional[str] = None,
        is_authorized: bool = False
    ) -> VoiceCallResult:
        """
        Initiates an outbound voice call session.
        Respects safety gates and dry-run defaults.
        """
        check = self.can_initiate_call(recipient_phone, is_authorized=is_authorized)
        if not check["allowed"]:
            logger.warning(f"[VoiceAdapter] Call blocked: {check['reason']} (phone: {recipient_phone})")
            return VoiceCallResult(
                success=False,
                call_id="",
                recipient_phone=recipient_phone,
                caller_id=caller_id or self.caller_id,
                status="BLOCKED",
                dry_run=self.dry_run,
                error=check["reason"]
            )

        e164_phone = check["phone"]
        outbound_caller = caller_id or self.caller_id
        sim_call_id = f"CA{hashlib.md5(f'{e164_phone}{datetime.utcnow().isoformat()}'.encode()).hexdigest()[:24]}"

        # Dry-run execution
        if self.dry_run or not self.account_sid or not self.auth_token:
            logger.info(
                f"[VoiceAdapter] [SIMULATED CALL] To: {e164_phone} | From: {outbound_caller} | "
                f"Context: {script_context[:60]}..."
            )
            return VoiceCallResult(
                success=True,
                call_id=sim_call_id,
                recipient_phone=e164_phone,
                caller_id=outbound_caller,
                status="CALL_INITIATED",
                dry_run=True,
                metadata={
                    "script_context": script_context,
                    "business_id": business_id
                }
            )

        # Real Twilio API dispatch (when enabled and authorized)
        import httpx
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Calls.json"
        auth = (self.account_sid, self.auth_token)
        data = {
            "To": e164_phone,
            "From": outbound_caller,
            "Url": f"https://{settings.SERVER_HOST}/api/v1/voice/twiml?context={script_context[:50]}"
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, data=data, auth=auth)
                if resp.status_code in (200, 201):
                    res_json = resp.json()
                    return VoiceCallResult(
                        success=True,
                        call_id=res_json.get("sid", sim_call_id),
                        recipient_phone=e164_phone,
                        caller_id=outbound_caller,
                        status="CALL_INITIATED",
                        dry_run=False,
                        metadata=res_json
                    )
                else:
                    return VoiceCallResult(
                        success=False,
                        call_id="",
                        recipient_phone=e164_phone,
                        caller_id=outbound_caller,
                        status="FAILED",
                        dry_run=False,
                        error=f"Twilio API error {resp.status_code}: {resp.text}"
                    )
        except Exception as e:
            return VoiceCallResult(
                success=False,
                call_id="",
                recipient_phone=e164_phone,
                caller_id=outbound_caller,
                status="FAILED",
                dry_run=False,
                error=str(e)
            )

    async def synthesize_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0
    ) -> VoiceSynthesisResult:
        """
        Synthesizes agent response speech via Voicebox TTS boundary.
        """
        return await voicebox_client.synthesize(text=text, voice_id=voice_id, speed=speed)

    def parse_telephony_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parses standard Twilio or telephony status callback into a normalized ConversationEvent dictionary.
        Recognizes: CALL_INITIATED, RINGING, ANSWERED, COMPLETED, FAILED, VOICEMAIL.
        """
        call_sid = payload.get("CallSid") or payload.get("call_id") or "unknown_call"
        raw_status = (payload.get("CallStatus") or payload.get("status") or "").lower()
        from_number = payload.get("From") or payload.get("caller_id") or ""
        to_number = payload.get("To") or payload.get("recipient_phone") or ""
        direction_str = payload.get("Direction", "outbound-api").lower()
        duration = int(payload.get("CallDuration") or payload.get("duration") or 0)
        recording_url = payload.get("RecordingUrl")
        answered_by = payload.get("AnsweredBy", "")

        direction = EventDirection.INBOUND.value if "inbound" in direction_str else EventDirection.OUTBOUND.value

        event_type = ConversationEventType.CALL_INITIATED.value
        if raw_status in ("ringing", "initiated"):
            event_type = ConversationEventType.RINGING.value
        elif raw_status in ("in-progress", "answered"):
            event_type = ConversationEventType.ANSWERED.value
        elif raw_status in ("completed",):
            if "machine" in answered_by.lower():
                event_type = ConversationEventType.VOICEMAIL.value
            else:
                event_type = ConversationEventType.COMPLETED.value
        elif raw_status in ("failed", "busy", "no-answer", "canceled"):
            event_type = ConversationEventType.FAILED.value

        idempotency_key = f"voice_{call_sid}_{raw_status}"

        return {
            "channel": ChannelType.VOICE.value,
            "direction": direction,
            "event_type": event_type,
            "provider": "twilio_voice",
            "provider_event_id": call_sid,
            "idempotency_key": idempotency_key,
            "from_number": from_number,
            "to_number": to_number,
            "content": f"Voice call {call_sid} status: {raw_status} (duration: {duration}s)",
            "metadata_json": {
                "raw_status": raw_status,
                "duration_seconds": duration,
                "recording_url": recording_url,
                "answered_by": answered_by,
                "raw_payload": payload
            }
        }

    def parse_transcription_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parses Twilio or STT transcription webhook into a normalized ConversationEvent.
        """
        call_sid = payload.get("CallSid") or payload.get("call_id") or "unknown_call"
        transcript_text = payload.get("TranscriptionText") or payload.get("text") or ""
        transcription_sid = payload.get("TranscriptionSid") or f"tr_{call_sid}_{int(datetime.utcnow().timestamp())}"
        status = payload.get("TranscriptionStatus", "completed")

        idempotency_key = f"voice_transcript_{transcription_sid}"

        return {
            "channel": ChannelType.VOICE.value,
            "direction": EventDirection.INBOUND.value,
            "event_type": ConversationEventType.TRANSCRIPT_READY.value,
            "provider": "twilio_stt",
            "provider_event_id": transcription_sid,
            "idempotency_key": idempotency_key,
            "content": transcript_text,
            "metadata_json": {
                "call_sid": call_sid,
                "transcription_status": status,
                "raw_payload": payload
            }
        }


# Global singleton instance
voice_adapter = VoiceAdapter()
