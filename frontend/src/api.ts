import type {
  TranscriptResponse,
  VoiceTranscribeResponse,
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

  // ── Phase 2 & 3: Live Gnani Prisma STT & Timbre TTS ──
  transcribeVoice: async (
    audioBlob: Blob | File,
    filename: string = 'recording.wav',
    demo: boolean = false,
    languageCode?: string,
  ): Promise<VoiceTranscribeResponse> => {
    const formData = new FormData()
    formData.append('audio_file', audioBlob, filename)
    formData.append('demo', demo ? 'true' : 'false')
    if (languageCode) {
      formData.append('language_code', languageCode)
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

  getEvidenceFileUrl: (claimId: string, evidenceId: string) =>
    `${BASE}/evidence/${encodeURIComponent(claimId)}/file/${encodeURIComponent(evidenceId)}`,

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

  getReportPdfUrl: (claimId: string, version?: string) =>
    `${BASE}/claims/${encodeURIComponent(claimId)}/report/pdf${version ? `?version=${encodeURIComponent(version)}` : ''}`,

  getReportLocalizedUrl: (claimId: string, lang: string = 'en', download: boolean = false) =>
    `${BASE}/claims/${encodeURIComponent(claimId)}/report/localized?lang=${encodeURIComponent(lang)}${download ? '&download=true' : ''}`,

  getReportJsonUrl: (claimId: string, version?: string) =>
    `${BASE}/claims/${encodeURIComponent(claimId)}/report/json${version ? `?version=${encodeURIComponent(version)}` : ''}`,

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
}
