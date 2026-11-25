"""
Tests for ClaimSathi AI Voice Endpoints (Phase 2).
Uses mocked HTTP responses for external Gnani APIs to ensure no live credits are consumed.
"""

import io
import wave
import pytest
from httpx import AsyncClient, ASGITransport, Response
import httpx
from app.main import app
from app.database import init_db
from app.config import get_settings
from app.audio_utils import generate_demo_wav

transport = ASGITransport(app=app)
_original_post = httpx.AsyncClient.post


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()
    yield


def create_test_wav(duration_seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Generate in-memory WAV bytes with accurate RIFF header."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        num_frames = int(duration_seconds * sample_rate)
        wf.writeframes(b"\x00\x00" * num_frames)
    return buf.getvalue()


@pytest.mark.anyio
async def test_transcribe_prisma_v25_mocked(monkeypatch):
    """Verify Prisma v2.5 STT request parameters and response parsing."""
    settings = get_settings()
    monkeypatch.setattr(settings, "gnani_api_key_id", "test_mock_api_key_123")
    monkeypatch.setattr(settings, "gnani_stt_model", "prisma-v2.5")

    captured_external_requests = []

    async def selective_post(self, url, *args, **kwargs):
        if "api.vachana.ai" in str(url):
            captured_external_requests.append({"url": str(url), "kwargs": kwargs})
            return Response(
                200,
                json={
                    "success": True,
                    "request_id": "req-mock-v25-789",
                    "transcript": "Mera accident Andheri East Mumbai mein hua car ka policy MOT-2024-MH-11223",
                    "model": "prisma-v2.5",
                    "processing_time": 0.35,
                    "end_to_end_latency": 0.45,
                },
            )
        return await _original_post(self, url, *args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient.post", selective_post)

    wav_bytes = create_test_wav(duration_seconds=2.0)
    files = {"audio_file": ("test.wav", wav_bytes, "audio/wav")}
    data = {"demo": "false", "language_code": "hi-IN"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/voice/transcribe", files=files, data=data)

    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["is_mock"] is False
    assert res_data["model"] == "prisma-v2.5"
    assert "MOT-2024-MH-11223" in res_data["transcript"]
    assert res_data["request_metadata"]["request_id"] == "req-mock-v25-789"

    # Verify request payload sent to Gnani
    assert len(captured_external_requests) == 1
    sent_kw = captured_external_requests[0]["kwargs"]
    assert sent_kw["headers"]["X-API-Key-ID"] == "test_mock_api_key_123"
    assert sent_kw["data"]["language_code"] == "hi-IN"
    # Prisma v2.5 mode must NOT send v3 parameters
    assert "writing_mode" not in sent_kw["data"]
    assert "model" not in sent_kw["data"]


@pytest.mark.anyio
async def test_transcribe_prisma_v30_mocked(monkeypatch):
    """Verify Prisma v3.0 STT mode sends model and supports detected language."""
    settings = get_settings()
    monkeypatch.setattr(settings, "gnani_api_key_id", "test_mock_api_key_123")
    monkeypatch.setattr(settings, "gnani_stt_model", "prisma-v3.0")
    monkeypatch.setattr(settings, "gnani_stt_writing_mode", "transcribe")

    captured_external_requests = []

    async def selective_post(self, url, *args, **kwargs):
        if "api.vachana.ai" in str(url):
            captured_external_requests.append({"url": str(url), "kwargs": kwargs})
            return Response(
                200,
                json={
                    "success": True,
                    "request_id": "req-mock-v30-999",
                    "transcript": "Meri gaadi ka accident ho gaya Pune mein",
                    "model": "prisma-v3.0",
                    "detected_language_code": "hi-IN",
                    "processing_time": 0.28,
                    "end_to_end_latency": 0.32,
                },
            )
        return await _original_post(self, url, *args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient.post", selective_post)

    wav_bytes = create_test_wav(duration_seconds=1.5)
    files = {"audio_file": ("test.wav", wav_bytes, "audio/wav")}
    data = {"demo": "false"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/voice/transcribe", files=files, data=data)

    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["model"] == "prisma-v3.0"
    assert res_data["detected_language"] == "hi-IN"

    assert len(captured_external_requests) == 1
    sent_kw = captured_external_requests[0]["kwargs"]
    assert sent_kw["data"]["model"] == "prisma-v3.0"
    assert sent_kw["data"]["writing_mode"] == "transcribe"


@pytest.mark.anyio
async def test_transcribe_enforces_30s_duration_limit():
    """Verify that audio exceeding 30 seconds is rejected with 400."""
    long_wav = create_test_wav(duration_seconds=35.0)
    files = {"audio_file": ("long_audio.wav", long_wav, "audio/wav")}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/voice/transcribe", files=files)

    assert resp.status_code == 400
    assert "30-second" in resp.json()["detail"] or "30" in resp.json()["detail"]


@pytest.mark.anyio
async def test_transcribe_rejects_unsupported_format():
    """Verify unsupported audio formats like .webm return guided 400 error."""
    files = {"audio_file": ("recording.webm", b"G__NOT_REAL_WEBM_DATA", "audio/webm")}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/voice/transcribe", files=files)

    assert resp.status_code == 400
    assert "WebM" in resp.json()["detail"]


@pytest.mark.anyio
async def test_transcribe_handles_401_unauthorized(monkeypatch):
    """Verify 401 from Gnani produces clear credentials error."""
    settings = get_settings()
    monkeypatch.setattr(settings, "gnani_api_key_id", "invalid_key")

    async def selective_post(self, url, *args, **kwargs):
        if "api.vachana.ai" in str(url):
            return Response(401, json={"message": "Invalid API Key"})
        return await _original_post(self, url, *args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient.post", selective_post)

    wav_bytes = create_test_wav(duration_seconds=1.0)
    files = {"audio_file": ("test.wav", wav_bytes, "audio/wav")}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/voice/transcribe", files=files, data={"demo": "false"})

    assert resp.status_code == 401
    assert "GNANI_API_KEY_ID" in resp.json()["detail"]


@pytest.mark.anyio
async def test_transcribe_handles_402_insufficient_credits(monkeypatch):
    """Verify 402 from Gnani produces clear credits error when no Groq fallback is configured."""
    settings = get_settings()
    monkeypatch.setattr(settings, "gnani_api_key_id", "valid_key")
    monkeypatch.setattr(settings, "llm_api_key", None)

    async def selective_post(self, url, *args, **kwargs):
        if "api.vachana.ai" in str(url):
            return Response(402, json={"message": "Out of credits"})
        return await _original_post(self, url, *args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient.post", selective_post)

    wav_bytes = create_test_wav(duration_seconds=1.0)
    files = {"audio_file": ("test.wav", wav_bytes, "audio/wav")}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/voice/transcribe", files=files, data={"demo": "false"})

    assert resp.status_code == 402
    assert "credits" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_transcribe_demo_mode_returns_mock_without_external_call():
    """Verify explicit demo=True returns mock transcript."""
    wav_bytes = create_test_wav(duration_seconds=1.0)
    files = {"audio_file": ("test.wav", wav_bytes, "audio/wav")}
    data = {"demo": "true"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/voice/transcribe", files=files, data=data)

    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["is_mock"] is True
    assert len(res_data["fields"]) == 5


@pytest.mark.anyio
async def test_speak_timbre_tts_mocked(monkeypatch):
    """Verify Timbre TTS sends audio_config and returns audio/wav."""
    settings = get_settings()
    monkeypatch.setattr(settings, "gnani_api_key_id", "test_mock_key")
    monkeypatch.setattr(settings, "gnani_tts_voice", "Nalini")
    monkeypatch.setattr(settings, "gnani_tts_model", "timbre-v2.5")

    synthetic_wav = generate_demo_wav(duration_seconds=0.5)
    captured_external_requests = []

    async def selective_post(self, url, *args, **kwargs):
        if "api.vachana.ai" in str(url):
            captured_external_requests.append({"url": str(url), "kwargs": kwargs})
            return Response(200, content=synthetic_wav, headers={"Content-Type": "audio/wav"})
        return await _original_post(self, url, *args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient.post", selective_post)

    payload = {
        "text": "Aapka claim darj ho gaya hai",
        "language": "hi-IN",
        "voice": "Nalini",
        "speed": 1.0,
        "demo": False,
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/voice/speak", json=payload)

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert resp.content == synthetic_wav

    assert len(captured_external_requests) == 1
    sent_kw = captured_external_requests[0]["kwargs"]
    assert sent_kw["headers"]["X-API-Key-ID"] == "test_mock_key"
    assert sent_kw["json"]["voice"] == "Nalini"
    assert sent_kw["json"]["model"] == "timbre-v2.5"
    assert sent_kw["json"]["audio_config"]["container"] == "wav"
    assert sent_kw["json"]["audio_config"]["encoding"] == "linear_pcm"


@pytest.mark.anyio
async def test_speak_failure_does_not_return_mock(monkeypatch):
    """Verify that when live TTS fails, it raises an error and NEVER returns mock audio."""
    settings = get_settings()
    monkeypatch.setattr(settings, "gnani_api_key_id", "test_mock_key")

    async def selective_post(self, url, *args, **kwargs):
        if "api.vachana.ai" in str(url):
            return Response(500, text="Internal Gnani TTS failure")
        return await _original_post(self, url, *args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient.post", selective_post)

    payload = {
        "text": "Failed test text",
        "demo": False,
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/voice/speak", json=payload)

    assert resp.status_code == 502
    assert "Gnani Speech API returned a server error" in resp.json()["detail"]


@pytest.mark.anyio
async def test_speak_demo_mode_returns_wav():
    """Verify demo mode returns playable WAV without external call."""
    payload = {
        "text": "Demo mode speech",
        "demo": True,
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/voice/speak", json=payload)

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert resp.headers.get("x-claimsathi-demo") == "true"
    assert len(resp.content) > 100


@pytest.mark.anyio
async def test_api_key_not_leaked_in_responses(monkeypatch):
    """Verify secret API key is never exposed in any response body or header."""
    secret_key = "super_secret_vach_key_9999"
    settings = get_settings()
    monkeypatch.setattr(settings, "gnani_api_key_id", secret_key)

    async def selective_post(self, url, *args, **kwargs):
        if "api.vachana.ai" in str(url):
            return Response(401, json={"detail": "Bad auth"})
        return await _original_post(self, url, *args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient.post", selective_post)

    wav_bytes = create_test_wav(duration_seconds=1.0)
    files = {"audio_file": ("test.wav", wav_bytes, "audio/wav")}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/voice/transcribe", files=files, data={"demo": "false"})

    assert secret_key not in resp.text
    for h_name, h_val in resp.headers.items():
        assert secret_key not in h_val


@pytest.mark.anyio
async def test_conversational_turn_remembers_bike_number_and_avoids_reasking():
    """
    Verify stateful multi-turn conversation remembers already-provided slots
    (such as bike registration & date) and never re-asks or emits hardcoded demo plates.
    """
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Turn 1: User gives date, vehicle type, and space-separated KL plate
        t1_resp = await client.post(
            "/api/v1/voice/converse",
            json={
                "message": "An accident happened on 18th November, my bike number is KL 07 AB 1234",
                "language": "en-IN",
                "known_fields": {},
                "history": [],
            },
        )
        assert t1_resp.status_code == 200
        t1 = t1_resp.json()

        t1_fields = {f["name"]: f["value"] for f in t1["fields"]}
        assert t1_fields["policy_reference"] == "KL-07-AB-1234"
        assert t1_fields["vehicle_type"] and "bike" in t1_fields["vehicle_type"].lower()
        assert t1["claimed_vehicle_type"] == "two_wheeler"
        assert "18" in (t1_fields["incident_date"] or "") and "November" in (t1_fields["incident_date"] or "")
        assert "policy_reference" not in t1["missing_fields"]
        assert "vehicle_type" not in t1["missing_fields"]
        assert "incident_date" not in t1["missing_fields"]
        assert t1["incident_description"] == t1_fields["damage_description"]
        assert t1["is_complete"] is False

        # Must not re-ask for bike/registration number or emit hardcoded demo plates
        reply1_lower = t1["reply_text"].lower()
        assert "registration number" not in reply1_lower or "kl-07-ab-1234" in reply1_lower
        for banned in ("ka-17-ea-4590", "ts-09-ea-4590", "mot-2024-ts-98765", "ka-01-mj-2026"):
            assert banned not in reply1_lower

        # Turn 2: User provides remaining location and damage
        t2_resp = await client.post(
            "/api/v1/voice/converse",
            json={
                "message": "near Indiranagar, headlamp broke",
                "language": "en-IN",
                "known_fields": t1_fields,
                "history": [
                    {"sender": "user", "text": "An accident happened on 18th November, my bike number is KL 07 AB 1234"},
                    {"sender": "assistant", "text": t1["reply_text"]},
                ],
                "expected_field": t1["missing_fields"][0] if t1["missing_fields"] else None,
            },
        )
        assert t2_resp.status_code == 200
        t2 = t2_resp.json()

        t2_fields = {f["name"]: f["value"] for f in t2["fields"]}
        assert t2_fields["policy_reference"] == "KL-07-AB-1234"
        assert t2_fields["vehicle_type"] and "bike" in t2_fields["vehicle_type"].lower()
        assert "18" in (t2_fields["incident_date"] or "")
        assert t2_fields["incident_location"] and "indiranagar" in t2_fields["incident_location"].lower()
        assert t2_fields["damage_description"] and (
            "headlight" in t2_fields["damage_description"].lower()
            or "headlamp" in t2_fields["damage_description"].lower()
        )
        assert t2["missing_fields"] == []
        assert t2["is_complete"] is True
        assert t2["vehicle_registration"] == "KL-07-AB-1234"
        assert t2["claimed_vehicle_type"] == "two_wheeler"


@pytest.mark.anyio
async def test_extract_text_respects_known_fields_state():
    """Verify /api/claims/extract-text preserves known_fields across turns."""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/claims/extract-text",
            json={
                "text": "Today morning near Kochi metro pillar, front fender cracked",
                "language": "en-IN",
                "known_fields": {
                    "policy_reference": "KL-01-CD-9876",
                    "vehicle_type": "Two-Wheeler (Bike)",
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        fields_map = {f["name"]: f["value"] for f in data["fields"]}
        assert fields_map["policy_reference"] == "KL-01-CD-9876"
        assert fields_map["vehicle_type"] == "Two-Wheeler (Bike)"
        assert fields_map["incident_date"] is not None
        assert fields_map["incident_location"] and "kochi" in fields_map["incident_location"].lower()
        assert fields_map["damage_description"] is not None
        assert data["missing_fields"] == []


@pytest.mark.anyio
async def test_cognitive_emotional_and_causal_plausibility_reasoning():
    """
    Verify 4-stage human cognitive & emotional reasoning:
    1. High-impact collision triggers safety inquiry, empathetic tone, and slower speech_rate.
    2. User confirming safety + rear-end hit with front-only critical damage triggers
       relief reaction, non-drivable/towing assessment, and physical plausibility inquiry.
    """
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Turn 1: High-impact highway collision from behind
        t1_resp = await client.post(
            "/api/v1/voice/converse",
            json={
                "message": "A truck hit my bike on the highway from behind on 18th November, my bike number is KL 07 AB 1234",
                "language": "en-IN",
                "known_fields": {},
                "history": [],
            },
        )
        assert t1_resp.status_code == 200
        t1 = t1_resp.json()
        trace1 = t1["reasoning_trace"]
        assert trace1 is not None
        assert trace1["detected_emotion"] == "distressed_high_impact"
        assert trace1["safety_check_status"] == "urgent_safety_inquiry"
        assert trace1["inferred_cause"] == "Rear-end impact"
        assert trace1["speech_rate"] < 1.0
        assert any(w in t1["reply_text"].lower() for w in ("safe", "okay", "hurt", "medical"))

        # Turn 2: User confirms they are safe, gives location & front-only critical damage
        t1_fields = {f["name"]: f["value"] for f in t1["fields"]}
        t2_resp = await client.post(
            "/api/v1/voice/converse",
            json={
                "message": "I am safe, happened near Indiranagar, front headlamp and front fork broke",
                "language": "en-IN",
                "known_fields": t1_fields,
                "history": [
                    {
                        "sender": "user",
                        "text": "A truck hit my bike on the highway from behind on 18th November, my bike number is KL 07 AB 1234",
                    },
                    {"sender": "assistant", "text": t1["reply_text"]},
                ],
            },
        )
        assert t2_resp.status_code == 200
        t2 = t2_resp.json()
        trace2 = t2["reasoning_trace"]
        assert trace2 is not None
        assert trace2["detected_emotion"] == "relieved_safe"
        assert trace2["safety_check_status"] == "confirmed_safe"
        assert trace2["drivability_assessment"] == "non_drivable_towing_recommended"
        assert "Rear impact reported with front-end damage" in trace2["plausibility_note"]
        assert "push" in t2["reply_text"].lower() or "forward" in t2["reply_text"].lower()
        assert "<" not in t2["reply_text"]
        assert "<exhales>" in t2["assistant_speech_text"] or "<pauses>" in t2["assistant_speech_text"]
        assert trace2["applied_gnani_tags"]
        assert t2["is_complete"] is True


@pytest.mark.anyio
async def test_transcribe_empty_silence_does_not_trigger_accident_script(monkeypatch):
    """Layer 0 silence gate: empty Gnani STT transcript must not fabricate an accident script."""
    settings = get_settings()
    monkeypatch.setattr(settings, "gnani_api_key_id", "test_mock_api_key_123")
    monkeypatch.setattr(settings, "gnani_stt_model", "prisma-v3.0")

    async def selective_post(self, url, *args, **kwargs):
        if "api.vachana.ai" in str(url):
            return Response(
                200,
                json={
                    "success": True,
                    "request_id": "req-silence-001",
                    "transcript": "",
                    "model": "prisma-v3.0",
                },
            )
        return await _original_post(self, url, *args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient.post", selective_post)

    wav_bytes = create_test_wav(duration_seconds=1.5)
    files = {"audio_file": ("silence.wav", wav_bytes, "audio/wav")}
    data = {"demo": "false", "language_code": "indic-auto"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/voice/transcribe", files=files, data=data)

    assert resp.status_code == 200
    body = resp.json()
    assert body["no_speech_detected"] is True
    assert body["transcript"] == ""
    assert body["assistant_dialogue"] is None
    assert body["assistant_speech_text"] is None
    assert body["reasoning_trace"] is None
    assert body["request_metadata"]["audio_rms"] == 0.0


@pytest.mark.anyio
async def test_converse_greeting_does_not_assume_accident():
    """Greeting or mic check must get a warm human greeting without assuming an accident."""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/voice/converse",
            json={
                "message": "Hello, can you hear me?",
                "language": "en-IN",
                "known_fields": {},
                "history": [],
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["no_speech_detected"] is False
    assert body["reasoning_trace"]["detected_intent"] == "greeting"
    reply_low = body["reply_text"].lower()
    assert "sorry" not in reply_low
    assert "accident" not in reply_low
    assert "<" not in body["reply_text"]


@pytest.mark.anyio
async def test_hindi_greeting_does_not_fill_damage_description():
    """Hindi greeting 'हलो।' must stay a greeting and NEVER leak into damage_description or incident_description."""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/voice/converse",
            json={
                "message": "हलो।",
                "language": "indic-auto",
                "known_fields": {},
                "history": [],
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    fields_map = {f["name"]: f["value"] for f in body["fields"]}
    assert body["reasoning_trace"]["detected_intent"] == "greeting"
    assert fields_map["damage_description"] is None
    assert body["incident_description"] is None
    assert len(body["missing_fields"]) == 5


@pytest.mark.anyio
async def test_converse_gemini_approach_a_with_gnani_tag_sanitization(monkeypatch):
    """Approach A: Google Gemini brain uses x-goog-api-key header, returns clean reply & valid Gnani tags."""
    settings = get_settings()
    secret_gemini_key = "AIzaSyMockGeminiSecretKeyForTest1234"
    monkeypatch.setattr(settings, "llm_api_url", None)
    monkeypatch.setattr(settings, "llm_api_key", None)
    monkeypatch.setattr(settings, "gemini_api_key", secret_gemini_key)
    monkeypatch.setattr(settings, "gemini_model", "gemini-2.5-flash")

    captured_gemini_reqs = []

    async def selective_post(self, url, *args, **kwargs):
        if "generativelanguage.googleapis.com" in str(url):
            captured_gemini_reqs.append({"url": str(url), "kwargs": kwargs})
            llm_json = {
                "intent": "claim_intake",
                "detected_emotion": "distressed_high_impact",
                "empathy_cue": "Checking personal wellbeing after highway skid",
                "safety_check_status": "urgent_safety_inquiry",
                "inferred_cause": "Wet road skid",
                "drivability_assessment": "caution_check_before_riding",
                "plausibility_note": "Consistent wet-road bike skid impact",
                "thought_process": "User sounded shaken about skidding on wet tarmac, so I should ask if they are unhurt first.",
                "extracted_fields": {
                    "policy_reference": "KL 07 AB 1234",
                    "vehicle_type": "bike",
                    "incident_location": "MG Road, Kochi",
                    "incident_date": "18th November",
                    "damage_description": "Front mudguard cracked",
                },
                "reply_text": "Oh no, skidding on a wet road is scary — are you completely unhurt right now?",
                "speech_text": "<sigh> Oh no, <invalid_emotion> skidding on a wet road is scary <pauses> <slow> are you completely unhurt right now?",
                "speech_rate": 0.94,
                "speech_pitch": 0.97,
            }
            return Response(
                200,
                json={
                    "candidates": [
                        {"content": {"parts": [{"text": __import__("json").dumps(llm_json)}]}}
                    ]
                },
            )
        return await _original_post(self, url, *args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient.post", selective_post)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/voice/converse",
            json={
                "message": "My bike KL 07 AB 1234 skidded near MG Road Kochi on 18th November, front mudguard cracked",
                "language": "en-IN",
                "known_fields": {},
                "history": [],
            },
        )

    assert resp.status_code == 200
    assert len(captured_gemini_reqs) == 1
    req = captured_gemini_reqs[0]
    assert secret_gemini_key not in req["url"]
    assert req["kwargs"]["headers"]["x-goog-api-key"] == secret_gemini_key

    body = resp.json()
    assert secret_gemini_key not in resp.text
    assert body["reasoning_trace"]["llm_provider"] == "gemini:gemini-2.5-flash"
    assert "<" not in body["reply_text"]
    assert "<sigh>" in body["assistant_speech_text"]
    assert "<pauses>" in body["assistant_speech_text"]
    assert "<slow>" in body["assistant_speech_text"]
    assert "<invalid_emotion>" not in body["assistant_speech_text"]
    assert body["vehicle_registration"] == "KL-07-AB-1234"
    assert body["claimed_vehicle_type"] == "two_wheeler"
    assert body["is_complete"] is True


@pytest.mark.anyio
async def test_converse_ollama_approach_b_fallback(monkeypatch):
    """Approach B: Local Ollama endpoint takes over seamlessly when Groq and Gemini are unconfigured."""
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_api_url", None)
    monkeypatch.setattr(settings, "llm_api_key", None)
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "ollama_enabled", True)
    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:1.5b")
    monkeypatch.setattr(settings, "ollama_api_url", "http://localhost:11434/api/chat")

    async def selective_post(self, url, *args, **kwargs):
        if "11434/api/chat" in str(url):
            ollama_json = {
                "intent": "question",
                "detected_emotion": "calm_informative",
                "empathy_cue": "Patiently answering customer question",
                "safety_check_status": "routine",
                "thought_process": "Customer asked how long claims take; answering honestly before continuing.",
                "extracted_fields": {},
                "reply_text": "Most clear claims finish initial verification in just a couple of minutes once photos are uploaded.",
                "speech_text": "Most clear claims finish initial verification in just a couple of minutes <pauses> once photos are uploaded.",
                "speech_rate": 1.0,
                "speech_pitch": 1.0,
            }
            return Response(
                200,
                json={"message": {"role": "assistant", "content": __import__("json").dumps(ollama_json)}},
            )
        return await _original_post(self, url, *args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient.post", selective_post)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/voice/converse",
            json={
                "message": "How long does it usually take to process this?",
                "language": "en-IN",
                "known_fields": {},
                "history": [],
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["reasoning_trace"]["llm_provider"] == "ollama:qwen2.5:1.5b"
    assert "couple of minutes" in body["reply_text"]
    assert "<pauses>" in body["assistant_speech_text"]


@pytest.mark.anyio
async def test_speak_timbre_v3_preserves_official_emotion_tags_and_remaps_legacy_voice(monkeypatch):
    """Timbre v3.0 preserves valid Gnani audio tags, strips bogus tags, remaps Nalini -> Shivani, and blocks tag-only strings."""
    settings = get_settings()
    monkeypatch.setattr(settings, "gnani_api_key_id", "test_mock_key")
    monkeypatch.setattr(settings, "gnani_tts_model", "timbre-v3.0")
    monkeypatch.setattr(settings, "gnani_tts_voice", "Shivani")

    synthetic_wav = generate_demo_wav(duration_seconds=0.5)
    captured = []

    async def selective_post(self, url, *args, **kwargs):
        if "api.vachana.ai" in str(url):
            captured.append(kwargs)
            return Response(200, content=synthetic_wav, headers={"Content-Type": "audio/wav"})
        return await _original_post(self, url, *args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient.post", selective_post)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ok_resp = await client.post(
            "/api/voice/speak",
            json={
                "text": "<sigh> Are you okay? <pauses> <bogus_tag> Take your time.",
                "language": "en-IN",
                "voice": "Nalini",
                "speed": 0.94,
                "demo": False,
            },
        )
        tag_only_resp = await client.post(
            "/api/voice/speak",
            json={
                "text": "<sigh> <pauses>",
                "language": "en-IN",
                "voice": "Shivani",
                "demo": False,
            },
        )

    assert ok_resp.status_code == 200
    assert ok_resp.headers["x-claimsathi-voice"] == "Shivani"
    assert ok_resp.headers["x-claimsathi-emotion-tags"] == "<sigh>,<pauses>"
    assert len(captured) == 1
    sent_json = captured[0]["json"]
    assert sent_json["model"] == "timbre-v3.0"
    assert sent_json["voice"] == "Shivani"
    assert "<sigh>" in sent_json["text"]
    assert "<pauses>" in sent_json["text"]
    assert "<bogus_tag>" not in sent_json["text"]

    assert tag_only_resp.status_code == 400
    assert "speakable words" in tag_only_resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_converse_groq_primary_and_gemini_fallback(monkeypatch):
    """Groq runs as primary LLM when configured, and falls back to Gemini seamlessly on HTTP 429."""
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_api_url", "https://api.groq.com/openai/v1/chat/completions")
    monkeypatch.setattr(settings, "llm_api_key", "gsk_mock_groq_secret_key_for_test")
    monkeypatch.setattr(settings, "llm_model", "qwen/qwen3.8-27b")
    monkeypatch.setattr(settings, "gemini_api_key", "AIzaSyMockGeminiFallbackKey")
    monkeypatch.setattr(settings, "gemini_model", "gemini-flash-lite-latest")

    groq_should_fail = {"flag": False}

    async def selective_post(self, url, *args, **kwargs):
        u = str(url)
        if "api.groq.com" in u:
            if groq_should_fail["flag"]:
                return Response(429, json={"error": {"message": "rate_limit"}})
            groq_json = {
                "intent": "claim_intake",
                "detected_emotion": "anxious_roadside",
                "empathy_cue": "Checking safety first",
                "safety_check_status": "urgent_safety_inquiry",
                "thought_process": "User skidded on Activa; ask if safe first.",
                "extracted_fields": {
                    "policy_reference": "KA-01-MJ-4412",
                    "vehicle_type": "Two-Wheeler",
                    "incident_location": "Indiranagar",
                    "incident_date": "Yesterday Evening",
                    "damage_description": "Front mudguard broken",
                },
                "reply_text": "I hope you are completely safe — I have noted KA-01-MJ-4412 and Indiranagar.",
                "speech_text": "<slow> I hope you are completely safe <pauses> I have noted KA-01-MJ-4412 and Indiranagar.",
                "speech_rate": 0.96,
                "speech_pitch": 1.0,
            }
            return Response(
                200,
                json={"choices": [{"message": {"content": __import__("json").dumps(groq_json)}}]},
            )
        if "generativelanguage.googleapis.com" in u:
            gem_json = {
                "intent": "claim_intake",
                "detected_emotion": "calm_informative",
                "safety_check_status": "routine",
                "thought_process": "Gemini fallback response.",
                "extracted_fields": {},
                "reply_text": "Gemini fallback took over cleanly.",
                "speech_text": "Gemini fallback took over cleanly.",
                "speech_rate": 1.0,
                "speech_pitch": 1.0,
            }
            return Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": __import__("json").dumps(gem_json)}]}}]},
            )
        return await _original_post(self, url, *args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient.post", selective_post)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post(
            "/api/v1/voice/converse",
            json={"message": "My Activa KA 01 MJ 4412 skidded near Indiranagar yesterday evening", "language": "en-IN"},
        )
        assert r1.status_code == 200
        assert r1.json()["reasoning_trace"]["llm_provider"] == "groq:qwen/qwen3.8-27b"

        groq_should_fail["flag"] = True
        r2 = await client.post(
            "/api/v1/voice/converse",
            json={"message": "My Activa KA 01 MJ 4412 skidded near Indiranagar yesterday evening", "language": "en-IN"},
        )
        assert r2.status_code == 200
        assert r2.json()["reasoning_trace"]["llm_provider"] == "gemini:gemini-flash-lite-latest"


@pytest.mark.anyio
async def test_transcribe_falls_back_to_groq_whisper_on_gnani_402_and_dravidian_routes_gemini_first(monkeypatch):
    """
    1. When Gnani Prisma STT returns 402 and a gsk_ Groq key is set, /api/voice/transcribe
       automatically fails over to Groq whisper-large-v3-turbo.
    2. Dravidian language codes (e.g. kn-IN) prioritize Gemini before Groq in _run_reasoning_llm.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "gnani_api_key_id", "valid_gnani_key")
    monkeypatch.setattr(settings, "llm_api_url", "https://api.groq.com/openai/v1/chat/completions")
    monkeypatch.setattr(settings, "llm_api_key", "gsk_mock_groq_secret_key_for_test")
    monkeypatch.setattr(settings, "llm_model", "qwen/qwen3.8-27b")
    monkeypatch.setattr(settings, "gemini_api_key", "AIzaSyMockGeminiKey")
    monkeypatch.setattr(settings, "gemini_model", "gemini-flash-lite-latest")

    async def selective_post(self, url, *args, **kwargs):
        u = str(url)
        if "api.vachana.ai" in u:
            return Response(402, json={"message": "Out of credits"})
        if "audio/transcriptions" in u:
            return Response(
                200,
                json={"text": "Hello, can you hear me?", "duration": 1.2},
            )
        if "generativelanguage.googleapis.com" in u:
            gem_json = {
                "intent": "claim_intake",
                "detected_emotion": "anxious_roadside",
                "safety_check_status": "urgent_safety_inquiry",
                "thought_process": "Kanglish truck collision — Gemini prioritized for kn-IN.",
                "extracted_fields": {},
                "reply_text": "Whitefield hattira truck dikki keli ghabari aayitu, neevu safe iddira?",
                "speech_text": "<sigh> Whitefield hattira truck dikki keli ghabari aayitu <pauses> neevu safe iddira?",
                "speech_rate": 0.95,
                "speech_pitch": 1.0,
            }
            return Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": __import__("json").dumps(gem_json)}]}}]},
            )
        if "api.groq.com/openai/v1/chat/completions" in u:
            groq_json = {
                "intent": "greeting",
                "detected_emotion": "warm_friendly",
                "safety_check_status": "routine",
                "thought_process": "Greeting reply from Groq.",
                "extracted_fields": {},
                "reply_text": "Hello! Yes, I can hear you clearly.",
                "speech_text": "<excited> Hello! Yes, I can hear you clearly.",
                "speech_rate": 1.0,
                "speech_pitch": 1.0,
            }
            return Response(
                200,
                json={"choices": [{"message": {"content": __import__("json").dumps(groq_json)}}]},
            )
        return await _original_post(self, url, *args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient.post", selective_post)

    wav_bytes = create_test_wav(duration_seconds=1.2)
    files = {"audio_file": ("test.wav", wav_bytes, "audio/wav")}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        stt_resp = await client.post("/api/voice/transcribe", files=files, data={"demo": "false", "language_code": "en-IN"})
        assert stt_resp.status_code == 200
        stt_data = stt_resp.json()
        assert stt_data["model"] == "groq:whisper-large-v3-turbo"
        assert stt_data["transcript"] == "Hello, can you hear me?"
        assert stt_data["reasoning_trace"]["llm_provider"] == "groq:qwen/qwen3.8-27b"

        kn_resp = await client.post(
            "/api/v1/voice/converse",
            json={"message": "Whitefield road nalli truck dikki hodeyitu", "language": "kn-IN"},
        )
        assert kn_resp.status_code == 200
        assert kn_resp.json()["reasoning_trace"]["llm_provider"] == "gemini:gemini-flash-lite-latest"


@pytest.mark.anyio
async def test_telugu_bike_with_bandi_and_bumper_extracts_bike_and_never_leaks_json(monkeypatch):
    """
    1. User says both 'నా బండి' (my vehicle) and 'నా బైక్' (my bike) in Telugu:
       deterministic + conversational turn MUST extract 'bike' (never 'car'), extract
       phonetic plate KA-34-E-19, and set claimed_vehicle_type == 'two_wheeler'.
    2. Generic ambiguous 'నా బండి' with no car/bike word stays None (asks car vs bike).
    3. Truncated / raw JSON returned by an LLM MUST NEVER leak into reply_text or speech_text.
    """
    from app.providers.transcription import extract_claim_fields

    telugu_utterance = (
        "హాయ్, నమస్తే నిన్న ధవళగిరిలో నేను పోతున్నప్పుడు నా బండి యాక్సిడెంట్ అయ్యింది. "
        "నా బైక్ నెంబర్. కేఏ త్రీ ఫోర్ ఈ వన్ నేన్ మరియు నా బండి హెడ్ లైట్ మరియు ఫ్రంట్ బంపర్ రెండు డ్యామేజ్ అయ్యాయి."
    )
    fields, _ = extract_claim_fields(telugu_utterance)
    fmap = {f.name: f.value for f in fields}
    assert fmap["vehicle_type"] == "bike"
    assert fmap["policy_reference"] == "KA-34-E-19"

    ambig_fields, _ = extract_claim_fields("నిన్న నా బండి యాక్సిడెంట్ అయ్యింది")
    ambig_map = {f.name: f.value for f in ambig_fields}
    assert ambig_map["vehicle_type"] is None

    # Simulate truncated raw JSON from Groq / custom LLM and unreachable Gemini -> must fall back cleanly, NEVER leak JSON!
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_api_url", "https://api.groq.com/openai/v1/chat/completions")
    monkeypatch.setattr(settings, "llm_api_key", "gsk_mock_key")
    monkeypatch.setattr(settings, "gemini_api_key", None)

    async def selective_post(self, url, *args, **kwargs):
        if "api.groq.com" in str(url):
            return Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": '{"intent": "claim_intake", "thought_process": "Internal secret brain note that got cut off'
                            }
                        }
                    ]
                },
            )
        return await _original_post(self, url, *args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient.post", selective_post)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/voice/converse",
            json={"message": telugu_utterance, "language": "te-IN", "known_fields": {}, "history": []},
        )
    assert resp.status_code == 200
    body = resp.json()
    res_map = {f["name"]: f["value"] for f in body["fields"]}
    assert res_map["vehicle_type"] == "bike"
    assert res_map["policy_reference"] == "KA-34-E-19"
    assert body["claimed_vehicle_type"] == "two_wheeler"
    assert "{" not in body["reply_text"]
    assert "thought_process" not in body["reply_text"]
    assert "{" not in body["assistant_speech_text"]


@pytest.mark.anyio
async def test_multilingual_and_mixed_language_accuracy_across_indian_languages():
    """
    Verify accurate phonetic policy/plate extraction, un-guessed vehicle_type,
    attached Indic locatives, and zero substring false positives across
    Hindi, Hinglish, Kannada, Tamil, Marathi, Malayalam, and English.
    """
    from app.providers.transcription import extract_claim_fields
    from app.providers.conversation import _is_pure_greeting_or_mic_check, _sanitize_llm_extracted_fields

    # 1. Hindi (Devanagari phonetic plate + location + yesterday evening + headlight)
    hi_fields, _ = extract_claim_fields(
        "मेरी बाइक नंबर डी एल जीरो वन ए बी चार पांच छह सात का कल शाम नोएडा में एक्सीडेंट हुआ, हेडलाइट टूट गई"
    )
    hi_map = {f.name: f.value for f in hi_fields}
    assert hi_map["vehicle_type"] == "bike"
    assert hi_map["policy_reference"] == "DL-01-AB-4567"
    assert hi_map["incident_location"] == "Noida"
    assert hi_map["incident_date"] == "Yesterday Evening"
    assert hi_map["damage_description"] and "headlight" in hi_map["damage_description"].lower()

    # 2. Hinglish ('double four' digit expansion + mixed terms)
    hg_fields, _ = extract_claim_fields(
        "Meri bike number KA 01 MJ double four one two ka kal shaam Indiranagar mein accident hua, front bumper dent ho gaya"
    )
    hg_map = {f.name: f.value for f in hg_fields}
    assert hg_map["vehicle_type"] == "bike"
    assert hg_map["policy_reference"] == "KA-01-MJ-4412"
    assert hg_map["incident_location"] and "indiranagar" in hg_map["incident_location"].lower()
    assert hg_map["incident_date"] == "Yesterday Evening"
    assert hg_map["damage_description"] and "bumper" in hg_map["damage_description"].lower()

    # 3. Kannada (phonetic plate + attached location + yesterday evening + headlight)
    kn_fields, _ = extract_claim_fields(
        "ನನ್ನ ಬೈಕ್ ನಂಬರ್ ಕೆ ಎ ಥರ್ಟೀ ಫೋರ್ ಟು ಟ್ವೆಂಟಿ ತ್ರೀ ನಿನ್ನೆ ಸಂಜೆ ದಾವಣಗೆರೆಯಲ್ಲಿ ಅಪಘಾತ ಆಯಿತು, ಹೆಡ್‌ಲೈಟ್ ಒಡೆದಿದೆ"
    )
    kn_map = {f.name: f.value for f in kn_fields}
    assert kn_map["vehicle_type"] == "bike"
    assert kn_map["policy_reference"] == "KA-34-223"
    assert kn_map["incident_location"] and "davanagere" in kn_map["incident_location"].lower()
    assert kn_map["incident_date"] == "Yesterday Evening"
    assert kn_map["damage_description"] and "headlight" in kn_map["damage_description"].lower()

    # 4. Tamil (phonetic plate + attached locative + yesterday evening + headlight)
    ta_fields, _ = extract_claim_fields(
        "என் பைக் நம்பர் டி என் ஜீரோ ஒன் ஏ பி நைன் எய்ட் செவன் சிக்ஸ் நேற்று மாலை சென்னையில் விபத்து, ஹெட்லைட் உடைந்தது"
    )
    ta_map = {f.name: f.value for f in ta_fields}
    assert ta_map["vehicle_type"] == "bike"
    assert ta_map["policy_reference"] == "TN-01-AB-9876"
    assert ta_map["incident_location"] and "chennai" in ta_map["incident_location"].lower()
    assert ta_map["incident_date"] == "Yesterday Evening"
    assert ta_map["damage_description"] and "headlight" in ta_map["damage_description"].lower()

    # 5. Marathi (Devanagari phonetic state + digits + attached locative + bumper)
    mr_fields, _ = extract_claim_fields(
        "माझी बाईक नंबर एम एच 12 ए बी 3456 काल संध्याकाळी पुण्यात अपघात झाला, बंपर तुटले"
    )
    mr_map = {f.name: f.value for f in mr_fields}
    assert mr_map["vehicle_type"] == "bike"
    assert mr_map["policy_reference"] == "MH-12-AB-3456"
    assert mr_map["incident_location"] and "pune" in mr_map["incident_location"].lower()
    assert mr_map["incident_date"] == "Yesterday Evening"
    assert mr_map["damage_description"] and "bumper" in mr_map["damage_description"].lower()

    # 6. Malayalam (bike + yesterday + headlight)
    ml_fields, _ = extract_claim_fields(
        "എന്റെ ബൈക്ക് ഇന്നലെ കൊച്ചിയിൽ അപകടം ഉണ്ടായി, ഹെഡ്ലൈറ്റ് പൊട്ടി"
    )
    ml_map = {f.name: f.value for f in ml_fields}
    assert ml_map["vehicle_type"] == "bike"
    assert ml_map["incident_location"] and "kochi" in ml_map["incident_location"].lower()
    assert ml_map["incident_date"] == "Yesterday"
    assert ml_map["damage_description"] and "headlight" in ml_map["damage_description"].lower()

    # 7. Zero substring false positives ('scared' != 'car', 'audio' != 'dio', 'automatically' != 'auto', 'busy' != 'bus', 'Kalyan' != 'kal')
    fp_fields, _ = extract_claim_fields(
        "I am scared near Kalyan Nagar, audio stopped and road was busy automatically"
    )
    fp_map = {f.name: f.value for f in fp_fields}
    assert fp_map["vehicle_type"] is None
    assert fp_map["incident_date"] is None

    # 8. Zero hardcoded defaults for generic gaadi/bandi/vandi or unmentioned damage
    for utt in ("Meri gaadi ka accident hua", "నా బండి యాక్సిడెంట్ అయింది", "என் வண்டி விபத்து", "I am confused whether it is a bike or car"):
        g_fields, _ = extract_claim_fields(utt)
        g_map = {f.name: f.value for f in g_fields}
        assert g_map["vehicle_type"] is None, f"Unexpected vehicle_type for {utt}: {g_map['vehicle_type']}"
        assert g_map["damage_description"] is None, f"Unexpected damage_description for {utt}: {g_map['damage_description']}"

    # 9. Multilingual greetings & LLM sanitizer guards
    for greet in ("வணக்கம்", "नमस्कार", "നമസ്കാരം", "হ্যালো", "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ", "hello vinipistunda"):
        assert _is_pure_greeting_or_mic_check(greet) is True

    sanitized = _sanitize_llm_extracted_fields({
        "vehicle_type": "bandi",
        "damage_description": "Vehicle accident damage reported",
        "incident_location": "Chennai",
    })
    assert "vehicle_type" not in sanitized
    assert "damage_description" not in sanitized
    assert sanitized["incident_location"] == "Chennai"
    assert _sanitize_llm_extracted_fields({"vehicle_type": "బైక్"})["vehicle_type"] == "bike"
    assert _sanitize_llm_extracted_fields({"vehicle_type": "கார்"})["vehicle_type"] == "car"


@pytest.mark.anyio
async def test_auto_extracts_vehicle_make_model_in_step1_conversation():
    """
    Verify vehicle Make/Model is automatically extracted from Step 1 utterances
    (e.g. 'Pulsar 220' -> 'Bajaj Pulsar 220F', 'Swift' -> 'Maruti Suzuki Swift')
    without substring false positives on 'audio', and kept out of user chat text.
    """
    from app.evidence.cost_estimator import extract_vehicle_make_model

    assert extract_vehicle_make_model("My Pulsar 220 bike met with an accident") == "Bajaj Pulsar 220F"
    assert extract_vehicle_make_model("My Swift car bumper got dented") == "Maruti Suzuki Swift"
    assert extract_vehicle_make_model("The audio stopped automatically") is None

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/voice/converse",
            json={
                "message": "Yesterday my Pulsar 220 bike KA 01 MJ 4412 met with an accident near Indiranagar, headlight broke",
                "language": "en-IN",
                "known_fields": {},
                "history": [],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["vehicle_make_model"] == "Bajaj Pulsar 220F"
        assert body["claimed_vehicle_type"] == "two_wheeler"


@pytest.mark.anyio
async def test_first_accident_turn_expresses_empathy_safety_reassurance_and_prosody(monkeypatch):
    """
    When a user first reports an accident (even right after a greeting turn):
    1. Safety concern & warm reassurance lead before missing-field collection.
    2. Captures mentioned slots (bike, damage) without fabricating unmentioned slots.
    3. Applies expressive Gnani Timbre v3.0 prosody tags and softened speech_rate (< 1.0)
       strictly in assistant_speech_text while keeping reply_text free of raw tags or JSON.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_api_url", None)
    monkeypatch.setattr(settings, "llm_api_key", None)
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "ollama_enabled", False)

    history_after_greeting = [
        {"sender": "user", "text": "Hello"},
        {"sender": "assistant", "text": "Hey there! Yes, I can hear you loud and clear. How can I help you today?"},
    ]

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/voice/converse",
            json={
                "message": "My bike was suddenly in an accident and got some damage",
                "language": "en-IN",
                "known_fields": {},
                "history": history_after_greeting,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        fmap = {f["name"]: f["value"] for f in data["fields"]}
        assert fmap["vehicle_type"] == "bike"
        assert "policy_reference" in data["missing_fields"]
        assert "incident_location" in data["missing_fields"]
        assert "incident_date" in data["missing_fields"]

        rt_low = data["reply_text"].lower()
        assert any(w in rt_low for w in ("sorry", "safe", "okay", "worry", "stress"))
        assert "<" not in data["reply_text"] and "{" not in data["reply_text"]
        assert "<slow>" in data["assistant_speech_text"] or "<sigh>" in data["assistant_speech_text"]
        assert "<pauses>" in data["assistant_speech_text"]
        assert data["reasoning_trace"]["speech_rate"] < 1.0

        # Now verify automatic prosody enrichment when an LLM returns untagged speech_text
        monkeypatch.setattr(settings, "llm_api_url", "https://api.groq.com/openai/v1/chat/completions")
        monkeypatch.setattr(settings, "llm_api_key", "gsk_mock_empathy_key")

        async def mock_groq_untagged(self, url, *args, **kwargs):
            if "api.groq.com" in str(url):
                payload = {
                    "extracted_fields": {"vehicle_type": "bike", "damage_description": "Minor accident damage"},
                    "reply_text": "I am so sorry to hear that. Are you safe right now? Don't worry, could you share your bike number when ready?",
                    "speech_text": "I am so sorry to hear that. Are you safe right now? Don't worry, could you share your bike number when ready?",
                    "intent": "claim_intake",
                    "insurance_sector": "motor",
                    "detected_emotion": "anxious_roadside",
                    "empathy_cue": "Checking user safety first",
                    "safety_check_status": "urgent_safety_inquiry",
                    "speech_rate": 1.0,
                    "speech_pitch": 1.0,
                }
                return Response(200, json={"choices": [{"message": {"content": __import__("json").dumps(payload)}}]})
            return await _original_post(self, url, *args, **kwargs)

        monkeypatch.setattr("httpx.AsyncClient.post", mock_groq_untagged)
        r_llm = await client.post(
            "/api/v1/voice/converse",
            json={
                "message": "My bike was suddenly in an accident and got some damage",
                "language": "en-IN",
                "known_fields": {},
                "history": history_after_greeting,
            },
        )
        assert r_llm.status_code == 200
        d_llm = r_llm.json()
        assert "<" not in d_llm["reply_text"]
        assert "<slow>" in d_llm["assistant_speech_text"]
        assert "<pauses>" in d_llm["assistant_speech_text"]
        assert d_llm["reasoning_trace"]["speech_rate"] < 1.0


@pytest.mark.anyio
async def test_vehicle_make_model_voice_capture_without_field_conflicts(monkeypatch):
    """
    Saying 'My bike is Pulsar 220' or 'My bike model is Pulsar 220' (even during follow-up turns
    for policy_reference, incident_date, or incident_location) must:
    1. Capture vehicle_make_model='Bajaj Pulsar 220F' and vehicle_type='bike'.
    2. NEVER pollute policy_reference ('PULSAR220' / 'MT-15'), incident_date ('Pulsar 220'), or incident_location.
    3. Acknowledge the bike model naturally and ask only for the missing field.
    """
    from app.evidence.cost_estimator import extract_vehicle_make_model
    from app.providers.transcription import extract_claim_fields, validate_and_normalize_field_answer

    settings = get_settings()
    monkeypatch.setattr(settings, "llm_api_url", None)
    monkeypatch.setattr(settings, "llm_api_key", None)
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "ollama_enabled", False)

    # Multilingual, phonetic STT & hyphenated model checks
    assert extract_vehicle_make_model("My bike model is Pulsar 220") == "Bajaj Pulsar 220F"
    assert extract_vehicle_make_model("My bike is Pulsar 220") == "Bajaj Pulsar 220F"
    assert extract_vehicle_make_model("my bike is impulser two twenty") == "Bajaj Pulsar 220F"
    assert extract_vehicle_make_model("నా బైక్ మోడల్ పల్సర్ 220") == "Bajaj Pulsar 220F"
    assert extract_vehicle_make_model("मेरी बाइक पल्सर २२० है") == "Bajaj Pulsar 220F"
    assert extract_vehicle_make_model("ನನ್ನ ಬೈಕ್ ಪಲ್ಸರ್ 220") == "Bajaj Pulsar 220F"
    assert extract_vehicle_make_model("என் பைக் பல்சர் 220") == "Bajaj Pulsar 220F"
    assert extract_vehicle_make_model("My bike is Yamaha MT-15") == "Yamaha MT-15"

    # MT-15 and Pulsar 220 must NEVER be misread as policy_reference
    f_mt, _ = extract_claim_fields("My bike is Yamaha MT-15")
    f_mt_map = {f.name: f.value for f in f_mt}
    assert f_mt_map["vehicle_type"] == "bike"
    assert f_mt_map["policy_reference"] is None

    f_p220, _ = extract_claim_fields("My bike is Pulsar 220")
    f_p220_map = {f.name: f.value for f in f_p220}
    assert f_p220_map["vehicle_type"] == "bike"
    assert f_p220_map["policy_reference"] is None
    assert f_p220_map["incident_date"] is None
    assert f_p220_map["incident_location"] is None

    # Validate follow-up guards directly for policy_reference, incident_date, incident_location
    for target in ("policy_reference", "incident_date", "incident_location"):
        vr = validate_and_normalize_field_answer(target, "My bike model is Pulsar 220", language="en-IN")
        assert vr["is_valid_for_target"] is False
        assert vr["vehicle_make_model"] == "Bajaj Pulsar 220F"
        assert target not in vr["routed_fields"]

    # End-to-end conversational follow-up when vehicle_type is already known and system expects policy_reference
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/voice/converse",
            json={
                "message": "My bike model is Pulsar 220",
                "language": "en-IN",
                "known_fields": {"vehicle_type": "bike", "damage_description": "Headlight broken"},
                "expected_field": "policy_reference",
                "history": [
                    {"sender": "user", "text": "My bike headlight broke"},
                    {"sender": "assistant", "text": "Sorry to hear that, are you safe? Could you share your vehicle registration or policy number?"},
                ],
            },
        )
        assert res.status_code == 200
        body = res.json()
        fmap = {f["name"]: f["value"] for f in body["fields"]}
        assert body["vehicle_make_model"] == "Bajaj Pulsar 220F"
        assert body["motor_slots"]["vehicle_make_model"] == "Bajaj Pulsar 220F"
        assert fmap["vehicle_type"] == "bike"
        assert fmap["policy_reference"] is None
        assert fmap["incident_date"] is None
        assert fmap["incident_location"] is None
        assert "Bajaj Pulsar 220F" in body["reply_text"]






