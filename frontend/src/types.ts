// Typed API contracts matching the backend Pydantic models (Phases 1–7)

export type FieldConfidence = 'high' | 'medium' | 'low' | 'missing'
export type ClaimStatusType =
  | 'draft'
  | 'evidence_pending'
  | 'evidence_screened'
  | 'pending_info'
  | 'confirmed'
  | 'dossier_generated'
  | 'submitted'
  | 'archived'

export interface ClaimField {
  name: string
  label: string
  value: string | null
  confidence: FieldConfidence
  is_edited: boolean
  follow_up_question: string | null
}

export interface RequestMetadata {
  request_id?: string
  processing_time?: number
  end_to_end_latency?: number
  mode?: string
  duration_seconds?: number
  audio_filename?: string
  bytes_received?: number
}

export interface VoiceTranscribeResponse {
  transcript: string
  model: string
  detected_language?: string | null
  is_mock: boolean
  request_metadata: RequestMetadata
  fields: ClaimField[]
  missing_fields: string[]
  assistant_dialogue?: string | null
  assistant_speech_text?: string | null
  assistant_language?: string | null
}

export interface SpeechSynthesizeRequest {
  text: string
  language?: string
  voice?: string
  speed?: number
  demo?: boolean
}

export interface HealthResponse {
  status: string
  version: string
  environment: string
  gnani_configured: boolean
  gnani_stt_model: string
  gnani_tts_model: string
  is_demo: boolean
}

export interface TranscriptResponse {
  transcript: string
  language: string
  is_mock: boolean
  fields: ClaimField[]
  missing_fields: string[]
}

// ── Phase 1: Customer Account & Vault ──

export interface UserConsentInput {
  ai_assistance_accepted: boolean
  media_storage_accepted: boolean
  fraud_screening_accepted: boolean
  privacy_policy_accepted: boolean
}

export interface UserProfile {
  customer_id: string
  name: string
  email: string
  phone: string
  preferred_language: string
  created_at: string
  consents: UserConsentInput
}

export interface RegisterRequest {
  name: string
  email: string
  phone: string
  password?: string
  preferred_language?: string
  consents?: UserConsentInput
}

export interface LoginRequest {
  identifier: string
  password?: string
  otp?: string
  demo_quick_login?: boolean
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: UserProfile
  message: string
}

// ── Phase 4: Evidence Collection & Integrity Engine ──

export type CaptureMethod = 'upload_photo' | 'upload_video' | 'live_photo' | 'guided_video'
export type ProvenanceStatus =
  | 'ai_provenance_detected'
  | 'ai_generated_provenance_detected'
  | 'integrity_warning'
  | 'inconclusive'
  | 'metadata_unavailable'
export type DuplicateStatus = 'unique' | 'exact_duplicate' | 'visual_duplicate'

export interface CaptureSessionInstruction {
  step: number
  code: string
  prompt: string
}

export interface CaptureSessionResponse {
  session_id: string
  claim_id: string
  capture_type: string
  instructions: CaptureSessionInstruction[]
  created_at: string
  expires_at: string
}

export interface EvidenceCheckRecord {
  check_id: string
  asset_id: string
  claim_id: string
  magic_bytes_valid: boolean
  detected_mime: string
  sha256_hash: string
  phash_hex: string | null
  provenance_status: ProvenanceStatus
  provenance_signal: string
  provenance_summary: string
  duplicate_status: DuplicateStatus
  matched_claim_id: string | null
  matched_asset_id: string | null
  hamming_distance: number | null
  requires_human_review: boolean
  privacy_masked_match: boolean
  exif_summary: Record<string, any>
  screening_outcome_label: string
  checked_at: string
}

export interface EvidenceAssetRecord {
  asset_id: string
  claim_id: string
  customer_id: string
  label: string
  original_filename: string
  media_type: string
  mime_type: string
  size_bytes: number
  capture_method: CaptureMethod
  capture_session_id: string | null
  width: number | null
  height: number | null
  duration_seconds: number | null
  storage_path: string
  created_at: string
  screening: EvidenceCheckRecord | null
}

// ── Phase 6: 9-Section Professional Claim Dossier & Layer 1 Canonical Schema ──

export interface CanonicalClaimSchema {
  claim_id: string
  customer_id: string
  insurance_type: string
  policy: {
    policy_number: string
    holder_name: string
  }
  incident: {
    date: string
    time: string
    location: string
    description: string
    vehicle_type: string
    damage_description: string
  }
  evidence: {
    images: string[]
    videos: string[]
    integrity_checks: Record<string, any>[]
  }
  validation: {
    status: string
    missing_fields: string[]
    warnings: string[]
  }
  customer_confirmation: {
    confirmed: boolean
    timestamp: string | null
  }
}

export interface ProfessionalClaimDossier {
  section_1_claim_header: Record<string, any>
  section_2_policyholder_profile: Record<string, any>
  section_3_policy_and_asset_details: Record<string, any>
  section_4_incident_summary: Record<string, any>
  section_5_structured_damage_report: Record<string, any>
  section_6_evidence_inventory_and_screening: Record<string, any>
  section_7_completeness_and_validation_checklist: Record<string, any>
  section_8_customer_declaration_and_confirmation: Record<string, any>
  section_9_audit_and_system_metadata: Record<string, any>
}

export interface ReportRecord {
  report_id: string
  claim_id: string
  version: string
  dossier: ProfessionalClaimDossier
  canonical_schema: CanonicalClaimSchema
  pdf_download_url: string
  json_download_url: string
  generated_at: string
}

// ── Phase 7: Mock Insurer Integration Gateway ──

export interface InsurerSubmissionStep {
  step: string
  status: string
  detail: string
  timestamp: string
}

export interface InsurerSubmissionResponse {
  submission_id: string
  claim_id: string
  recipient: string
  recipient_display_name: string
  delivery_status: string
  insurer_claim_reference: string
  processing_status: string
  pipeline_steps: InsurerSubmissionStep[]
  mapped_payload_preview: Record<string, any>
  submitted_at: string
  disclaimer: string
}

// ── Claim Records & Vault ──

export interface ClaimCreateRequest {
  customer_id?: string
  insurance_type?: string
  policy_holder_name?: string
  policy_reference: string
  incident_location: string
  incident_date: string
  incident_time?: string
  vehicle_type: string
  vehicle_registration?: string
  damage_description: string
  drivable_status?: string
  injuries_reported?: string
  police_fir_info?: string
  transcript: string
  language?: string
  conversation_id?: string
  edited_fields?: string[]
  customer_confirmed?: boolean
}

export interface ClaimCreateResponse {
  id: string
  customer_id: string
  status: ClaimStatusType
  message: string
  is_demo: boolean
}

export interface ClaimRecord {
  id: string
  customer_id: string
  insurance_type: string
  policy_holder_name: string
  policy_reference: string
  incident_location: string
  incident_date: string
  incident_time: string
  vehicle_type: string
  vehicle_registration: string
  damage_description: string
  drivable_status: string
  injuries_reported: string
  police_fir_info: string
  transcript: string
  language: string
  status: ClaimStatusType
  customer_confirmed: boolean
  confirmed_at: string | null
  report_version: string
  insurer_submission_status: string
  is_demo: boolean
  created_at: string
  updated_at: string
}

export interface TimelineEvent {
  timestamp: string
  title: string
  description: string
  status?: string | null
}

export interface AuditLogEntry {
  log_id: string
  user_id: string
  claim_id?: string
  action: string
  details: string
  timestamp: string
}

export interface ClaimDetailResponse {
  claim: ClaimRecord
  timeline: TimelineEvent[]
  evidence: EvidenceAssetRecord[]
  reports: ReportRecord[]
  insurer_submissions: InsurerSubmissionResponse[]
  audit_logs: AuditLogEntry[]
  is_demo: boolean
}

export interface ClaimListResponse {
  claims: ClaimRecord[]
  total: number
  is_demo: boolean
}

export interface VaultSummaryResponse {
  user: UserProfile
  total_claims: number
  claims: ClaimRecord[]
  recent_audit_logs: AuditLogEntry[]
}

export interface DashboardStats {
  total_claims: number
  recent_claims: ClaimRecord[]
  is_demo: boolean
}
