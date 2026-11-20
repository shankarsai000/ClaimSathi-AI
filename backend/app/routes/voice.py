"""
Voice API routes for ClaimSathi AI (Phase 2).
Provides endpoints for Gnani Prisma STT transcription and Gnani Timbre TTS speech synthesis.
"""

import json
from typing import Optional
from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from ..audio_utils import validate_audio_file
from ..config import get_settings
from ..models import (
    ConverseTurnRequest,
    ConverseTurnResponse,
    EvidenceNarrationRequest,
    EvidenceNarrationResponse,
    ExtractSlotsRequest,
    ExtractSlotsResponse,
    SpeechSynthesizeRequest,
    VoiceTranscribeResponse,
)
from ..providers.conversation import process_conversational_turn
from ..providers.speech import GnaniTimbreProvider, MockSpeechProvider
from ..providers.transcription import (
    GnaniPrismaProvider,
    MockTranscriptionProvider,
    detect_conversation_language,
    extract_claim_fields,
    extract_multimodal_slots,
    generate_assistant_dialogue,
    generate_code_mixed_slot_reply,
    generate_evidence_narration,
)

router = APIRouter(prefix="/voice", tags=["Voice"])
v1_voice_router = APIRouter(prefix="/v1/voice", tags=["Voice v1"])

live_stt = GnaniPrismaProvider()
mock_stt = MockTranscriptionProvider()

live_tts = GnaniTimbreProvider()
mock_tts = MockSpeechProvider()


@router.post("/transcribe", response_model=VoiceTranscribeResponse)
async def transcribe_audio_file(
    audio_file: UploadFile = File(..., description="Uploaded audio file (.wav, .mp3, .ogg, .flac, .aac, .m4a)"),
    demo: bool = Form(False, description="Explicit demo mode flag"),
    language_code: Optional[str] = Form(None, description="Optional language override (e.g. hi-IN)"),
    known_fields_json: Optional[str] = Form(None, description="Optional JSON map of already-captured fields"),
    history_json: Optional[str] = Form(None, description="Optional JSON array of prior turns"),
    expected_field: Optional[str] = Form(None, description="Optional field currently being answered"),
):
    """
    Transcribe spoken claim audio using Gnani Prisma ASR.
    Enforces a 30-second duration limit and supported Indic audio formats.
    Returns transcript, model info, detected language, and stateful conversational reply.
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
        # Explicit demo mode requested by caller (used by automated tests only)
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

    known_fields = None
    history = None
    if known_fields_json:
        try:
            parsed_kf = json.loads(known_fields_json)
            if isinstance(parsed_kf, dict):
                known_fields = parsed_kf
        except Exception:
            known_fields = None
    if history_json:
        try:
            parsed_h = json.loads(history_json)
            if isinstance(parsed_h, list):
                history = parsed_h
        except Exception:
            history = None

    conv = await process_conversational_turn(
        message=result["transcript"],
        language=result.get("detected_language") or language_code or "indic-auto",
        known_fields=known_fields,
        history=history,
        expected_field=expected_field,
    )

    return VoiceTranscribeResponse(
        transcript=result["transcript"],
        model=result["model"],
        detected_language=conv["assistant_language"],
        is_mock=result["is_mock"],
        request_metadata=result["request_metadata"],
        fields=conv["fields"],
        missing_fields=conv["missing_fields"],
        assistant_dialogue=conv["reply_text"],
        assistant_speech_text=conv["reply_text"],
        assistant_language=conv["assistant_language"],
        claimed_vehicle_type=conv.get("claimed_vehicle_type"),
        vehicle_registration=conv.get("vehicle_registration"),
        damage_keywords=conv.get("damage_keywords", []),
        incident_description=conv.get("incident_description"),
    )


@router.post("/converse", response_model=ConverseTurnResponse)
@v1_voice_router.post("/converse", response_model=ConverseTurnResponse)
async def converse_with_claim_assistant(request: ConverseTurnRequest):
    """
    Stateful multi-turn conversational intake endpoint.
    Remembers already-provided details (`known_fields`) and generates a natural,
    non-repetitive human response asking only for genuinely missing info.
    """
    res = await process_conversational_turn(
        message=request.message,
        language=request.language,
        known_fields=request.known_fields,
        history=request.history,
        expected_field=request.expected_field,
    )
    return ConverseTurnResponse(**res)


@router.post("/extract-slots", response_model=ExtractSlotsResponse)
@v1_voice_router.post("/extract-slots", response_model=ExtractSlotsResponse)
async def extract_voice_slots(request: ExtractSlotsRequest):
    """
    Extract structured vehicle/damage/registration slots from code-mixed Indic text/speech
    and return a concise, empathetic roadside voice reply (<35 words, zero markdown).
    """
    raw_text = request.text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="Text input is required.")

    resolved_lang = detect_conversation_language(raw_text, request.language)
    slots = extract_multimodal_slots(raw_text, language_hint=request.language or resolved_lang)
    fields, missing = extract_claim_fields(raw_text)
    dialogue_info = generate_assistant_dialogue(
        transcript=raw_text,
        fields=fields,
        missing_fields=missing,
        detected_language=resolved_lang,
    )
    concise_reply = generate_code_mixed_slot_reply(
        slots=slots,
        language_hint=request.language if (request.language and request.language != "indic-auto") else slots.get("detected_language"),
    )
    return ExtractSlotsResponse(
        transcript=raw_text,
        claimed_vehicle_type=slots.get("claimed_vehicle_type"),
        vehicle_registration=slots.get("vehicle_registration"),
        damage_keywords=slots.get("damage_keywords", []),
        incident_description=slots.get("incident_description") or raw_text,
        detected_language=slots.get("detected_language") or resolved_lang,
        reply_text=concise_reply,
        fields=fields,
        missing_fields=missing,
        assistant_dialogue=concise_reply,
        assistant_speech_text=concise_reply,
        assistant_language=dialogue_info["language"],
    )


@router.post("/narrate-evidence", response_model=EvidenceNarrationResponse)
@v1_voice_router.post("/narrate-evidence", response_model=EvidenceNarrationResponse)
async def narrate_evidence_verdict(request: EvidenceNarrationRequest):
    """
    Generate natural spoken Indic/code-mixed narration for evidence verification outcomes.
    Concise (<40 words, no markdown/symbols) and clear for TTS audio playback.
    """
    result = generate_evidence_narration(
        decision=request.decision,
        claimed_vehicle_type=request.claimed_vehicle_type,
        detected_vehicle_category=request.detected_vehicle_category,
        vehicle_category_mismatch=request.vehicle_category_mismatch,
        total_estimated_inr=request.total_estimated_inr,
        damages=request.damages,
        language=request.language,
    )
    return EvidenceNarrationResponse(**result)


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

