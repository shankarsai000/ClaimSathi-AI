"""
Voice API routes for ClaimSathi AI (Phase 2).
Provides endpoints for Gnani Prisma STT transcription and Gnani Timbre TTS speech synthesis.
"""

from typing import Optional
from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from ..audio_utils import validate_audio_file
from ..config import get_settings
from ..models import SpeechSynthesizeRequest, VoiceTranscribeResponse
from ..providers.speech import GnaniTimbreProvider, MockSpeechProvider
from ..providers.transcription import (
    GnaniPrismaProvider,
    MockTranscriptionProvider,
    extract_claim_fields,
    generate_assistant_dialogue,
)

router = APIRouter(prefix="/voice", tags=["Voice"])

live_stt = GnaniPrismaProvider()
mock_stt = MockTranscriptionProvider()

live_tts = GnaniTimbreProvider()
mock_tts = MockSpeechProvider()


@router.post("/transcribe", response_model=VoiceTranscribeResponse)
async def transcribe_audio_file(
    audio_file: UploadFile = File(..., description="Uploaded audio file (.wav, .mp3, .ogg, .flac, .aac, .m4a)"),
    demo: bool = Form(False, description="Explicit demo mode flag"),
    language_code: Optional[str] = Form(None, description="Optional language override (e.g. hi-IN)"),
):
    """
    Transcribe spoken claim audio using Gnani Prisma ASR.
    Enforces a 30-second duration limit and supported Indic audio formats.
    Returns transcript, model info, detected language, and extracted claim fields.
    """
    settings = get_settings()

    filename = audio_file.filename or "recording.wav"
    raw_bytes = await audio_file.read()

    # Validate audio format, size, and duration (30s limit)
    normalized_mime, detected_duration = validate_audio_file(
        filename=filename,
        content_type=audio_file.content_type,
        audio_bytes=raw_bytes,
        max_duration_seconds=settings.max_audio_duration_seconds,
        max_size_bytes=settings.max_audio_upload_size_bytes,
    )

    # Route to either Demo or Live provider
    if demo:
        # Explicit demo mode requested by caller
        result = await mock_stt.transcribe(
            audio_bytes=raw_bytes,
            filename=filename,
            content_type=normalized_mime,
            language_code=language_code,
        )
    else:
        # Live Gnani Prisma STT
        # Note: Will raise HTTPException on failure; NEVER silently substitute mock!
        result = await live_stt.transcribe(
            audio_bytes=raw_bytes,
            filename=filename,
            content_type=normalized_mime,
            language_code=language_code,
        )

    # Attach detected duration to request metadata if available
    if detected_duration is not None:
        result["request_metadata"]["duration_seconds"] = round(detected_duration, 2)

    # Extract structured claim fields from the transcription
    fields, missing = extract_claim_fields(result["transcript"])

    # Generate human-like conversational dialogue in speaker's language
    dialogue_info = generate_assistant_dialogue(
        transcript=result["transcript"],
        fields=fields,
        missing_fields=missing,
        detected_language=result.get("detected_language"),
    )

    return VoiceTranscribeResponse(
        transcript=result["transcript"],
        model=result["model"],
        detected_language=result.get("detected_language"),
        is_mock=result["is_mock"],
        request_metadata=result["request_metadata"],
        fields=fields,
        missing_fields=missing,
        assistant_dialogue=dialogue_info["display_text"],
        assistant_speech_text=dialogue_info["speech_text"],
        assistant_language=dialogue_info["language"],
    )


@router.post("/speak")
async def synthesize_speech(request: SpeechSynthesizeRequest):
    """
    Synthesize text into WAV speech using Gnani Timbre TTS (Timbre v2.5 / Nalini).
    Returns binary WAV audio with Content-Type: audio/wav.
    Never silently substitutes mock audio when a live request fails.
    """
    if request.demo:
        # Explicit demo mode requested
        audio_bytes = await mock_tts.synthesize(
            text=request.text,
            language=request.language,
            voice=request.voice,
            speed=request.speed,
        )
        return Response(
            content=audio_bytes,
            media_type="audio/wav",
            headers={
                "X-ClaimSathi-Provider": "MockSpeech-Demo",
                "X-ClaimSathi-Demo": "true",
            },
        )

    # Live Gnani Timbre TTS
    # Raises HTTPException if credentials invalid, credits exhausted, or service error.
    audio_bytes = await live_tts.synthesize(
        text=request.text,
        language=request.language,
        voice=request.voice,
        speed=request.speed,
    )

    settings = get_settings()
    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={
            "X-ClaimSathi-Provider": f"Gnani-Timbre-{settings.gnani_tts_model}",
            "X-ClaimSathi-Voice": request.voice or settings.gnani_tts_voice,
            "X-ClaimSathi-Demo": "false",
        },
    )

