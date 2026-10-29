// Typed API contracts matching the backend Pydantic models (Phase 2)

export type FieldConfidence = 'high' | 'medium' | 'low' | 'missing'
export type ClaimStatusType = 'draft' | 'pending_info' | 'confirmed' | 'submitted'

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

export interface ClaimCreateRequest {
  policy_reference: string
  incident_location: string
  incident_date: string
  vehicle_type: string
  damage_description: string
  transcript: string
}

export interface ClaimCreateResponse {
  id: string
  status: ClaimStatusType
  message: string
  is_demo: boolean
}

export interface ClaimRecord {
  id: string
  policy_reference: string
  incident_location: string
  incident_date: string
  vehicle_type: string
  damage_description: string
  transcript: string
  status: ClaimStatusType
  is_demo: boolean
  created_at: string
  updated_at: string
}

export interface TimelineEvent {
  timestamp: string
  title: string
  description: string
}

export interface ClaimDetailResponse {
  claim: ClaimRecord
  timeline: TimelineEvent[]
  is_demo: boolean
}

export interface ClaimListResponse {
  claims: ClaimRecord[]
  total: number
  is_demo: boolean
}

export interface DashboardStats {
  total_claims: number
  recent_claims: ClaimRecord[]
  is_demo: boolean
}
