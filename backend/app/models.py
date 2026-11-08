"""
ClaimSathi AI – Complete Domain Models (Phases 1–7)
Aligned with _ClaimSathi AI product flow.pdf:
1. Customer Platform (Users, Unique IDs USR-XXXXXX, Consents, JWT Auth)
2. Claim Intelligence Engine (Gnani Prisma STT + Timbre TTS, Structured Extraction, Conversations)
3. Evidence Integrity Engine (C2PA, SynthID, EXIF, SHA-256, 64-bit DCT pHash, Guided Live Camera)
4. Claim Documentation Engine (9-Section Professional Dossier, Layer 1 Canonical Schema JSON, PDF Report)
5. Customer Claims Vault & Audit Logs
6. Layer 2 Insurer Adapter & Mock Insurer Integration Gateway
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
    EVIDENCE_PENDING = "evidence_pending"
    SCREENED = "screened"
    CONFIRMED = "confirmed"
    REPORT_GENERATED = "report_generated"
    SUBMITTED = "submitted"  # demo-only; simulated insurer submission
    ARCHIVED = "archived"


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


class ProvenanceSignalResult(str, Enum):
    """Exact MVP classification rules from Page 2 of PDF."""
    SUPPORTED_AI_WATERMARK = "Supported AI watermark detected"
    VALID_AI_CREDENTIAL = "Valid AI-generation credential detected"
    INVALID_CREDENTIAL = "Invalid credential"
    NO_SUPPORTED_SIGNAL = "No supported signal"
    METADATA_MISSING = "Metadata missing"


class ProvenanceSystemResponse(str, Enum):
    """Exact System response mapping from Page 2 of PDF."""
    AI_PROVENANCE_DETECTED = "AI provenance detected"
    AI_GENERATED_PROVENANCE_DETECTED = "AI-generated provenance detected"
    INTEGRITY_WARNING = "Integrity warning"
    INCONCLUSIVE = "Inconclusive"
    METADATA_UNAVAILABLE = "Metadata unavailable"


class DuplicateStatus(str, Enum):
    UNIQUE = "unique"
    EXACT_DUPLICATE = "exact_duplicate"      # SHA-256 match -> Duplicate Flag
    VISUAL_DUPLICATE = "visual_duplicate"    # pHash match -> Possible Reuse -> Human Review


# ── Phase 1: Customer Registration / Login / Consent ──
class UserConsentInput(BaseModel):
    data_processing_consent: bool = True
    evidence_screening_consent: bool = True
    retention_policy_acknowledged: bool = True


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=3, max_length=120)
    phone: str = Field(..., min_length=8, max_length=20)
    password: str = Field(..., min_length=4, max_length=128)
    declared_insurer: str = Field(default="Bharat General Insurance")
    consents: UserConsentInput = Field(default_factory=UserConsentInput)


class LoginRequest(BaseModel):
    identifier: str = Field(..., description="Email, phone, or customer ID (e.g. USR-100001)")
    password: Optional[str] = None
    otp_code: Optional[str] = None
    demo_quick_login: bool = False


class OTPRequest(BaseModel):
    identifier: str


class UserProfile(BaseModel):
    customer_id: str
    name: str
    email: str
    phone: str
    declared_insurer: str
    consents: UserConsentInput
    total_claims: int = 0
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile


# ── ClaimField & ClaimDraft ────────────────────────────
class ClaimField(BaseModel):
    """A single extracted field with confidence metadata."""
    name: str
    label: str
    value: Optional[str] = None
    confidence: FieldConfidence = FieldConfidence.MISSING
    is_edited: bool = False
    is_verified: bool = False
    follow_up_question: Optional[str] = None


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
    customer_id: str = "USR-100001"
    insurance_type: str = "motor"
    policy_reference: str
    insurer_name: str = "Bharat General Insurance"
    policy_type: str = "Comprehensive Motor Policy"
    incident_location: str
    incident_date: str
    vehicle_type: str
    damage_description: str
    people_involved: str = "Policyholder (Driver)"
    injuries_reported: str = "No physical injuries reported"
    detailed_statement: str = ""
    transcript: str
    status: ClaimStatus = ClaimStatus.CONFIRMED
    customer_confirmation: bool = True
    report_status: str = "not_generated"
    insurer_submission_status: str = "not_submitted"
    evidence_count_images: int = 0
    evidence_count_videos: int = 0
    is_demo: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Timeline Event ─────────────────────────────────────
class TimelineEvent(BaseModel):
    timestamp: datetime
    title: str
    description: str


# ── Phase 3 & 4: Evidence Collection & Screening ───────
class CaptureSessionRequest(BaseModel):
    claim_id: Optional[str] = None
    capture_type: str = "guided_video_and_photo"


class CaptureSessionResponse(BaseModel):
    session_id: str
    claim_id: Optional[str] = None
    instructions: list[str]
    created_at: datetime
    expires_in_seconds: int = 900


class EvidenceCheckRecord(BaseModel):
    check_id: str
    evidence_id: str
    claim_id: str
    sha256_hash: str
    perceptual_hash: Optional[str] = None
    magic_bytes_valid: bool = True
    detected_format: str = "unknown"
    malware_scan_status: str = "clean"
    c2pa_found: bool = False
    synthid_found: bool = False
    provenance_result: str = ProvenanceSignalResult.NO_SUPPORTED_SIGNAL.value
    provenance_system_response: str = ProvenanceSystemResponse.INCONCLUSIVE.value
    provenance_details: dict[str, Any] = Field(default_factory=dict)
    duplicate_status: DuplicateStatus = DuplicateStatus.UNIQUE
    duplicate_match_type: Optional[str] = None  # "same_claim" or "cross_claim"
    matched_claim_reference: Optional[str] = None  # Privacy-protected reference
    matched_evidence_id: Optional[str] = None
    hamming_distance: Optional[int] = None
    requires_human_review: bool = False
    screening_outcome_label: str = ""
    checked_at: datetime


class EvidenceAssetRecord(BaseModel):
    evidence_id: str
    claim_id: str
    user_id: str
    label: str  # e.g. "Image 01", "Video 01"
    media_type: str  # "image" | "video"
    capture_method: str  # "upload_photo" | "upload_video" | "live_photo" | "guided_video"
    capture_session_id: Optional[str] = None
    original_filename: str
    detected_mime: str
    file_size_bytes: int
    width: Optional[int] = None
    height: Optional[int] = None
    exif_metadata: dict[str, Any] = Field(default_factory=dict)
    upload_timestamp: datetime
    screening: EvidenceCheckRecord


# ── Phase 5: 9-Section Professional Dossier & Canonical Schema ──
class DossierSection01Customer(BaseModel):
    customer_id: str
    name: str
    email: str
    phone: str
    declared_insurer: str


class DossierSection02Policy(BaseModel):
    policy_number: str
    insurer_name: str
    policy_type: str
    insurance_category: str = "Motor Insurance"
    verification_status: str = "Unverified (Customer-entered value)"


class DossierSection03Incident(BaseModel):
    incident_date_time: str
    incident_location: str
    incident_description: str
    vehicle_details: str
    people_involved: str
    injuries_or_damage: str


class DossierSection04Statement(BaseModel):
    chronological_account: str
    source_language: str = "Multilingual (Hinglish / Telugu / English)"
    customer_confirmed: bool = True


class DossierEvidenceItem(BaseModel):
    item_label: str  # "Image 01", "Image 02", "Video 01"
    evidence_id: str
    media_type: str
    capture_method: str
    screening_outcome: str
    provenance_response: str
    duplicate_status: str
    requires_human_review: bool


class DossierSection05EvidenceInventory(BaseModel):
    items: list[DossierEvidenceItem]
    disclaimer: str = "Illustrative screening results, not actual verification."


class DossierSection06ValidationReview(BaseModel):
    missing_information: list[str]
    inconsistent_answers: list[str]
    evidence_warnings: list[str]
    unresolved_fields: list[str]
    human_review_recommended: bool = False


class DossierSupportingDoc(BaseModel):
    evidence_id: str
    filename: str
    media_type: str
    file_size_bytes: int
    sha256_hash: str
    perceptual_hash: Optional[str] = None
    capture_session_id: Optional[str] = None
    upload_timestamp: str


class DossierSection07SupportingDocuments(BaseModel):
    documents: list[DossierSupportingDoc]


class DossierSection08PreparationSummary(BaseModel):
    incident_summary: str
    available_evidence_summary: str
    outstanding_requirements: list[str]
    recommended_next_steps: list[str]


class DossierSection09Declaration(BaseModel):
    customer_confirmed: bool
    confirmed_by_name: str
    confirmed_by_id: str
    report_generation_timestamp: str
    report_id: str
    report_version: str
    regulatory_disclaimer: str = (
        "ClaimSathi AI preparation report. Not an insurer-issued claim form, "
        "surveyor report, claim approval or guarantee of settlement."
    )


class ProfessionalClaimDossier(BaseModel):
    """Complete 9-Section Professional Insurance Claim Dossier (Pages 5-6 of PDF)."""
    claim_id: str
    report_id: str
    report_version: str = "1.0"
    insurance_category: str = "Motor Insurance"
    status_badge: str = "Customer confirmed"
    section_01_customer: DossierSection01Customer
    section_02_policy: DossierSection02Policy
    section_03_incident: DossierSection03Incident
    section_04_statement: DossierSection04Statement
    section_05_evidence_inventory: DossierSection05EvidenceInventory
    section_06_validation_review: DossierSection06ValidationReview
    section_07_supporting_documents: DossierSection07SupportingDocuments
    section_08_preparation_summary: DossierSection08PreparationSummary
    section_09_declaration: DossierSection09Declaration


class CanonicalClaimSchema(BaseModel):
    """Layer 1 — ClaimSathi Canonical Schema (Pages 6-7 of PDF)."""
    claim_id: str
    customer_id: str
    insurance_type: str = "motor"
    policy: dict[str, Any]
    incident: dict[str, Any]
    evidence: dict[str, Any]
    validation: dict[str, Any]
    customer_confirmation: bool = True
    report_status: str = "generated"
    insurer_submission_status: str = "not_submitted"


class ReportRecord(BaseModel):
    report_id: str
    claim_id: str
    user_id: str
    version: str
    dossier: ProfessionalClaimDossier
    canonical_schema: CanonicalClaimSchema
    pdf_download_url: str
    json_download_url: str
    generated_at: datetime


# ── Phase 7: Mock Insurer Integration Gateway ──────────
class InsurerSubmissionRequest(BaseModel):
    recipient: str = Field(default="DEMO_INSURER_A", description="Target insurer adapter ID")
    submission_channel: str = Field(default="Official insurer API", description="API | Portal | SFTP")
    customer_authorized: bool = True


class InsurerSubmissionResponse(BaseModel):
    """Exact Mock Insurer Gateway response from Page 11 of PDF."""
    submission_id: str
    claim_id: str
    recipient: str
    recipient_display_name: str = "Demo Insurer A (Motor Claims API)"
    delivery_status: str = "simulated_success"
    insurer_claim_reference: str
    processing_status: str = "received"
    pipeline_steps: list[dict[str, str]] = Field(default_factory=list)
    mapped_payload_preview: dict[str, Any] = Field(default_factory=dict)
    submitted_at: datetime
    disclaimer: str = "Demo only — not a real insurer submission"


# ── API Request / Response ─────────────────────────────
class ClaimCreateRequest(BaseModel):
    policy_reference: str = Field(..., min_length=1, description="Synthetic policy ID")
    incident_location: str = Field(..., min_length=1)
    incident_date: str = Field(..., min_length=1)
    vehicle_type: str = Field(..., min_length=1)
    damage_description: str = Field(..., min_length=1)
    transcript: str = ""
    customer_id: Optional[str] = None
    insurer_name: Optional[str] = "Bharat General Insurance"
    policy_type: Optional[str] = "Comprehensive Motor Policy"
    people_involved: Optional[str] = "Policyholder (Driver)"
    injuries_reported: Optional[str] = "No physical injuries reported"
    detailed_statement: Optional[str] = None
    conversation_turns: Optional[list[dict[str, Any]]] = None


class ClaimUpdateRequest(BaseModel):
    policy_reference: Optional[str] = None
    insurer_name: Optional[str] = None
    policy_type: Optional[str] = None
    incident_location: Optional[str] = None
    incident_date: Optional[str] = None
    vehicle_type: Optional[str] = None
    damage_description: Optional[str] = None
    people_involved: Optional[str] = None
    injuries_reported: Optional[str] = None
    detailed_statement: Optional[str] = None
    customer_confirmation: Optional[bool] = None


class ClaimCreateResponse(BaseModel):
    id: str
    claim_id: str = ""
    status: ClaimStatus
    message: str
    is_demo: bool = True


class ClaimDetailResponse(BaseModel):
    claim: ClaimRecord
    timeline: list[TimelineEvent]
    evidence: list[EvidenceAssetRecord] = Field(default_factory=list)
    reports: list[ReportRecord] = Field(default_factory=list)
    insurer_submissions: list[InsurerSubmissionResponse] = Field(default_factory=list)
    is_demo: bool = True


class ClaimListResponse(BaseModel):
    claims: list[ClaimRecord]
    total: int
    is_demo: bool = True


class VaultSummaryResponse(BaseModel):
    user: UserProfile
    total_cases: int
    claims: list[ClaimRecord]
    recent_reports: list[dict[str, Any]]
    audit_logs: list[dict[str, Any]]


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
    language: str = "hi-en"


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
