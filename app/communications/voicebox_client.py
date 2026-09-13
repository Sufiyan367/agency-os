"""
Voicebox Audio Synthesis Boundary Client.

Reference: https://github.com/jamiepine/voicebox
Voicebox is a modular, swappable audio synthesis / Text-to-Speech (TTS) engine boundary.
It provides natural voice generation for outbound or inbound voice assistant interactions.

IMPORTANT ARCHITECTURAL BOUNDARY:
- Voicebox is an AUDIO SYNTHESIS engine, NOT telephone infrastructure or carrier service.
- Telephony signaling and call management are handled by the Voice Telephony Adapter (e.g. Twilio).
- Voicebox receives text transcripts and produces high-quality speech waveforms/audio streams.
- Zero live audio synthesis network calls during automated testing (mock / dry-run safe).
"""
import os
import hashlib
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from app.core.config import settings
from app.core.logging import logger


class VoiceSynthesisResult(BaseModel):
    success: bool
    voice_id: str
    text: str
    audio_format: str = "wav"
    duration_seconds: float = 0.0
    audio_url: Optional[str] = None
    audio_base64: Optional[str] = None
    is_synthesized: bool = True
    dry_run: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class VoiceboxClient:
    """
    Interface for Voicebox TTS integration.
    Defaults to dry-run/mock synthesis when VOICEBOX_API_URL or live voice is disabled.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        default_voice_id: str = "en_neutral_professional",
        dry_run: Optional[bool] = None
    ):
        self.base_url = base_url or os.getenv("VOICEBOX_API_URL", "")
        self.api_key = api_key or os.getenv("VOICEBOX_API_KEY", "")
        self.default_voice_id = default_voice_id
        self.dry_run = dry_run if dry_run is not None else getattr(settings, "VOICE_DRY_RUN", True)

    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        pitch: float = 1.0,
        audio_format: str = "wav"
    ) -> VoiceSynthesisResult:
        """
        Synthesizes text into speech audio.
        In dry-run or unconfigured environment, returns simulated synthesis metadata without HTTP calls.
        """
        clean_text = (text or "").strip()
        selected_voice = voice_id or self.default_voice_id

        if not clean_text:
            return VoiceSynthesisResult(
                success=False,
                voice_id=selected_voice,
                text="",
                error="Text to synthesize cannot be empty."
            )

        # Estimate duration roughly based on 150 words per minute
        word_count = len(clean_text.split())
        est_duration = max(1.0, round((word_count / 150.0) * 60.0 / max(speed, 0.5), 2))
        text_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()[:12]

        if self.dry_run or not self.base_url:
            logger.info(
                f"[VoiceboxClient] Simulated TTS synthesis (dry_run=True): voice={selected_voice}, "
                f"words={word_count}, est_duration={est_duration}s"
            )
            return VoiceSynthesisResult(
                success=True,
                voice_id=selected_voice,
                text=clean_text,
                audio_format=audio_format,
                duration_seconds=est_duration,
                audio_url=f"/static/audio/mock_voicebox_{text_hash}.{audio_format}",
                is_synthesized=True,
                dry_run=True,
                metadata={
                    "engine": "voicebox-mock",
                    "speed": speed,
                    "pitch": pitch,
                    "word_count": word_count,
                    "hash": text_hash
                }
            )

        # Live Voicebox REST API client (when configured)
        import httpx
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            payload = {
                "text": clean_text,
                "voice_id": selected_voice,
                "speed": speed,
                "pitch": pitch,
                "format": audio_format
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{self.base_url.rstrip('/')}/v1/synthesize", json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    return VoiceSynthesisResult(
                        success=True,
                        voice_id=selected_voice,
                        text=clean_text,
                        audio_format=audio_format,
                        duration_seconds=data.get("duration_seconds", est_duration),
                        audio_url=data.get("audio_url"),
                        audio_base64=data.get("audio_base64"),
                        is_synthesized=True,
                        dry_run=False,
                        metadata=data.get("metadata", {})
                    )
                else:
                    return VoiceSynthesisResult(
                        success=False,
                        voice_id=selected_voice,
                        text=clean_text,
                        error=f"Voicebox API returned HTTP {resp.status_code}: {resp.text}"
                    )
        except Exception as e:
            logger.error(f"[VoiceboxClient] Synthesis failed: {e}")
            return VoiceSynthesisResult(
                success=False,
                voice_id=selected_voice,
                text=clean_text,
                error=str(e)
            )


# Global singleton instance
voicebox_client = VoiceboxClient()
