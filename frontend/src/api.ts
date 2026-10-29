import type {
  TranscriptResponse,
  VoiceTranscribeResponse,
  ClaimCreateRequest,
  ClaimCreateResponse,
  ClaimDetailResponse,
  ClaimListResponse,
  DashboardStats,
  HealthResponse,
} from './types'

const BASE = '/api'

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...(options?.headers || {}) },
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

  // Phase 2: Live Gnani Prisma STT (or explicit demo mode)
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

  // Phase 2: Live Gnani Timbre TTS (or explicit demo mode)
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

  // Legacy Phase 1 mock transcribe endpoint for backwards compatibility
  transcribe: (language = 'hi-en') =>
    request<TranscriptResponse>('/claims/transcribe', {
      method: 'POST',
      body: JSON.stringify({ use_mock: true, language }),
    }),

  createClaim: (data: ClaimCreateRequest) =>
    request<ClaimCreateResponse>('/claims/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getClaim: (id: string) =>
    request<ClaimDetailResponse>(`/claims/${id}`),

  listClaims: () =>
    request<ClaimListResponse>('/claims/'),

  getStats: () =>
    request<DashboardStats>('/claims/stats'),
}
