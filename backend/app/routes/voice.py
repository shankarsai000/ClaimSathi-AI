"""
Voice API routes for ClaimSathi AI (Phase 2).
Provides endpoints for Gnani Prisma STT transcription and Gnani Timbre TTS speech synthesis.
"""

import json
from typing import Optional
from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from ..audio_utils import compute_wav_rms_energy, validate_audio_file
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
from ..providers.conversation import (
    FIELD_ORDER,
    build_claim_fields_state,
    has_meaningful_words,
    process_conversational_turn,
)
from ..providers.speech import (
    GnaniTimbreProvider,
    MockSpeechProvider,
    extract_gnani_audio_tags,
    sanitize_gnani_audio_tags,
)
from ..providers.transcription import (
    GnaniPrismaProvider,
    MockTranscriptionProvider,
    detect_conversation_language,
    extract_claim_fields,
    extract_multimodal_slots,
    generate_assistant_dialogue,
    generate_code_mixed_slot_reply,
    generate_evidence_narration,
    transcribe_via_groq_whisper,
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
    known_motor_slots_json: Optional[str] = Form(None, description="Optional JSON map of Group A motor slots"),
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
        # Live Gnani Prisma STT with automatic Groq Whisper failover on 402/429/5xx
        try:
            result = await live_stt.transcribe(
                audio_bytes=raw_bytes,
                filename=filename,
                content_type=normalized_mime,
                language_code=language_code,
            )
        except HTTPException as stt_exc:
            if stt_exc.status_code in (402, 429, 500, 502, 503, 504):
                whisper_res = await transcribe_via_groq_whisper(
                    audio_bytes=raw_bytes,
                    filename=filename,
                    content_type=normalized_mime,
                    language_code=language_code,
                )
                if whisper_res is not None:
                    result = whisper_res
                else:
                    raise
            else:
                raise

    # Attach detected duration and audio RMS energy to request metadata if available
    if detected_duration is not None:
        result["request_metadata"]["duration_seconds"] = round(detected_duration, 2)
    audio_rms = compute_wav_rms_energy(raw_bytes)
    if audio_rms is not None:
        result["request_metadata"]["audio_rms"] = audio_rms

    known_fields = None
    history = None
    if known_fields_json:
        try:
            parsed_kf = json.loads(known_fields_json)
            if isinstance(parsed_kf, dict):
                known_fields = parsed_kf
        except Exception:
            known_fields = None
    known_motor_slots = None
    if known_motor_slots_json:
        try:
            parsed_ms = json.loads(known_motor_slots_json)
            if isinstance(parsed_ms, dict):
                known_motor_slots = parsed_ms
        except Exception:
            known_motor_slots = None
    if history_json:
        try:
            parsed_h = json.loads(history_json)
            if isinstance(parsed_h, list):
                history = parsed_h
        except Exception:
            history = None

    raw_transcript = (result.get("transcript") or "").strip()
    if not has_meaningful_words(raw_transcript):
        prev_known = {
            k: (known_fields.get(k) or None) if isinstance(known_fields, dict) else None
            for k in FIELD_ORDER
        }
        resolved_lang = result.get("detected_language") or (
            language_code if (language_code and language_code != "indic-auto") else "en-IN"
        )
        preserved_fields, preserved_missing = build_claim_fields_state(prev_known, resolved_lang)
        return VoiceTranscribeResponse(
            transcript="",
            model=result["model"],
            detected_language=resolved_lang,
            is_mock=result["is_mock"],
            request_metadata=result["request_metadata"],
            fields=preserved_fields,
            missing_fields=preserved_missing,
            assistant_dialogue=None,
            assistant_speech_text=None,
            assistant_language=resolved_lang,
            claimed_vehicle_type=None,
            vehicle_registration=prev_known.get("policy_reference"),
            damage_keywords=[],
            incident_description=prev_known.get("damage_description"),
            reasoning_trace=None,
            no_speech_detected=True,
        )

    conv = await process_conversational_turn(
        message=raw_transcript,
        language=result.get("detected_language") or language_code or "indic-auto",
        known_fields=known_fields,
        history=history,
        expected_field=expected_field,
        known_motor_slots=known_motor_slots,
    )

    return VoiceTranscribeResponse(
        transcript=raw_transcript,
        model=result["model"],
        detected_language=conv["assistant_language"],
        is_mock=result["is_mock"],
        request_metadata=result["request_metadata"],
        fields=conv["fields"],
        missing_fields=conv["missing_fields"],
        assistant_dialogue=conv["reply_text"],
        assistant_speech_text=conv.get("assistant_speech_text") or conv["reply_text"],
        assistant_language=conv["assistant_language"],
        claimed_vehicle_type=conv.get("claimed_vehicle_type"),
        vehicle_make_model=conv.get("vehicle_make_model"),
        vehicle_registration=conv.get("vehicle_registration"),
        claimed_registration=conv.get("claimed_registration"),
        motor_slots=conv.get("motor_slots"),
        damage_keywords=conv.get("damage_keywords", []),
        incident_description=conv.get("incident_description"),
        reasoning_trace=conv.get("reasoning_trace"),
        no_speech_detected=conv.get("no_speech_detected", False),
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
        known_motor_slots=request.known_motor_slots,
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
        vehicle_make_model=slots.get("vehicle_make_model"),
        vehicle_registration=slots.get("vehicle_registration"),
        claimed_registration=slots.get("claimed_registration"),
        motor_slots=slots.get("motor_slots"),
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
        reasons=request.reasons,
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
    is_v3 = "v3" in (settings.gnani_tts_model or "").lower()
    applied_tags = extract_gnani_audio_tags(sanitize_gnani_audio_tags(request.text)) if is_v3 else []
    effective_voice = live_tts.resolve_effective_voice(request.voice)
    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={
            "X-ClaimSathi-Provider": f"Gnani-Timbre-{settings.gnani_tts_model}",
            "X-ClaimSathi-Voice": effective_voice,
            "X-ClaimSathi-Emotion-Tags": ",".join(applied_tags) or "none",
            "X-ClaimSathi-Demo": "false",
        },
    )

