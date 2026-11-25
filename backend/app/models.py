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
from typing import Optional, Any, Literal
from uuid import uuid4
from pydantic import BaseModel, Field

from .evidence.vehicle_identity import mask_pii_value


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


# ── Complete Indian Motor Insurance (2W & 4W) Additive Schema (Groups A-D) ──
class VoiceIntakeMotorSlots(BaseModel):
    """Group A conversational motor claim slots captured from voice/text intake."""
    claimed_registration: Optional[str] = None
    vehicle_make_model: Optional[str] = None
    loss_type: Optional[Literal["own_damage_accident", "theft", "fire_natural_calamity", "third_party"]] = None
    incident_time: Optional[str] = None
    driver_was_owner: Optional[bool] = None
    driver_name: Optional[str] = None
    driver_relationship: Optional[Literal["owner", "paid_driver", "relative_or_friend"]] = None
    vehicle_usage_type: Optional[Literal["private_social_domestic", "commercial_hire_reward"]] = None
    pillion_rider_present: Optional[bool] = None
    occupants_count: Optional[int] = None
    injury_or_third_party_flag: Optional[bool] = None
    police_fir_lodged_flag: Optional[bool] = None
    inspection_location: Optional[str] = None


class MotorClaimFormDetails(BaseModel):
    """Group B (compulsory structured form) & Group C (conditional) Indian Motor Claim fields."""
    # Group B1: Claimant & Policy Identification
    claimant_name: Optional[str] = None
    registered_mobile: Optional[str] = None
    claimant_email: Optional[str] = None
    residential_address: Optional[str] = None
    pincode: Optional[str] = None
    other_insurance_exists: Optional[bool] = None
    other_insurance_details: Optional[str] = None

    # Group B2: Incident & Vehicle Usage Details
    loss_type: Optional[Literal["own_damage_accident", "theft", "fire_natural_calamity", "third_party"]] = None
    incident_time: Optional[str] = None
    vehicle_usage_type: Optional[Literal["private_social_domestic", "commercial_hire_reward"]] = None
    pillion_rider_present: Optional[bool] = None
    occupants_count: Optional[int] = None
    vehicle_was_parked_unattended: Optional[bool] = None
    injury_or_third_party_flag: Optional[bool] = None
    police_fir_lodged_flag: Optional[bool] = None

    # Group B3: Driver Details at Time of Accident (skipped when theft or parked unattended)
    driver_was_owner: Optional[bool] = None
    driver_name: Optional[str] = None
    driver_age: Optional[int] = None
    driver_address: Optional[str] = None
    driver_relationship: Optional[Literal["owner", "paid_driver", "relative_or_friend"]] = None
    driver_license_number: Optional[str] = None
    driver_license_expiry: Optional[str] = None
    driver_license_class: Optional[Literal["MCWG", "MCWOG", "LMV", "HMV", "other"]] = None
    driver_issuing_rto: Optional[str] = None
    driver_under_intoxication: Optional[bool] = None
    driver_injured: Optional[bool] = None
    driver_license_mismatch_warning: Optional[str] = None

    # Group B4: Inspection, Settlement Mode & Workshop Details
    claim_settlement_mode: Optional[Literal["cashless", "reimbursement"]] = None
    inspection_location: Optional[str] = None
    preferred_inspection_datetime: Optional[str] = None
    workshop_name: Optional[str] = None
    workshop_address: Optional[str] = None
    workshop_contact: Optional[str] = None
    approx_estimated_repair_cost_inr: Optional[float] = None

    # Group B5: Legal Declarations & DPDP Consent
    dpdp_consent_granted: Optional[bool] = None
    dpdp_consent_timestamp: Optional[str] = None
    truthfulness_declaration_accepted: Optional[bool] = None
    declaration_place: Optional[str] = None
    declaration_date: Optional[str] = None
    insured_digital_signature: Optional[str] = None

    # Group C Trigger 1: claim_settlement_mode == "reimbursement"
    bank_account_holder_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_ifsc_code: Optional[str] = None
    bank_branch_name: Optional[str] = None

    # Group C Trigger 2: police_fir_lodged_flag == True
    fir_or_gd_number: Optional[str] = None
    police_station_name: Optional[str] = None
    fir_report_date: Optional[str] = None
    fir_complainant_name: Optional[str] = None

    # Group C Trigger 3: loss_type == "theft"
    non_traceable_report_status: Optional[Literal["pending", "obtained", "not_applicable"]] = None
    all_original_keys_available: Optional[bool] = None
    financier_hypothecated: Optional[bool] = None
    financier_name: Optional[str] = None
    stolen_accessories_details: Optional[str] = None

    # Group C Trigger 4: injury_or_third_party_flag == True or driver_injured == True
    third_party_loss_type: Optional[Literal["injury", "death", "property_damage", "driver_or_occupant_only"]] = None
    third_party_injured_count: Optional[int] = None
    hospital_and_treatment_details: Optional[str] = None
    third_party_vehicle_reg: Optional[str] = None
    third_party_policy_details: Optional[str] = None
    third_party_damage_summary: Optional[str] = None
    witness_name: Optional[str] = None
    witness_contact: Optional[str] = None

    # Group C Trigger 5: loss_type == "fire_natural_calamity"
    fire_brigade_report_number: Optional[str] = None

    def masked_copy(self, mask_all_sensitive: bool = True) -> "MotorClaimFormDetails":
        """Return a shallow copy with DPDP-sensitive identifiers masked for logs/summaries."""
        updates: dict[str, Any] = {}
        if self.bank_account_number:
            updates["bank_account_number"] = mask_pii_value(self.bank_account_number, 4)
        if mask_all_sensitive:
            if self.driver_license_number:
                updates["driver_license_number"] = mask_pii_value(self.driver_license_number, 4)
            if self.registered_mobile:
                updates["registered_mobile"] = mask_pii_value(self.registered_mobile, 4)
        return self.model_copy(update=updates)


class InsurerPolicyMaster(BaseModel):
    """Group D: Insurer-side policy master details (Adjuster/Dossier only; never asked on Customer Portal)."""
    claim_reference_number: Optional[str] = None
    policy_start_date: Optional[str] = None
    policy_end_date: Optional[str] = None
    idv_inr: Optional[float] = None
    ncb_percent: Optional[float] = None
    coverage_type: Optional[str] = None
    active_addons: list[str] = Field(default_factory=list)
    compulsory_excess_inr: Optional[float] = None
    voluntary_excess_inr: Optional[float] = None
    hypothecation_financier: Optional[str] = None


class ExternalRegistryChecks(BaseModel):
    """Group D: Nullable external government/industry registry hooks for next sprint."""
    engine_number: Optional[str] = None
    chassis_vin_number: Optional[str] = None
    vahan_status: Optional[str] = "pending_integration"
    sarathi_dl_status: Optional[str] = "pending_integration"
    iib_cross_claim_status: Optional[str] = "pending_integration"
    edar_sync_status: Optional[str] = "pending_integration"


class SurveyorAssessment(BaseModel):
    """Group D: Licensed surveyor assessment fields (Adjuster Portal & Dossier only)."""
    surveyor_name: Optional[str] = None
    surveyor_irdai_license_no: Optional[str] = None
    odometer_reading_km: Optional[int] = None
    damage_freshness_classification: Literal["fresh", "pre_existing", "mixed", "pending"] = "pending"
    imt_gr9_depreciation_inr: Optional[float] = None
    salvage_value_inr: Optional[float] = None
    constructive_total_loss: Optional[bool] = None
    net_assessed_payable_inr: Optional[float] = None


class MotorAdjusterPlaceholders(BaseModel):
    """Group D container for Insurer, Registry, and Surveyor read-only/adjuster-managed fields."""
    insurer_policy_master: InsurerPolicyMaster = Field(default_factory=InsurerPolicyMaster)
    external_registry_checks: ExternalRegistryChecks = Field(default_factory=ExternalRegistryChecks)
    surveyor_assessment: SurveyorAssessment = Field(default_factory=SurveyorAssessment)


class AdjusterAssessmentUpdateRequest(BaseModel):
    """Adjuster Portal update payload for Group D fields."""
    insurer_policy_master: Optional[InsurerPolicyMaster] = None
    external_registry_checks: Optional[ExternalRegistryChecks] = None
    surveyor_assessment: Optional[SurveyorAssessment] = None


# ── ClaimRecord ────────────────────────────────────────
class ClaimRecord(BaseModel):
    """Persisted claim ticket."""
    id: str = Field(default_factory=lambda: f"DEMO-{uuid4().hex[:8].upper()}")
    customer_id: str = "USR-100001"
    insurance_type: str = "motor"
    policy_reference: str
    claimed_registration: Optional[str] = None
    insurer_name: str = "Bharat General Insurance"
    policy_type: str = "Comprehensive Motor Policy"
    incident_location: str
    incident_date: str
    vehicle_type: str
    vehicle_make_model: Optional[str] = None
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
    motor_claim_form: MotorClaimFormDetails = Field(default_factory=MotorClaimFormDetails)
    insurer_adjuster_data: MotorAdjusterPlaceholders = Field(default_factory=MotorAdjusterPlaceholders)
    masked_pii_summary: dict[str, Optional[str]] = Field(default_factory=dict)
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
    claimant_name: Optional[str] = None
    registered_mobile_masked: Optional[str] = None
    claimant_email: Optional[str] = None
    residential_address: Optional[str] = None
    pincode: Optional[str] = None
    other_insurance_exists: Optional[bool] = None
    other_insurance_details: Optional[str] = None


class DossierSection02Policy(BaseModel):
    policy_number: str
    insurer_name: str
    policy_type: str
    insurance_category: str = "Motor Insurance"
    verification_status: str = "Unverified (Customer-entered value)"
    claimed_registration: Optional[str] = None
    vehicle_make_model: Optional[str] = None
    vehicle_usage_type: Optional[str] = None
    insurer_policy_master: dict[str, Any] = Field(default_factory=dict)


class DossierSection03Incident(BaseModel):
    incident_date_time: str
    incident_location: str
    incident_description: str
    vehicle_details: str
    people_involved: str
    injuries_or_damage: str
    loss_type: Optional[str] = None
    incident_time: Optional[str] = None
    pillion_rider_present: Optional[bool] = None
    occupants_count: Optional[int] = None
    vehicle_was_parked_unattended: Optional[bool] = None
    injury_or_third_party_flag: Optional[bool] = None
    police_fir_lodged_flag: Optional[bool] = None
    driver_details: dict[str, Any] = Field(default_factory=dict)
    conditional_disclosures: dict[str, Any] = Field(default_factory=dict)


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
    driver_license_mismatch_warning: Optional[str] = None
    external_registry_checks: dict[str, Any] = Field(default_factory=dict)
    surveyor_assessment: dict[str, Any] = Field(default_factory=dict)


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
    motor_checklist_items: list[str] = Field(default_factory=list)


class DossierSection08PreparationSummary(BaseModel):
    incident_summary: str
    available_evidence_summary: str
    outstanding_requirements: list[str]
    recommended_next_steps: list[str]
    claim_settlement_mode: Optional[str] = None
    inspection_location: Optional[str] = None
    preferred_inspection_datetime: Optional[str] = None
    workshop_details: dict[str, Any] = Field(default_factory=dict)
    approx_estimated_repair_cost_inr: Optional[float] = None
    reimbursement_bank_summary: dict[str, Any] = Field(default_factory=dict)


class DossierSection09Declaration(BaseModel):
    customer_confirmed: bool
    confirmed_by_name: str
    confirmed_by_id: str
    report_generation_timestamp: str
    report_id: str
    report_version: str
    dpdp_consent_granted: Optional[bool] = None
    dpdp_consent_timestamp: Optional[str] = None
    truthfulness_declaration_accepted: Optional[bool] = None
    declaration_place: Optional[str] = None
    declaration_date: Optional[str] = None
    insured_digital_signature: Optional[str] = None
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
    user_declared_fields: dict[str, Any] = Field(default_factory=dict)
    insurer_and_registry_fields: dict[str, Any] = Field(default_factory=dict)


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
    claimed_registration: Optional[str] = None
    incident_location: str = Field(..., min_length=1)
    incident_date: str = Field(..., min_length=1)
    vehicle_type: str = Field(..., min_length=1)
    vehicle_make_model: Optional[str] = None
    damage_description: str = Field(..., min_length=1)
    transcript: str = ""
    customer_id: Optional[str] = None
    insurer_name: Optional[str] = "Bharat General Insurance"
    policy_type: Optional[str] = "Comprehensive Motor Policy"
    people_involved: Optional[str] = "Policyholder (Driver)"
    injuries_reported: Optional[str] = "No physical injuries reported"
    detailed_statement: Optional[str] = None
    conversation_turns: Optional[list[dict[str, Any]]] = None
    evidence_id: Optional[str] = None
    claimed_vehicle_type: Optional[str] = "four_wheeler"
    verification_decision: Optional[str] = None
    spoof_risk: Optional[float] = None
    total_estimated_inr: Optional[int] = None
    cost_estimate: Optional[dict[str, Any]] = None
    motor_claim_form: Optional[MotorClaimFormDetails] = None
    insurer_adjuster_data: Optional[MotorAdjusterPlaceholders] = None


class ClaimUpdateRequest(BaseModel):
    policy_reference: Optional[str] = None
    claimed_registration: Optional[str] = None
    insurer_name: Optional[str] = None
    policy_type: Optional[str] = None
    incident_location: Optional[str] = None
    incident_date: Optional[str] = None
    vehicle_type: Optional[str] = None
    vehicle_make_model: Optional[str] = None
    damage_description: Optional[str] = None
    people_involved: Optional[str] = None
    injuries_reported: Optional[str] = None
    detailed_statement: Optional[str] = None
    customer_confirmation: Optional[bool] = None
    evidence_id: Optional[str] = None
    claimed_vehicle_type: Optional[str] = None
    verification_decision: Optional[str] = None
    spoof_risk: Optional[float] = None
    total_estimated_inr: Optional[int] = None
    cost_estimate: Optional[dict[str, Any]] = None
    motor_claim_form: Optional[MotorClaimFormDetails] = None
    insurer_adjuster_data: Optional[MotorAdjusterPlaceholders] = None


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


class ConversationalReasoningTrace(BaseModel):
    """Structured cognitive & emotional reasoning trace produced before the voice agent speaks."""
    detected_emotion: str = "calm_informative"
    empathy_cue: str = "Warm, attentive listening"
    safety_check_status: str = "routine"
    inferred_cause: Optional[str] = None
    drivability_assessment: str = "unknown"
    plausibility_note: str = "Consistent narrative mechanics"
    causal_question_asked: Optional[str] = None
    thought_process: str = ""
    speech_rate: float = 1.0
    speech_pitch: float = 1.0
    llm_provider: str = "local-cognitive"
    detected_intent: str = "claim_intake"
    insurance_sector: str = "motor"
    applied_gnani_tags: list[str] = Field(default_factory=list)


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
    claimed_vehicle_type: Optional[str] = None
    vehicle_make_model: Optional[str] = None
    vehicle_registration: Optional[str] = None
    claimed_registration: Optional[str] = None
    motor_slots: Optional[VoiceIntakeMotorSlots] = None
    damage_keywords: list[str] = Field(default_factory=list)
    incident_description: Optional[str] = None
    reasoning_trace: Optional[ConversationalReasoningTrace] = None
    no_speech_detected: bool = False


class EvidenceNarrationRequest(BaseModel):
    """Request model for multimodal evidence narration."""
    decision: str
    claimed_vehicle_type: str = "four_wheeler"
    detected_vehicle_category: Optional[str] = None
    vehicle_category_mismatch: bool = False
    total_estimated_inr: float = 0.0
    damages: list[Any] = Field(default_factory=list)
    language: Optional[str] = "hi-IN"
    reasons: list[str] = Field(default_factory=list)


class EvidenceNarrationResponse(BaseModel):
    """Response model for multimodal evidence narration."""
    spoken_narration: str
    narration_text: str
    language: str
    decision: str
    total_estimated_inr: float


class ExtractSlotsRequest(BaseModel):
    """Request model for code-mixed multi-slot claim extraction."""
    text: str = Field(..., min_length=1, max_length=3000)
    language: Optional[str] = "indic-auto"


class ExtractSlotsResponse(BaseModel):
    """Response model for code-mixed multi-slot extraction and concise voice reply."""
    transcript: str
    claimed_vehicle_type: Optional[str] = None
    vehicle_make_model: Optional[str] = None
    vehicle_registration: Optional[str] = None
    claimed_registration: Optional[str] = None
    motor_slots: Optional[VoiceIntakeMotorSlots] = None
    damage_keywords: list[str] = Field(default_factory=list)
    incident_description: str
    detected_language: str
    reply_text: str
    fields: list[ClaimField] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    assistant_dialogue: str
    assistant_speech_text: str
    assistant_language: str


class ConverseTurnRequest(BaseModel):
    """Stateful multi-turn conversational intake request."""
    message: str = Field(..., min_length=1, max_length=4000)
    language: Optional[str] = "indic-auto"
    known_fields: dict[str, Optional[str]] = Field(default_factory=dict)
    known_motor_slots: Optional[dict[str, Any]] = None
    history: list[dict[str, str]] = Field(default_factory=list)
    expected_field: Optional[str] = None


class ConverseTurnResponse(BaseModel):
    """Stateful multi-turn conversational intake response."""
    transcript: str
    detected_language: str
    assistant_language: str
    reply_text: str
    assistant_dialogue: str
    assistant_speech_text: str
    fields: list[ClaimField] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    known_fields: dict[str, Optional[str]] = Field(default_factory=dict)
    newly_captured: dict[str, str] = Field(default_factory=dict)
    claimed_vehicle_type: Optional[str] = None
    vehicle_make_model: Optional[str] = None
    vehicle_registration: Optional[str] = None
    claimed_registration: Optional[str] = None
    motor_slots: Optional[VoiceIntakeMotorSlots] = None
    damage_keywords: list[str] = Field(default_factory=list)
    incident_description: Optional[str] = None
    is_complete: bool = False
    no_speech_detected: bool = False
    reasoning_trace: Optional[ConversationalReasoningTrace] = None
