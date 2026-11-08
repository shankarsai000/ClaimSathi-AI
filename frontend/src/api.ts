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
  UserConsentInput,
  CaptureSessionResponse,
  EvidenceAssetRecord,
  ReportRecord,
  InsurerSubmissionResponse,
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

  // ── Phase 1: Customer Registration, Login & Vault ──
  register: async (data: RegisterRequest): Promise<AuthResponse> => {
    const res = await request<AuthResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    })
    setStoredAuth(res.access_token, res.user)
    return res
  },

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

  updateConsent: (consents: UserConsentInput) =>
    request<{ status: string; customer_id: string; consents: UserConsentInput }>('/auth/consent', {
      method: 'POST',
      body: JSON.stringify(consents),
    }),

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

  // ── Phase 4: Evidence Collection & Integrity Engine ──
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
    request<{ claim_id: string; total: number; assets: EvidenceAssetRecord[] }>(
      `/evidence/${encodeURIComponent(claimId)}`,
    ),

  getEvidenceFileUrl: (assetId: string) => `${BASE}/evidence/file/${encodeURIComponent(assetId)}`,

  // ── Phase 5, 6 & 7: Claims, Confirmation, 9-Section Dossier, PDF & Mock Insurer Gateway ──
  createClaim: (data: ClaimCreateRequest) =>
    request<ClaimCreateResponse>('/claims/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  confirmClaim: (
    claimId: string,
    data: {
      confirmed?: boolean
      edited_fields?: Record<string, string>
      drivable_status?: string
      injuries_reported?: string
      police_fir_info?: string
      vehicle_registration?: string
      incident_time?: string
    },
  ) =>
    request<{ status: string; claim: any }>(`/claims/${encodeURIComponent(claimId)}/confirm`, {
      method: 'POST',
      body: JSON.stringify({ confirmed: true, ...data }),
    }),

  generateReport: (claimId: string) =>
    request<ReportRecord>(`/claims/${encodeURIComponent(claimId)}/report`, {
      method: 'POST',
    }),

  getLatestReport: (claimId: string) =>
    request<ReportRecord>(`/claims/${encodeURIComponent(claimId)}/report`),

  getReportPdfUrl: (claimId: string, version?: string) =>
    `${BASE}/claims/${encodeURIComponent(claimId)}/report/pdf${version ? `?version=${encodeURIComponent(version)}` : ''}`,

  getReportJsonUrl: (claimId: string, version?: string) =>
    `${BASE}/claims/${encodeURIComponent(claimId)}/report/json${version ? `?version=${encodeURIComponent(version)}` : ''}`,

  submitToInsurer: (claimId: string, recipient = 'DEMO_INSURER_A') =>
    request<InsurerSubmissionResponse>(`/claims/${encodeURIComponent(claimId)}/submit-insurer`, {
      method: 'POST',
      body: JSON.stringify({
        recipient,
        submission_channel: 'Official insurer API',
        include_canonical_json: true,
        include_pdf_dossier: true,
      }),
    }),

  getClaim: (id: string) => request<ClaimDetailResponse>(`/claims/${encodeURIComponent(id)}`),

  listClaims: (customerId?: string) =>
    request<ClaimListResponse>(
      customerId ? `/claims/?customer_id=${encodeURIComponent(customerId)}` : '/claims/',
    ),

  getStats: () => request<DashboardStats>('/claims/stats'),
}
