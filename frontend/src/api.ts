import type {
  TranscriptResponse,
  VoiceTranscribeResponse,
  EvidenceNarrationRequest,
  EvidenceNarrationResponse,
  ExtractSlotsResponse,
  ConverseTurnRequest,
  ConverseTurnResponse,
  ClaimCreateRequest,
  ClaimCreateResponse,
  ClaimDetailResponse,
  ClaimListResponse,
  DashboardStats,
  HealthResponse,
  RegisterRequest,
  LoginRequest,
  AuthResponse,
  UserProfile,
  VaultSummaryResponse,
  CaptureSessionResponse,
  EvidenceAssetRecord,
  ReportRecord,
  InsurerSubmissionResponse,
  ClaimRecord,
  EvidenceVerificationReport,
  EvidenceVerificationHistoryResponse,
} from './types'

const BASE = '/api'
const TOKEN_KEY = 'claimsathi_auth_token'
const USER_KEY = 'claimsathi_user_profile'

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function getStoredUser(): UserProfile | null {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setStoredAuth(token: string, user: UserProfile) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
  window.dispatchEvent(new Event('claimsathi-auth-change'))
}

export function clearStoredAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  window.dispatchEvent(new Event('claimsathi-auth-change'))
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const token = getStoredToken()
  const authHeaders: Record<string, string> = token
    ? { Authorization: `Bearer ${token}` }
    : {}

  const resp = await fetch(`${BASE}${url}`, {
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders,
      ...(options?.headers || {}),
    },
    ...options,
  })
  if (!resp.ok) {
    if (resp.status === 401 && !url.includes('/auth/login') && !url.includes('/auth/register')) {
      clearStoredAuth()
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('claimsathi-session-expired'))
      }
    }
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || `Request failed: ${resp.status}`)
  }
  return resp.json()
}

export const api = {
  health: () => request<HealthResponse>('/health'),

  // ── Phase 1: Customer Registration, Login, OTP & Vault ──
  register: async (data: RegisterRequest): Promise<AuthResponse> => {
    const res = await request<AuthResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    })
    setStoredAuth(res.access_token, res.user)
    return res
  },

  requestOtp: (identifier: string) =>
    request<{ identifier: string; otp_sent: boolean; demo_otp_code: string; message: string }>(
      '/auth/request-otp',
      {
        method: 'POST',
        body: JSON.stringify({ identifier }),
      },
    ),

  login: async (data: LoginRequest): Promise<AuthResponse> => {
    const res = await request<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
    })
    setStoredAuth(res.access_token, res.user)
    return res
  },

  getMe: () => request<UserProfile>('/auth/me'),

  getVault: (customerId?: string) =>
    request<VaultSummaryResponse>(
      customerId ? `/auth/vault?customer_id=${encodeURIComponent(customerId)}` : '/auth/vault',
    ),

  logout: async (): Promise<void> => {
    try {
      await request('/auth/logout', { method: 'POST' })
    } catch {
      // Ignore network errors on logout
    } finally {
      clearStoredAuth()
    }
  },

  // ── Phase 2 & 3: Live Gnani Prisma STT & Stateful Conversation ──
  transcribeVoice: async (
    audioBlob: Blob | File,
    filename: string = 'recording.wav',
    demo: boolean = false,
    languageCode?: string,
    knownFields?: Record<string, string | null>,
    history?: Array<{ sender: 'user' | 'assistant'; text: string }>,
    expectedField?: string | null,
  ): Promise<VoiceTranscribeResponse> => {
    const formData = new FormData()
    formData.append('audio_file', audioBlob, filename)
    formData.append('demo', demo ? 'true' : 'false')
    if (languageCode) {
      formData.append('language_code', languageCode)
    }
    if (knownFields) {
      formData.append('known_fields_json', JSON.stringify(knownFields))
    }
    if (history && history.length > 0) {
      formData.append('history_json', JSON.stringify(history))
    }
    if (expectedField) {
      formData.append('expected_field', expectedField)
    }

    const resp = await fetch(`${BASE}/voice/transcribe`, {
      method: 'POST',
      body: formData,
    })

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }))
      throw new Error(err.detail || `Voice transcription failed with status ${resp.status}`)
    }
    return resp.json()
  },

  converseClaimTurn: async (
    req: ConverseTurnRequest,
  ): Promise<ConverseTurnResponse> => {
    return request<ConverseTurnResponse>('/v1/voice/converse', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  },

  synthesizeSpeech: async (
    text: string,
    options?: { language?: string; voice?: string; speed?: number; demo?: boolean },
  ): Promise<Blob> => {
    const resp = await fetch(`${BASE}/voice/speak`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text,
        language: options?.language,
        voice: options?.voice,
        speed: options?.speed ?? 1.0,
        demo: options?.demo ?? false,
      }),
    })

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }))
      throw new Error(err.detail || `Speech synthesis failed with status ${resp.status}`)
    }
    return resp.blob()
  },

  extractVoiceSlots: async (
    text: string,
    language: string = 'indic-auto',
  ): Promise<ExtractSlotsResponse> => {
    return request<ExtractSlotsResponse>('/v1/voice/extract-slots', {
      method: 'POST',
      body: JSON.stringify({ text, language }),
    })
  },

  narrateEvidence: async (
    req: EvidenceNarrationRequest,
  ): Promise<EvidenceNarrationResponse> => {
    return request<EvidenceNarrationResponse>('/v1/voice/narrate-evidence', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  },

  transcribe: (language = 'hi-en') =>
    request<TranscriptResponse>('/claims/transcribe', {
      method: 'POST',
      body: JSON.stringify({ use_mock: true, language }),
    }),

  extractTextIntake: (text: string, language = 'en-IN') =>
    request<{
      transcript: string
      detected_language: string
      fields: any[]
      missing_fields: string[]
      assistant_dialogue: string
      assistant_speech_text: string
      assistant_language: string
      claimed_vehicle_type?: 'two_wheeler' | 'four_wheeler' | null
      vehicle_registration?: string | null
      damage_keywords?: string[]
      incident_description?: string | null
    }>('/claims/extract-text', {
      method: 'POST',
      body: JSON.stringify({ text, language }),
    }),

  validateFieldAnswer: (targetField: string, answer: string, language = 'en-IN') =>
    request<{
      is_valid_for_target: boolean
      english_value: string | null
      routed_fields: Record<string, string>
      error_prompt: string | null
      detected_language: string
    }>('/claims/validate-field-answer', {
      method: 'POST',
      body: JSON.stringify({ target_field: targetField, answer, language }),
    }),

  // ── Phase 3 & 4: Evidence Collection & Integrity Engine ──
  startCaptureSession: (claimId: string, captureType = 'guided_video_and_photo') =>
    request<CaptureSessionResponse>('/evidence/capture-session', {
      method: 'POST',
      body: JSON.stringify({ claim_id: claimId, capture_type: captureType }),
    }),

  uploadEvidence: async (
    claimId: string,
    file: Blob | File,
    filename: string,
    captureMethod: string = 'upload_photo',
    captureSessionId?: string,
  ): Promise<EvidenceAssetRecord> => {
    const token = getStoredToken()
    const formData = new FormData()
    formData.append('file', file, filename)
    formData.append('capture_method', captureMethod)
    if (captureSessionId) {
      formData.append('capture_session_id', captureSessionId)
    }

    const headers: Record<string, string> = token
      ? { Authorization: `Bearer ${token}` }
      : {}

    const resp = await fetch(`${BASE}/evidence/${encodeURIComponent(claimId)}/upload`, {
      method: 'POST',
      headers,
      body: formData,
    })

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }))
      throw new Error(err.detail || `Evidence upload failed with status ${resp.status}`)
    }
    return resp.json()
  },

  listClaimEvidence: (claimId: string) =>
    request<EvidenceAssetRecord[]>(`/evidence/${encodeURIComponent(claimId)}`),

  createMediaTicket: (claimId: string) =>
    request<{ ticket: string; claim_id: string; expires_in: number }>(
      `/claims/${encodeURIComponent(claimId)}/media-ticket`,
      { method: 'POST' }
    ),

  getEvidenceFileUrl: (claimId: string, evidenceId: string, ticket?: string) => {
    if (ticket) {
      return `${BASE}/evidence/${encodeURIComponent(claimId)}/file/${encodeURIComponent(evidenceId)}?ticket=${encodeURIComponent(ticket)}`
    }
    const token = getStoredToken()
    const tokenParam = token ? `?token=${encodeURIComponent(token)}` : ''
    return `${BASE}/evidence/${encodeURIComponent(claimId)}/file/${encodeURIComponent(evidenceId)}${tokenParam}`
  },

  downloadReportPdf: async (claimId: string, version?: string): Promise<Blob> => {
    const token = getStoredToken()
    const url = `${BASE}/claims/${encodeURIComponent(claimId)}/report/pdf${version ? `?version=${encodeURIComponent(version)}` : ''}`
    const resp = await fetch(url, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!resp.ok) {
      throw new Error(`PDF download failed with status ${resp.status}`)
    }
    return resp.blob()
  },

  downloadReportJson: async (claimId: string, version?: string): Promise<any> => {
    const token = getStoredToken()
    const url = `${BASE}/claims/${encodeURIComponent(claimId)}/report/json${version ? `?version=${encodeURIComponent(version)}` : ''}`
    const resp = await fetch(url, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!resp.ok) {
      throw new Error(`JSON download failed with status ${resp.status}`)
    }
    return resp.json()
  },

  // ── Phase 5, 6 & 7: Claims, Confirmation, 9-Section Dossier, PDF & Mock Insurer Gateway ──
  createClaim: (data: ClaimCreateRequest) =>
    request<ClaimCreateResponse>('/claims/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateAndConfirmClaim: (claimId: string, updates: Record<string, any>) =>
    request<ClaimRecord>(`/claims/${encodeURIComponent(claimId)}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    }),

  generateReport: (claimId: string) =>
    request<ReportRecord>(`/claims/${encodeURIComponent(claimId)}/report`, {
      method: 'POST',
    }),

  getLatestReport: (claimId: string) =>
    request<ReportRecord>(`/claims/${encodeURIComponent(claimId)}/report`),

  getReportPdfUrl: (claimId: string, version?: string) => {
    const token = getStoredToken()
    const params = new URLSearchParams()
    if (version) params.set('version', version)
    if (token) params.set('token', token)
    const qs = params.toString()
    return `${BASE}/claims/${encodeURIComponent(claimId)}/report/pdf${qs ? `?${qs}` : ''}`
  },

  getReportLocalizedUrl: (claimId: string, lang: string = 'en', download: boolean = false) => {
    const token = getStoredToken()
    const params = new URLSearchParams()
    params.set('lang', lang)
    if (download) params.set('download', 'true')
    if (token) params.set('token', token)
    return `${BASE}/claims/${encodeURIComponent(claimId)}/report/localized?${params.toString()}`
  },

  getReportJsonUrl: (claimId: string, version?: string) => {
    const token = getStoredToken()
    const params = new URLSearchParams()
    if (version) params.set('version', version)
    if (token) params.set('token', token)
    const qs = params.toString()
    return `${BASE}/claims/${encodeURIComponent(claimId)}/report/json${qs ? `?${qs}` : ''}`
  },

  submitToInsurer: (claimId: string, recipient = 'DEMO_INSURER_A') =>
    request<InsurerSubmissionResponse>(`/claims/${encodeURIComponent(claimId)}/submit-insurer`, {
      method: 'POST',
      body: JSON.stringify({
        recipient,
        submission_channel: 'Official insurer API',
        customer_authorized: true,
      }),
    }),

  getClaim: (id: string) => request<ClaimDetailResponse>(`/claims/${encodeURIComponent(id)}`),

  listClaims: (customerId?: string) =>
    request<ClaimListResponse>(
      customerId ? `/claims/?customer_id=${encodeURIComponent(customerId)}` : '/claims/',
    ),

  getStats: () => request<DashboardStats>('/claims/stats'),

  // ── Sprint 1.4 / 1.5 / 1.6: 5-Stage Evidence Verification & INR Cost Estimate ──
  verifyEvidenceV1: async (
    file: File,
    claimedVehicleType: 'four_wheeler' | 'two_wheeler' = 'four_wheeler',
  ): Promise<EvidenceVerificationReport> => {
    const token = getStoredToken()
    const formData = new FormData()
    formData.append('file', file)
    formData.append('claimed_vehicle_type', claimedVehicleType)
    const resp = await fetch(`${BASE}/v1/evidence/verify`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }))
      throw new Error(err.detail || `Verification failed: ${resp.status}`)
    }
    return resp.json()
  },

  getEvidenceHistoryV1: (limit: number = 25) =>
    request<EvidenceVerificationHistoryResponse>(`/v1/evidence/history?limit=${limit}`),

  getEvidenceVerificationByIdV1: (evidenceId: string) =>
    request<EvidenceVerificationReport>(`/v1/evidence/${encodeURIComponent(evidenceId)}`),

  // ── Sprint 1.7: Reviewer Decision Override & Official Claim Creation ──
  overrideEvidenceDecision: (
    evidenceId: string,
    newDecision: 'PASS' | 'REJECT',
    reviewerNote: string = 'Manual adjuster review completed.',
  ) =>
    request<EvidenceVerificationReport>(`/v1/evidence/${encodeURIComponent(evidenceId)}/override`, {
      method: 'POST',
      body: JSON.stringify({
        new_decision: newDecision,
        reviewer_note: reviewerNote,
      }),
    }),

  createClaimFromEvidence: (
    evidenceId: string,
    data: {
      policy_number?: string
      vehicle_registration?: string
      incident_description?: string
    } = {},
  ) =>
    request<EvidenceVerificationReport>(
      `/v1/evidence/${encodeURIComponent(evidenceId)}/create-claim`,
      {
        method: 'POST',
        body: JSON.stringify({
          policy_number: data.policy_number || 'POL-IND-2026-8841',
          vehicle_registration: data.vehicle_registration || 'KA-01-MJ-2026',
          incident_description:
            data.incident_description || 'Automated AI damage assessment submission.',
        }),
      },
    ),
}
