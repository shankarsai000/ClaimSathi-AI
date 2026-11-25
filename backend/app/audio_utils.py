"""
Audio validation and processing utilities for ClaimSathi AI.
Enforces 30-second maximum duration, supported format checks, and WAV generation.
"""

import io
import math
import struct
import wave
from typing import Optional, Tuple
from fastapi import HTTPException


SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".aac", ".m4a"}
SUPPORTED_MIME_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mpeg",
    "audio/mp3",
    "audio/ogg",
    "audio/flac",
    "audio/aac",
    "audio/m4a",
    "audio/mp4",
    "audio/x-m4a",
    "application/octet-stream",  # often sent by generic uploaders for wav
}


def validate_audio_file(
    filename: str,
    content_type: Optional[str],
    audio_bytes: bytes,
    max_duration_seconds: float = 30.0,
    max_size_bytes: int = 25 * 1024 * 1024,
) -> Tuple[str, Optional[float]]:
    """
    Validate audio format, file size, and duration.
    Returns (normalized_content_type, duration_seconds_if_detected).
    Raises HTTPException if invalid.
    """
    if not audio_bytes or len(audio_bytes) == 0:
        raise HTTPException(
            status_code=400,
            detail="The uploaded audio file is empty. Please record or select an audio file.",
        )

    if len(audio_bytes) > max_size_bytes:
        mb_limit = max_size_bytes / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"Audio file size exceeds the {mb_limit:.0f}MB limit.",
        )

    # Check extension
    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()

    if ext == ".webm" or (content_type and "webm" in content_type.lower()):
        raise HTTPException(
            status_code=400,
            detail=(
                "WebM audio format is not supported by the Gnani Speech API. "
                "Please record using ClaimSathi's built-in WAV recorder or upload "
                "a supported format (.wav, .mp3, .ogg, .flac, .aac, .m4a)."
            ),
        )

    if ext and ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported audio format '{ext}'. Supported formats are: "
                f"{', '.join(sorted(SUPPORTED_EXTENSIONS))}."
            ),
        )

    # Determine best content type
    normalized_mime = content_type or "audio/wav"
    if ext == ".wav":
        normalized_mime = "audio/wav"
    elif ext == ".mp3":
        normalized_mime = "audio/mpeg"
    elif ext == ".ogg":
        normalized_mime = "audio/ogg"
    elif ext == ".flac":
        normalized_mime = "audio/flac"
    elif ext == ".m4a":
        normalized_mime = "audio/m4a"

    # Enforce 30-second duration check
    duration = None
    # For WAV files, inspect RIFF header and sample count
    if audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        try:
            with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                framerate = wf.getframerate()
                nframes = wf.getnframes()
                if framerate > 0:
                    duration = nframes / float(framerate)
                    if duration > max_duration_seconds:
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                f"Audio duration ({duration:.1f}s) exceeds the maximum allowed "
                                f"limit of {max_duration_seconds:.0f} seconds. Please record a shorter clip."
                            ),
                        )
        except HTTPException:
            raise
        except Exception:
            # Non-fatal if header parsing fails on unusual WAV subtypes
            pass

    return normalized_mime, duration


def compute_wav_rms_energy(audio_bytes: bytes) -> Optional[float]:
    """
    Compute normalized RMS energy in [0.0, 1.0] for 16-bit PCM WAV buffers.
    Returns None when the audio is not a standard 16-bit PCM WAV stream.
    """
    if not audio_bytes or len(audio_bytes) < 44:
        return None
    if audio_bytes[:4] != b"RIFF" or audio_bytes[8:12] != b"WAVE":
        return None
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            if wf.getsampwidth() != 2:
                return None
            nframes = wf.getnframes()
            if nframes <= 0:
                return 0.0
            nchannels = max(1, wf.getnchannels())
            frames = wf.readframes(min(nframes, 480000))
            sample_count = len(frames) // 2
            if sample_count <= 0:
                return 0.0
            samples = struct.unpack(f"<{sample_count}h", frames[: sample_count * 2])
            sum_sq = sum(s * s for s in samples)
            rms = math.sqrt(sum_sq / float(sample_count)) / 32768.0
            return round(min(1.0, rms), 6)
    except Exception:
        return None


def generate_demo_wav(duration_seconds: float = 1.0, frequency: float = 440.0) -> bytes:
    """Generate a valid, playable 16-bit PCM mono WAV file for demo mode."""
    sample_rate = 16000
    num_samples = int(sample_rate * duration_seconds)
    buf = io.BytesIO()

    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)

        # Generate a gentle soft tone
        samples = bytearray()
        for i in range(num_samples):
            # Apply an envelope to prevent clicks
            envelope = math.sin(math.pi * i / num_samples)
            val = int(envelope * 8000.0 * math.sin(2.0 * math.pi * frequency * i / sample_rate))
            samples.extend(struct.pack("<h", max(-32768, min(32767, val))))

        wf.writeframes(bytes(samples))

    return buf.getvalue()

