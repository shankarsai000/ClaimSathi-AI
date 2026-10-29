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
    """Verify 402 from Gnani produces clear credits error."""
    settings = get_settings()
    monkeypatch.setattr(settings, "gnani_api_key_id", "valid_key")

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
