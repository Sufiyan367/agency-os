"""
Voice Provider Abstractions.
Keeps DryRunVoiceProvider as default. Zero live outbound telephony without explicit configuration.
"""
from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)


class CallResult(BaseModel):
    success: bool
    call_id: str
    recipient_phone: str
    dry_run: bool
    duration_seconds: int = 0
    transcript: str = ""
    error: Optional[str] = None


class BaseVoiceProvider(ABC):
    @abstractmethod
    async def place_call(self, phone: str, script_context: str, language: str = "en") -> CallResult:
        pass


class DryRunVoiceProvider(BaseVoiceProvider):
    async def place_call(self, phone: str, script_context: str, language: str = "en") -> CallResult:
        logger.info(f"[DRY-RUN VOICE] Calling: {phone} (Language: {language}) | Script: {script_context[:60]}...")
        return CallResult(
            success=True,
            call_id=f"dry_voice_{phone[-4:] if len(phone) >= 4 else '0000'}",
            recipient_phone=phone,
            dry_run=True,
            duration_seconds=30,
            transcript="Simulated initial voice consultation invitation completed in test mode."
        )
