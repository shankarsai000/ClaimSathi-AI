"""
Speech synthesis providers for ClaimSathi AI (Phase 2).
Includes Gnani Timbre TTS REST integration and Mock fallback.
Endpoint: https://api.vachana.ai/api/v1/tts/inference
"""

from abc import ABC, abstractmethod
import logging
import re
from typing import List, Optional
import httpx
from fastapi import HTTPException
from ..config import get_settings
from ..audio_utils import generate_demo_wav

logger = logging.getLogger("claimsathi.speech")

# Official Gnani Timbre v3.0 case-sensitive inline audio tags (docs.gnani.ai)
GNANI_TIMBRE_V3_ALLOWED_TAGS = frozenset({
    "<coughs>",
    "<excited>",
    "<exhales>",
    "<giggle>",
    "<laugh>",
    "<pauses>",
    "<shouting>",
    "<sigh>",
    "<slow>",
    "<sniffles>",
    "<whispers>",
    "<yawns>",
    "<clears throat>",
})
_ANY_ANGLE_TAG_RE = re.compile(r"<[^<>]{1,32}>")

# Model-specific voices: v2.5 voices (e.g. Nalini) cannot be sent with timbre-v3.0
TIMBRE_V25_ONLY_VOICES = frozenset({"nalini"})
DEFAULT_TIMBRE_V3_VOICE = "Shivani"


def extract_gnani_audio_tags(text: str) -> List[str]:
    """Return all valid Gnani Timbre v3.0 inline audio tags present in text."""
    return [
        m.group(0)
        for m in _ANY_ANGLE_TAG_RE.finditer(text or "")
        if m.group(0) in GNANI_TIMBRE_V3_ALLOWED_TAGS
    ]


def sanitize_gnani_audio_tags(text: str) -> str:
    """Keep only official Gnani Timbre v3.0 tags and strip unsupported tags."""
    if not text:
        return ""
    cleaned = _ANY_ANGLE_TAG_RE.sub(
        lambda m: f" {m.group(0)} " if m.group(0) in GNANI_TIMBRE_V3_ALLOWED_TAGS else " ",
        text,
    )
    return re.sub(r"\s+", " ", cleaned).strip()


def strip_gnani_audio_tags(text: str) -> str:
    """Remove all inline angle-bracket audio tags for clean UI display or v2.5 TTS."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", _ANY_ANGLE_TAG_RE.sub(" ", text)).strip()


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

    def resolve_effective_voice(self, requested_voice: Optional[str] = None) -> str:
        """Ensure the selected voice is compatible with the active Gnani Timbre model."""
        model = (self.settings.gnani_tts_model or "timbre-v2.5").lower()
        is_v3 = "v3" in model
        raw_voice = (requested_voice or self.settings.gnani_tts_voice or (DEFAULT_TIMBRE_V3_VOICE if is_v3 else "Nalini")).strip()
        if is_v3 and raw_voice.lower() in TIMBRE_V25_ONLY_VOICES:
            cfg_voice = (self.settings.gnani_tts_voice or "").strip()
            if cfg_voice and cfg_voice.lower() not in TIMBRE_V25_ONLY_VOICES:
                return cfg_voice
            return DEFAULT_TIMBRE_V3_VOICE
        return raw_voice

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
        model = self.settings.gnani_tts_model or "timbre-v2.5"
        is_v3 = "v3" in model.lower()
        target_voice = self.resolve_effective_voice(voice)

        if is_v3:
            clean_text = sanitize_gnani_audio_tags(clean_text)
            if not strip_gnani_audio_tags(clean_text):
                raise HTTPException(
                    status_code=400,
                    detail="Text must contain speakable words in addition to emotion tags.",
                )
        else:
            clean_text = strip_gnani_audio_tags(clean_text)
            if not clean_text:
                raise HTTPException(status_code=400, detail="Text cannot be empty for speech synthesis.")

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
