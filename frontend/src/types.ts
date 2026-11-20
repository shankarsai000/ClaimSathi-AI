// Typed API contracts matching the backend Pydantic models (Phases 1–7)

export type FieldConfidence = 'high' | 'medium' | 'low' | 'missing'
export type ClaimStatusType =
  | 'draft'
  | 'pending_info'
  | 'evidence_pending'
  | 'screened'
  | 'confirmed'
  | 'report_generated'
  | 'submitted'
  | 'archived'

export interface ClaimField {
  name: string
  label: string
  value: string | null
  confidence: FieldConfidence
  is_edited: boolean
  is_verified?: boolean
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
  claimed_vehicle_type?: 'two_wheeler' | 'four_wheeler' | null
  vehicle_registration?: string | null
  damage_keywords?: string[]
  incident_description?: string | null
}

export interface EvidenceNarrationRequest {
  decision: 'PASS' | 'REVIEW' | 'REJECT' | string
  claimed_vehicle_type: string
  detected_vehicle_category?: string | null
  vehicle_category_mismatch?: boolean
  total_estimated_inr?: number
  damages?: any[]
  language?: string
}

export interface EvidenceNarrationResponse {
  spoken_narration: string
  narration_text?: string
  language: string
  decision: string
  total_estimated_inr: number
}

export interface ExtractSlotsResponse {
  transcript: string
  claimed_vehicle_type?: 'two_wheeler' | 'four_wheeler' | null
  vehicle_registration?: string | null
  damage_keywords: string[]
  incident_description: string
  detected_language: string
  reply_text: string
  fields: ClaimField[]
  missing_fields: string[]
  assistant_dialogue: string
  assistant_speech_text: string
  assistant_language: string
}

export interface ConverseTurnRequest {
  message: string
  language?: string
  known_fields?: Record<string, string | null>
  history?: Array<{ sender: 'user' | 'assistant'; text: string }>
  expected_field?: string | null
}

export interface ConverseTurnResponse {
  transcript: string
  detected_language: string
  assistant_language: string
  reply_text: string
  assistant_dialogue: string
  assistant_speech_text: string
  fields: ClaimField[]
  missing_fields: string[]
  known_fields: Record<string, string | null>
  newly_captured: Record<string, string>
  claimed_vehicle_type?: 'two_wheeler' | 'four_wheeler' | null
  vehicle_registration?: string | null
  damage_keywords: string[]
  incident_description?: string | null
  is_complete: boolean
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
  data_processing_consent: boolean
  evidence_screening_consent: boolean
  retention_policy_acknowledged: boolean
}

export interface UserProfile {
  customer_id: string
  name: string
  email: string
  phone: string
  declared_insurer: string
  consents: UserConsentInput
  total_claims: number
  created_at: string
}

export interface RegisterRequest {
  name: string
  email: string
  phone: string
  password: string
  declared_insurer?: string
  consents?: UserConsentInput
}

export interface LoginRequest {
  identifier: string
  password?: string
  otp_code?: string
  demo_quick_login?: boolean
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: UserProfile
}

// ── Phase 3 & 4: Evidence Collection & Integrity Engine ──

export type CaptureMethod = 'upload_photo' | 'upload_video' | 'live_photo' | 'guided_video'
export type DuplicateStatus = 'unique' | 'exact_duplicate' | 'visual_duplicate'

export interface CaptureSessionResponse {
  session_id: string
  claim_id: string | null
  instructions: string[]
  created_at: string
  expires_in_seconds: number
}

export interface EvidenceCheckRecord {
  check_id: string
  evidence_id: string
  claim_id: string
  sha256_hash: string
  perceptual_hash: string | null
  magic_bytes_valid: boolean
  detected_format: string
  malware_scan_status: string
  c2pa_found: boolean
  synthid_found: boolean
  provenance_result: string
  provenance_system_response: string
  provenance_details: Record<string, any>
  duplicate_status: DuplicateStatus
  duplicate_match_type: string | null
  matched_claim_reference: string | null
  matched_evidence_id: string | null
  hamming_distance: number | null
  requires_human_review: boolean
  screening_outcome_label: string
  checked_at: string
}

export interface EvidenceAssetRecord {
  evidence_id: string
  claim_id: string
  user_id: string
  label: string
  media_type: string
  capture_method: string
  capture_session_id: string | null
  original_filename: string
  detected_mime: string
  file_size_bytes: number
  width: number | null
  height: number | null
  exif_metadata: Record<string, any>
  upload_timestamp: string
  screening: EvidenceCheckRecord
}

// ── Phase 5 & 6: 9-Section Professional Claim Dossier & Layer 1 Canonical Schema ──

export interface CanonicalClaimSchema {
  claim_id: string
  customer_id: string
  insurance_type: string
  policy: Record<string, any>
  incident: Record<string, any>
  evidence: Record<string, any>
  validation: Record<string, any>
  customer_confirmation: boolean
  report_status: string
  insurer_submission_status: string
}

export interface ProfessionalClaimDossier {
  claim_id: string
  report_id: string
  report_version: string
  insurance_category: string
  status_badge: string
  section_01_customer: Record<string, any>
  section_02_policy: Record<string, any>
  section_03_incident: Record<string, any>
  section_04_statement: Record<string, any>
  section_05_evidence_inventory: Record<string, any>
  section_06_validation_review: Record<string, any>
  section_07_supporting_documents: Record<string, any>
  section_08_preparation_summary: Record<string, any>
  section_09_declaration: Record<string, any>
}

export interface ReportRecord {
  report_id: string
  claim_id: string
  user_id?: string
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
  policy_reference: string
  incident_location: string
  incident_date: string
  vehicle_type: string
  damage_description: string
  transcript: string
  customer_id?: string
  insurer_name?: string
  policy_type?: string
  people_involved?: string
  injuries_reported?: string
  detailed_statement?: string
  evidence_id?: string
  claimed_vehicle_type?: string
  verification_decision?: string
  spoof_risk?: number
  total_estimated_inr?: number
  cost_estimate?: CostEstimateReport | null
}

export interface ClaimCreateResponse {
  id: string
  claim_id?: string
  status: ClaimStatusType
  message: string
  is_demo: boolean
}

export interface ClaimRecord {
  id: string
  customer_id: string
  insurance_type: string
  policy_reference: string
  insurer_name: string
  policy_type: string
  incident_location: string
  incident_date: string
  vehicle_type: string
  damage_description: string
  people_involved: string
  injuries_reported: string
  detailed_statement: string
  transcript: string
  status: ClaimStatusType
  customer_confirmation: boolean
  report_status: string
  insurer_submission_status: string
  evidence_count_images: number
  evidence_count_videos: number
  is_demo: boolean
  created_at: string
  updated_at: string
}

export interface TimelineEvent {
  timestamp: string
  title: string
  description: string
}

export interface AuditLogEntry {
  log_id: string
  user_id: string
  claim_id?: string | null
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
  is_demo: boolean
}

export interface ClaimListResponse {
  claims: ClaimRecord[]
  total: number
  is_demo: boolean
}

export interface VaultSummaryResponse {
  user: UserProfile
  total_cases: number
  claims: ClaimRecord[]
  recent_reports: Record<string, any>[]
  audit_logs: AuditLogEntry[]
}

export interface DashboardStats {
  total_claims: number
  recent_claims: ClaimRecord[]
  is_demo: boolean
}

// ── Sprint 1.4 / 1.5: 5-Stage Evidence Intelligence & Cost Estimator ──

export interface CostEstimateLineItem {
  damage_type: string
  confidence: number
  area_ratio: number
  severity: 'Minor' | 'Moderate' | 'Severe'
  base_part_inr: number
  labor_inr: number
  Diagnostic_multiplier: number
  multiplier?: number
  subtotal_inr: number
}

export interface CostEstimateReport {
  currency: string
  estimate_status: 'APPROVED_AUTO_ESTIMATE' | 'PROVISIONAL_PENDING_REVIEW' | 'REJECTED_NO_ESTIMATE'
  overall_severity: 'None' | 'Minor' | 'Moderate' | 'Severe'
  line_items: CostEstimateLineItem[]
  total_estimated_inr: number
  total_inr: number
}

export interface YoloDetectionBox {
  class_id: number
  class_name: string
  confidence: number
  bbox: [number, number, number, number]
  area_ratio: number
}

export interface EvidenceVerificationReport {
  id: string
  filename: string
  sha256: string
  decision: 'PASS' | 'REVIEW' | 'REJECT'
  claimed_vehicle_type?: 'four_wheeler' | 'two_wheeler' | string
  detected_vehicle_category?: 'four_wheeler' | 'two_wheeler' | 'unknown' | string
  vehicle_category_mismatch?: boolean
  spoof_risk: number
  predicted_spoof_class: string
  vehicle_detected: boolean
  damage_count: number
  context_valid?: boolean
  reasons: string[]
  cost_estimate?: CostEstimateReport | null
  stage_results: {
    claimed_vehicle_type?: string
    detected_vehicle_category?: string
    vehicle_category_mismatch?: boolean
    stage1_integrity?: {
      stage1_passed: boolean
      sha256: string
      file_size_bytes: number
      detected_format?: string | null
      detected_mime?: string
      width?: number | null
      height?: number | null
      error_code?: string | null
      error_reason?: string | null
    } | null
    stage2_metadata?: {
      has_exif: boolean
      camera_make_model?: string | null
      datetime_original?: string | null
      software_tag?: string | null
      editing_software_detected: boolean
      c2pa_present: boolean
      metadata_risk_score: number
    } | null
    stage3a_vehicle?: {
      vehicle_detected: boolean
      detected_classes: string[]
      max_confidence: number
      largest_area_ratio: number
      detections: YoloDetectionBox[]
    } | null
    stage3b_damage?: {
      damage_detected: boolean
      damage_count: number
      detected_damage_types: string[]
      max_confidence: number
      detections: YoloDetectionBox[]
    } | null
    stage4_spoof?: {
      spoof_risk: number
      predicted_class: string
      probabilities: Record<string, number>
      thresholds: Record<string, number>
      device: string
    } | null
    stage5_risk?: {
      decision: 'PASS' | 'REVIEW' | 'REJECT'
      reasons: string[]
      requires_human_review: boolean
    } | null
    cost_estimate?: CostEstimateReport | null
    linked_claim?: LinkedClaim | null
  }
  linked_claim?: LinkedClaim | null
  processing_time_ms: number
  created_at: string
}

export interface LinkedClaim {
  claim_id: string
  evidence_id: string
  policy_number: string
  vehicle_registration: string
  vehicle_category: string
  verification_decision: 'PASS' | 'REVIEW' | 'REJECT'
  estimate_status?: string
  total_estimated_inr: number
  damage_count: number
  claim_status: 'APPROVED' | 'UNDER_REVIEW'
  created_at: string
}

export interface EvidenceVerificationHistoryResponse {
  total: number
  verifications: EvidenceVerificationReport[]
}
