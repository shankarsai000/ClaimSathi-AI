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

export interface ConversationalReasoningTrace {
  detected_emotion: string
  empathy_cue: string
  safety_check_status: string
  inferred_cause?: string | null
  drivability_assessment: string
  plausibility_note: string
  causal_question_asked?: string | null
  thought_process: string
  speech_rate: number
  speech_pitch: number
  llm_provider?: string
  detected_intent?: string
  applied_gnani_tags?: string[]
}

export type MotorLossType =
  | 'own_damage_accident'
  | 'theft'
  | 'fire_natural_calamity'
  | 'third_party'

export type MotorUsageType = 'private_social_domestic' | 'commercial_hire_reward'
export type MotorDriverRelationship = 'owner' | 'paid_driver' | 'relative_or_friend'
export type MotorLicenseClass = 'MCWG' | 'MCWOG' | 'LMV' | 'HMV' | 'other'
export type ClaimSettlementMode = 'cashless' | 'reimbursement'

export interface VoiceIntakeMotorSlots {
  claimed_registration?: string | null
  vehicle_make_model?: string | null
  loss_type?: MotorLossType | null
  incident_time?: string | null
  driver_was_owner?: boolean | null
  driver_name?: string | null
  driver_relationship?: MotorDriverRelationship | null
  vehicle_usage_type?: MotorUsageType | null
  pillion_rider_present?: boolean | null
  occupants_count?: number | null
  injury_or_third_party_flag?: boolean | null
  police_fir_lodged_flag?: boolean | null
  inspection_location?: string | null
}

export interface MotorClaimFormDetails {
  // Group B1: Claimant & Policy Identification
  claimant_name?: string | null
  registered_mobile?: string | null
  claimant_email?: string | null
  residential_address?: string | null
  pincode?: string | null
  other_insurance_exists?: boolean | null
  other_insurance_details?: string | null

  // Group B2: Incident & Vehicle Usage Details
  loss_type?: MotorLossType | null
  incident_time?: string | null
  vehicle_usage_type?: MotorUsageType | null
  pillion_rider_present?: boolean | null
  occupants_count?: number | null
  vehicle_was_parked_unattended?: boolean | null
  injury_or_third_party_flag?: boolean | null
  police_fir_lodged_flag?: boolean | null

  // Group B3: Driver Details at Time of Accident
  driver_was_owner?: boolean | null
  driver_name?: string | null
  driver_age?: number | null
  driver_address?: string | null
  driver_relationship?: MotorDriverRelationship | null
  driver_license_number?: string | null
  driver_license_expiry?: string | null
  driver_license_class?: MotorLicenseClass | null
  driver_issuing_rto?: string | null
  driver_under_intoxication?: boolean | null
  driver_injured?: boolean | null
  driver_license_mismatch_warning?: string | null

  // Group B4: Inspection, Settlement Mode & Workshop Details
  claim_settlement_mode?: ClaimSettlementMode | null
  inspection_location?: string | null
  preferred_inspection_datetime?: string | null
  workshop_name?: string | null
  workshop_address?: string | null
  workshop_contact?: string | null
  approx_estimated_repair_cost_inr?: number | null

  // Group B5: Legal Declarations & DPDP Consent
  dpdp_consent_granted?: boolean | null
  dpdp_consent_timestamp?: string | null
  truthfulness_declaration_accepted?: boolean | null
  declaration_place?: string | null
  declaration_date?: string | null
  insured_digital_signature?: string | null

  // Group C Trigger 1: Reimbursement Bank / NEFT Details
  bank_account_holder_name?: string | null
  bank_account_number?: string | null
  bank_ifsc_code?: string | null
  bank_branch_name?: string | null

  // Group C Trigger 2: FIR / Police Report Details
  fir_or_gd_number?: string | null
  police_station_name?: string | null
  fir_report_date?: string | null
  fir_complainant_name?: string | null

  // Group C Trigger 3: Theft-Specific Details
  non_traceable_report_status?: 'pending' | 'obtained' | 'not_applicable' | null
  all_original_keys_available?: boolean | null
  financier_hypothecated?: boolean | null
  financier_name?: string | null
  stolen_accessories_details?: string | null

  // Group C Trigger 4: Injury / Third-Party Details
  third_party_loss_type?: 'injury' | 'death' | 'property_damage' | 'driver_or_occupant_only' | null
  third_party_injured_count?: number | null
  hospital_and_treatment_details?: string | null
  third_party_vehicle_reg?: string | null
  third_party_policy_details?: string | null
  third_party_damage_summary?: string | null
  witness_name?: string | null
  witness_contact?: string | null

  // Group C Trigger 5: Fire / Natural Calamity
  fire_brigade_report_number?: string | null
}

export interface InsurerPolicyMaster {
  claim_reference_number?: string | null
  policy_start_date?: string | null
  policy_end_date?: string | null
  idv_inr?: number | null
  ncb_percent?: number | null
  coverage_type?: string | null
  active_addons: string[]
  compulsory_excess_inr?: number | null
  voluntary_excess_inr?: number | null
  hypothecation_financier?: string | null
}

export interface ExternalRegistryChecks {
  engine_number?: string | null
  chassis_vin_number?: string | null
  vahan_status?: string | null
  sarathi_dl_status?: string | null
  iib_cross_claim_status?: string | null
  edar_sync_status?: string | null
}

export interface SurveyorAssessment {
  surveyor_name?: string | null
  surveyor_irdai_license_no?: string | null
  odometer_reading_km?: number | null
  damage_freshness_classification: 'fresh' | 'pre_existing' | 'mixed' | 'pending'
  imt_gr9_depreciation_inr?: number | null
  salvage_value_inr?: number | null
  constructive_total_loss?: boolean | null
  net_assessed_payable_inr?: number | null
}

export interface MotorAdjusterPlaceholders {
  insurer_policy_master: InsurerPolicyMaster
  external_registry_checks: ExternalRegistryChecks
  surveyor_assessment: SurveyorAssessment
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
  vehicle_make_model?: string | null
  vehicle_registration?: string | null
  claimed_registration?: string | null
  motor_slots?: VoiceIntakeMotorSlots | null
  damage_keywords?: string[]
  incident_description?: string | null
  reasoning_trace?: ConversationalReasoningTrace | null
  no_speech_detected?: boolean
}

export interface EvidenceNarrationRequest {
  decision: 'PASS' | 'REVIEW' | 'REJECT' | string
  claimed_vehicle_type: string
  detected_vehicle_category?: string | null
  vehicle_category_mismatch?: boolean
  total_estimated_inr?: number
  damages?: any[]
  language?: string
  reasons?: string[]
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
  vehicle_make_model?: string | null
  vehicle_registration?: string | null
  claimed_registration?: string | null
  motor_slots?: VoiceIntakeMotorSlots | null
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
  known_motor_slots?: Record<string, any>
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
  vehicle_make_model?: string | null
  vehicle_registration?: string | null
  claimed_registration?: string | null
  motor_slots?: VoiceIntakeMotorSlots | null
  damage_keywords: string[]
  incident_description?: string | null
  is_complete: boolean
  no_speech_detected?: boolean
  reasoning_trace?: ConversationalReasoningTrace | null
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
  user_declared_fields?: Record<string, any>
  insurer_and_registry_fields?: Record<string, any>
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
  claimed_registration?: string
  incident_location: string
  incident_date: string
  vehicle_type: string
  vehicle_make_model?: string
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
  motor_claim_form?: MotorClaimFormDetails
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
  claimed_registration?: string | null
  insurer_name: string
  policy_type: string
  incident_location: string
  incident_date: string
  vehicle_type: string
  vehicle_make_model?: string | null
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
  motor_claim_form?: MotorClaimFormDetails
  insurer_adjuster_data?: MotorAdjusterPlaceholders
  masked_pii_summary?: Record<string, string | null>
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
  estimate_band_min_inr?: number
  estimate_band_max_inr?: number
  vehicle_make_model?: string
  make_model_tier?: string
  tier_multiplier?: number
  bfsi_regulatory_disclaimer?: string
}

export interface VehicleIdentityBinding {
  claimed_registration?: string | null
  detected_plate_candidate?: string | null
  detected_candidates?: string[]
  plate_match_status: string
  identity_bound: boolean
  requires_identity_review: boolean
  identity_note: string
  mandatory_capture_prompts?: string[]
}

export interface WhatsappHandoffResponse {
  session_id: string
  claim_id: string | null
  handoff_url: string
  masked_phone: string
  masked_registration: string
  raw_whatsapp_media_blocked: boolean
  instructions: string[]
  whatsapp_template_preview: string
  expires_in_seconds: number
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
  vehicle_identity?: VehicleIdentityBinding | null
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
      provenance_advisory_only?: boolean
      provenance_disclaimer?: string
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

export interface GovernanceMetricsResponse {
  total_verifications: number
  ai_flagged_count: number
  false_positive_overrides: number
  false_negative_overrides: number
  false_positive_rate: number
  false_negative_rate: number
  override_reason_breakdown: Record<string, number>
  irdai_governance_compliant: boolean
}
