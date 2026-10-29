"""
ClaimSathi AI – Domain Models (Phase 2)
Includes typed contracts for Gnani Prisma STT and Timbre TTS integrations.
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional, Any
from uuid import uuid4
from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────
class ClaimStatus(str, Enum):
    DRAFT = "draft"
    PENDING_INFO = "pending_info"
    CONFIRMED = "confirmed"
    SUBMITTED = "submitted"  # demo-only; no real submission


class FieldConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MISSING = "missing"


class VehicleType(str, Enum):
    CAR = "car"
    BIKE = "bike"
    TRUCK = "truck"
    AUTO_RICKSHAW = "auto_rickshaw"
    BUS = "bus"
    OTHER = "other"


# ── ClaimField ─────────────────────────────────────────
class ClaimField(BaseModel):
    """A single extracted field with confidence metadata."""
    name: str
    label: str
    value: Optional[str] = None
    confidence: FieldConfidence = FieldConfidence.MISSING
    is_edited: bool = False
    follow_up_question: Optional[str] = None


# ── ClaimDraft ─────────────────────────────────────────
class ClaimDraft(BaseModel):
    """In-progress claim before confirmation."""
    transcript: str = ""
    fields: list[ClaimField] = []
    missing_fields: list[str] = []
    status: ClaimStatus = ClaimStatus.DRAFT
    is_demo: bool = True


# ── ClaimRecord ────────────────────────────────────────
class ClaimRecord(BaseModel):
    """Persisted claim ticket."""
    id: str = Field(default_factory=lambda: f"DEMO-{uuid4().hex[:8].upper()}")
    policy_reference: str
    incident_location: str
    incident_date: str
    vehicle_type: str
    damage_description: str
    transcript: str
    status: ClaimStatus = ClaimStatus.CONFIRMED
    is_demo: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Timeline Event ─────────────────────────────────────
class TimelineEvent(BaseModel):
    timestamp: datetime
    title: str
    description: str


# ── API Request / Response ─────────────────────────────
class ClaimCreateRequest(BaseModel):
    policy_reference: str = Field(..., min_length=1, description="Synthetic policy ID")
    incident_location: str = Field(..., min_length=1)
    incident_date: str = Field(..., min_length=1)
    vehicle_type: str = Field(..., min_length=1)
    damage_description: str = Field(..., min_length=1)
    transcript: str = ""


class ClaimCreateResponse(BaseModel):
    id: str
    status: ClaimStatus
    message: str
    is_demo: bool = True


class ClaimDetailResponse(BaseModel):
    claim: ClaimRecord
    timeline: list[TimelineEvent]
    is_demo: bool = True


class ClaimListResponse(BaseModel):
    claims: list[ClaimRecord]
    total: int
    is_demo: bool = True


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    gnani_configured: bool = False
    gnani_stt_model: str = ""
    gnani_tts_model: str = ""
    is_demo: bool = True


class TranscriptRequest(BaseModel):
    use_mock: bool = True
    language: str = "hi-en"  # Hinglish


class TranscriptResponse(BaseModel):
    transcript: str
    language: str
    is_mock: bool = True
    fields: list[ClaimField]
    missing_fields: list[str]


# ── Voice API Models (Phase 2 - Gnani AI) ──────────────
class SpeechSynthesizeRequest(BaseModel):
    """Request model for Gnani Timbre TTS speech synthesis."""
    text: str = Field(..., min_length=1, max_length=2000, description="Text to synthesize into speech")
    language: Optional[str] = Field(None, description="Language code (e.g. hi-IN)")
    voice: Optional[str] = Field(None, description="Verified voice name (e.g. Nalini)")
    speed: float = Field(1.0, ge=0.5, le=2.0, description="Speech rate")
    demo: bool = Field(False, description="Whether to simulate speech response")


class VoiceTranscribeResponse(BaseModel):
    """Response model for Gnani Prisma STT transcription."""
    transcript: str
    model: str
    detected_language: Optional[str] = None
    is_mock: bool = False
    request_metadata: dict[str, Any] = Field(default_factory=dict)
    fields: list[ClaimField] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    assistant_dialogue: Optional[str] = None
    assistant_speech_text: Optional[str] = None
    assistant_language: Optional[str] = None
