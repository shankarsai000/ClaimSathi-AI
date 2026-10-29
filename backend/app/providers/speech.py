"""
Speech synthesis providers for ClaimSathi AI (Phase 2).
Includes Gnani Timbre TTS REST integration and Mock fallback.
Endpoint: https://api.vachana.ai/api/v1/tts/inference
"""

from abc import ABC, abstractmethod
import logging
from typing import Optional
import httpx
from fastapi import HTTPException
from ..config import get_settings
from ..audio_utils import generate_demo_wav

logger = logging.getLogger("claimsathi.speech")


class SpeechProvider(ABC):
    """Abstract interface for text-to-speech providers."""

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        language: Optional[str] = None,
        voice: Optional[str] = None,
        speed: float = 1.0,
    ) -> bytes:
        """Convert text into WAV audio bytes."""
        ...

    @abstractmethod
    def get_provider_name(self) -> str:
        ...


class GnaniTimbreProvider(SpeechProvider):
    """
    Live integration with Gnani Timbre Text-to-Speech REST API.
    Uses Timbre v2.5 model and verified voice (e.g. Nalini for hi-IN).
    Endpoint: https://api.vachana.ai/api/v1/tts/inference
    """

    def __init__(self):
        self.settings = get_settings()

    def get_provider_name(self) -> str:
        return f"Gnani Timbre ({self.settings.gnani_tts_model}) [LIVE]"

    async def synthesize(
        self,
        text: str,
        language: Optional[str] = None,
        voice: Optional[str] = None,
        speed: float = 1.0,
    ) -> bytes:
        api_key = self.settings.gnani_api_key_id
        if not api_key or not api_key.strip():
            raise HTTPException(
                status_code=400,
                detail=(
                    "Gnani API Key is not configured. Please set GNANI_API_KEY_ID in backend/.env "
                    "or enable Demo Mode to synthesize simulated voice."
                ),
            )

        clean_text = (text or "").strip()
        if not clean_text:
            raise HTTPException(status_code=400, detail="Text cannot be empty for speech synthesis.")

        endpoint = self.settings.gnani_tts_endpoint
        target_lang = language or self.settings.gnani_tts_language or "hi-IN"
        target_voice = voice or self.settings.gnani_tts_voice or "Nalini"
        model = self.settings.gnani_tts_model or "timbre-v2.5"

        # Headers - NEVER log or leak API key
        headers = {
            "X-API-Key-ID": api_key.strip(),
            "Content-Type": "application/json",
        }

        # Documented audio_config requesting standard WAV output
        payload = {
            "text": clean_text,
            "voice": target_voice,
            "model": model,
            "language": target_lang,
            "speed": max(0.5, min(2.0, float(speed))),
            "audio_config": {
                "encoding": "linear_pcm",
                "container": "wav",
                "num_channels": 1,
                "sample_rate": 24000,
                "sample_width": 2,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                )
        except httpx.TimeoutException:
            logger.error("Gnani Timbre TTS request timed out.")
            raise HTTPException(
                status_code=504,
                detail="The Gnani Text-to-Speech service timed out. Please try again.",
            )
        except httpx.RequestError as exc:
            logger.error(f"Gnani Timbre TTS network error: {exc.__class__.__name__}")
            raise HTTPException(
                status_code=502,
                detail=f"Unable to connect to Gnani Speech API: {exc.__class__.__name__}.",
            )

        # Inspect HTTP Status
        if response.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail="Authentication failed with Gnani Speech API. Please verify your GNANI_API_KEY_ID in backend/.env.",
            )
        elif response.status_code == 402:
            raise HTTPException(
                status_code=402,
                detail="Insufficient credits on your Gnani AI account for speech synthesis.",
            )
        elif response.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail="Gnani Speech API rate limit exceeded. Please wait a moment before trying again.",
            )
        elif response.status_code >= 500:
            raise HTTPException(
                status_code=502,
                detail=f"Gnani Speech API returned a server error (HTTP {response.status_code}). Please retry.",
            )
        elif response.status_code != 200:
            error_msg = response.text
            try:
                err_json = response.json()
                error_msg = err_json.get("message") or err_json.get("error") or error_msg
            except Exception:
                pass
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Gnani Speech API rejected TTS request: {error_msg}",
            )

        audio_content = response.content
        if not audio_content or len(audio_content) == 0:
            raise HTTPException(
                status_code=502,
                detail="Gnani Speech API returned empty audio content.",
            )

        # Critical requirement: Never return mock audio when real request fails
        return audio_content


class MockSpeechProvider(SpeechProvider):
    """
    Simulated TTS for Demo Mode.
    Generates a soft demo audio wave so frontend can demonstrate audio playback.
    """

    async def synthesize(
        self,
        text: str,
        language: Optional[str] = None,
        voice: Optional[str] = None,
        speed: float = 1.0,
    ) -> bytes:
        # Generates a valid 16-bit PCM WAV audio tone (1.5 seconds)
        return generate_demo_wav(duration_seconds=1.5, frequency=440.0)

    def get_provider_name(self) -> str:
        return "MockSpeech [DEMO]"
