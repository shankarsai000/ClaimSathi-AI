import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, getStoredUser } from '../api'
import { useAppSettings } from '../i18n'
import type {
  ClaimField,
  VoiceTranscribeResponse,
  ConversationalReasoningTrace,
  CaptureSessionResponse,
  EvidenceAssetRecord,
  EvidenceVerificationReport,
  WhatsappHandoffResponse,
  YoloDetectionBox,
  VoiceIntakeMotorSlots,
  MotorClaimFormDetails,
  MotorLossType,
  MotorUsageType,
  MotorDriverRelationship,
  MotorLicenseClass,
  ClaimSettlementMode,
} from '../types'
import ConfidenceBadge from '../components/ConfidenceBadge'
import ProviderBadge from '../components/ProviderBadge'
import Spinner from '../components/Spinner'
import { WavRecorder, type VadState } from '../utils/wavRecorder'
import { playAudioBlob, stopAudio } from '../utils/audioPlayer'
import {
  Mic,
  Square,
  Upload,
  Volume2,
  VolumeX,
  ChevronRight,
  CheckCircle,
  AlertTriangle,
  Edit3,
  Send,
  Bot,
  User,
  Radio,
  ShieldCheck,
  Check,
  Camera,
  Video,
  Fingerprint,
  FileCheck,
  Sparkles,
  Copy,
  RefreshCw,
  RotateCcw,
  Car,
  Bike,
  IndianRupee,
  XCircle,
  ChevronDown,
} from 'lucide-react'

interface MessageTurn {
  id: string
  sender: 'assistant' | 'user'
  text: string
  audioText?: string
  language?: string
  audioDuration?: number
  latencyMs?: number
  timestamp: string
  isStreaming?: boolean
  reasoningTrace?: ConversationalReasoningTrace | null
}

const INDIAN_LANGUAGES = [
  { code: 'indic-auto', label: '🌐 Auto-Detect All 10+ Languages (Telugu, Kannada, Hindi, etc.)' },
  { code: 'te-IN', label: '🇮🇳 Telugu / Tenglish (te-IN)' },
  { code: 'kn-IN', label: '🇮🇳 Kannada / Kanglish (kn-IN)' },
  { code: 'hi-IN', label: '🇮🇳 Hindi / Hinglish (hi-IN)' },
  { code: 'en-IN', label: '🇮🇳 Indian English (en-IN)' },
  { code: 'ta-IN', label: '🇮🇳 Tamil / Tanglish (ta-IN)' },
  { code: 'mr-IN', label: '🇮🇳 Marathi (mr-IN)' },
  { code: 'bn-IN', label: '🇮🇳 Bengali (bn-IN)' },
  { code: 'gu-IN', label: '🇮🇳 Gujarati (gu-IN)' },
  { code: 'ml-IN', label: '🇮🇳 Malayalam (ml-IN)' },
  { code: 'pa-IN', label: '🇮🇳 Punjabi (pa-IN)' },
  { code: 'ur-IN', label: '🇮🇳 Urdu (ur-IN)' },
]

const CODE_MIXED_LANGUAGE_PILLS = [
  { key: 'auto', code: 'indic-auto', label: 'Auto / Hinglish' },
  { key: 'hinglish', code: 'hi-Latn', label: 'Hinglish' },
  { key: 'kanglish', code: 'kn-Latn', label: 'Kanglish' },
  { key: 'english', code: 'en-IN', label: 'English (IN)' },
  { key: 'hindi', code: 'hi-IN', label: 'हिंदी' },
  { key: 'kannada', code: 'kn-IN', label: 'ಕನ್ನಡ' },
  { key: 'tamil', code: 'ta-IN', label: 'தமிழ்' },
  { key: 'telugu', code: 'te-IN', label: 'తెలుగు' },
]

function formatCategoryLabel(cat?: string) {
  if (!cat) return 'Unknown'
  if (cat === 'two_wheeler') return 'Two-Wheeler (Bike)'
  if (cat === 'four_wheeler') return 'Four-Wheeler (Car)'
  return cat
}

function formatInr(amount: number) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount)
}

export default function NewClaim() {
  const navigate = useNavigate()
  const { t } = useAppSettings()

  // Wizard Step: 1 = Conversation, 2 = Evidence & Live Camera, 3 = Customer Review & Declaration
  const [wizardStep, setWizardStep] = useState<1 | 2 | 3>(1)
  const [activeClaimId, setActiveClaimId] = useState<string | null>(null)

  // Claim fields & conversational state
  const [fields, setFields] = useState<ClaimField[]>([
    { name: 'policy_reference', label: 'Policy / Vehicle Number', value: null, confidence: 'missing', is_edited: false, follow_up_question: null },
    { name: 'vehicle_type', label: 'Vehicle Type', value: null, confidence: 'missing', is_edited: false, follow_up_question: null },
    { name: 'incident_location', label: 'Incident Location', value: null, confidence: 'missing', is_edited: false, follow_up_question: null },
    { name: 'incident_date', label: 'Incident Date', value: null, confidence: 'missing', is_edited: false, follow_up_question: null },
    { name: 'damage_description', label: 'Damage Description', value: null, confidence: 'missing', is_edited: false, follow_up_question: null },
  ])
  const [missingFields, setMissingFields] = useState<string[]>([])
  const [transcript, setTranscript] = useState('')
  const [activeMissingIndex, setActiveMissingIndex] = useState(0)
  const [textIntakeInput, setTextIntakeInput] = useState('')

  // Supplemental & Formal Motor Claim Fields (Groups A, B, C — pre-filled from profile & voice)
  const [vehicleRegistration, setVehicleRegistration] = useState('')
  const [incidentTime, setIncidentTime] = useState('')
  const [drivableStatus, setDrivableStatus] = useState('')
  const [injuriesReported, setInjuriesReported] = useState('No injuries reported')
  const [policeFirInfo, setPoliceFirInfo] = useState('Not filed')
  const [declarationChecked, setDeclarationChecked] = useState(true)
  const [motorSlots, setMotorSlots] = useState<VoiceIntakeMotorSlots>({})
  const [openAccordion, setOpenAccordion] = useState<string>('claimant')
  const [motorForm, setMotorForm] = useState<MotorClaimFormDetails>(() => {
    const u = getStoredUser()
    const todayIso = new Date().toISOString().slice(0, 10)
    return {
      claimant_name: u?.name || '',
      registered_mobile: u?.phone || '',
      claimant_email: u?.email || '',
      residential_address: '',
      pincode: '',
      other_insurance_exists: false,
      other_insurance_details: '',
      loss_type: 'own_damage_accident',
      incident_time: '',
      vehicle_usage_type: 'private_social_domestic',
      pillion_rider_present: false,
      occupants_count: 1,
      vehicle_was_parked_unattended: false,
      injury_or_third_party_flag: false,
      police_fir_lodged_flag: false,
      driver_was_owner: true,
      driver_name: u?.name || '',
      driver_age: undefined,
      driver_address: '',
      driver_relationship: 'owner',
      driver_license_number: '',
      driver_license_expiry: '',
      driver_license_class: undefined,
      driver_issuing_rto: '',
      driver_under_intoxication: false,
      driver_injured: false,
      claim_settlement_mode: 'cashless',
      inspection_location: '',
      preferred_inspection_datetime: '',
      workshop_name: '',
      workshop_address: '',
      workshop_contact: '',
      approx_estimated_repair_cost_inr: undefined,
      dpdp_consent_granted: false,
      dpdp_consent_timestamp: '',
      truthfulness_declaration_accepted: true,
      declaration_place: '',
      declaration_date: todayIso,
      insured_digital_signature: u?.name || '',
      bank_account_holder_name: u?.name || '',
      bank_account_number: '',
      bank_ifsc_code: '',
      bank_branch_name: '',
      fir_or_gd_number: '',
      police_station_name: '',
      fir_report_date: '',
      fir_complainant_name: u?.name || '',
      non_traceable_report_status: 'pending',
      all_original_keys_available: true,
      financier_hypothecated: false,
      financier_name: '',
      stolen_accessories_details: '',
      third_party_loss_type: 'injury',
      third_party_injured_count: 0,
      hospital_and_treatment_details: '',
      third_party_vehicle_reg: '',
      third_party_policy_details: '',
      third_party_damage_summary: '',
      witness_name: '',
      witness_contact: '',
      fire_brigade_report_number: '',
    }
  })

  const updateMotorForm = (patch: Partial<MotorClaimFormDetails>) => {
    setMotorForm((prev) => {
      const next = { ...prev, ...patch }
      if (next.driver_was_owner) {
        if ('claimant_name' in patch || patch.driver_was_owner === true) {
          next.driver_name = next.claimant_name || next.driver_name || ''
        }
        if ('residential_address' in patch || patch.driver_was_owner === true) {
          next.driver_address = next.residential_address || next.driver_address || ''
        }
        next.driver_relationship = 'owner'
      }
      return next
    })
  }

  // Conversation turns history
  const [messages, setMessages] = useState<MessageTurn[]>([
    {
      id: 'greeting',
      sender: 'assistant',
      text: 'Hello! I am ClaimSathi, your claims assistant. Tell me in your own words what happened to your vehicle — include whatever details you have like your bike or car number, where and when it happened, and what was damaged.',
      audioText: 'Hello! I am ClaimSathi, your claims assistant. Tell me in your own words what happened to your vehicle.',
      language: 'en-IN',
      timestamp: 'Just now',
    },
  ])

  // System & Environment state (Always live real-input mode; never mock scripts)
  const [error, setError] = useState('')
  const [isDemoMode] = useState(false)
  const [activeModel, setActiveModel] = useState<string>('prisma-v3.0')
  const [selectedLanguage, setSelectedLanguage] = useState<string>('indic-auto')
  const [lockedLanguage, setLockedLanguage] = useState<string | null>(null)
  const [autoVoiceEnabled, setAutoVoiceEnabled] = useState(true)
  const [handsFreeMode, setHandsFreeMode] = useState(false)
  const [vadState, setVadState] = useState<VadState>('calibrating')
  const [voiceNotice, setVoiceNotice] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [hasStartedIntake, setHasStartedIntake] = useState(false)

  // Live browser SpeechRecognition parallel capture (real-speech fallback if external STT fails)
  const speechRecRef = useRef<any>(null)
  const liveBrowserTranscriptRef = useRef<string>('')
  const handsFreeModeRef = useRef(false)
  const isProcessingTurnRef = useRef(false)
  const hasStartedIntakeRef = useRef(false)
  const missingFieldsRef = useRef<string[]>([])
  const wizardStepRef = useRef<1 | 2 | 3>(1)
  const isPlayingAudioRef = useRef(false)
  const isRecordingRef = useRef(false)
  const isAnswerRecordingRef = useRef(false)
  const autoListenTimerRef = useRef<number | null>(null)
  const browserSpeechResolveRef = useRef<((completed: boolean) => void) | null>(null)
  const startRecordingRef = useRef<() => Promise<void>>(async () => {})
  const stopRecordingRef = useRef<() => Promise<void>>(async () => {})
  const cancelRecordingRef = useRef<() => void>(() => {})
  const startAnswerRecordingRef = useRef<() => Promise<void>>(async () => {})
  const stopAnswerRecordingRef = useRef<() => Promise<void>>(async () => {})
  const cancelAnswerRecordingRef = useRef<() => void>(() => {})

  const startBrowserSpeechCapture = (langHint?: string) => {
    liveBrowserTranscriptRef.current = ''
    if (typeof window === 'undefined') return
    const SpeechRec = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SpeechRec) return
    try {
      const rec = new SpeechRec()
      rec.continuous = true
      rec.interimResults = true
      rec.lang = langHint && langHint !== 'indic-auto' ? normalizeApiLang(langHint) : 'en-IN'
      rec.onresult = (event: any) => {
        let combined = ''
        for (let i = 0; i < event.results.length; i++) {
          combined += event.results[i][0].transcript + ' '
        }
        const cleaned = combined.trim()
        if (cleaned.length > liveBrowserTranscriptRef.current.length) {
          liveBrowserTranscriptRef.current = cleaned
          recorderRef.current?.notifyExternalSpeechActivity()
          answerRecorderRef.current?.notifyExternalSpeechActivity()
        }
      }
      rec.onerror = () => {}
      rec.start()
      speechRecRef.current = rec
    } catch {
      speechRecRef.current = null
    }
  }

  const stopBrowserSpeechCapture = (): string => {
    if (speechRecRef.current) {
      try {
        speechRecRef.current.stop()
      } catch {}
      speechRecRef.current = null
    }
    return liveBrowserTranscriptRef.current.trim()
  }

  const getKnownFieldsMap = (sourceFields: ClaimField[] = fields): Record<string, string | null> => {
    const out: Record<string, string | null> = {}
    for (const f of sourceFields) {
      out[f.name] = f.confidence !== 'missing' && f.value ? f.value : null
    }
    return out
  }

  const getHistoryPayload = (sourceMsgs: MessageTurn[] = messages): Array<{ sender: 'user' | 'assistant'; text: string }> =>
    sourceMsgs
      .filter((m) => !m.isStreaming && m.text)
      .slice(-10)
      .map((m) => ({ sender: m.sender, text: m.text }))

  // Resolve the active session language:
  // 1) If user manually selected a specific language, use it.
  // 2) If 'indic-auto' is selected and first turn locked a language, use lockedLanguage.
  // 3) Otherwise 'indic-auto' for initial detection.
  const normalizeApiLang = (lang: string) =>
    lang === 'hi-Latn' ? 'hi-IN' : lang === 'kn-Latn' ? 'kn-IN' : lang

  const effectiveSttLanguage =
    selectedLanguage !== 'indic-auto'
      ? normalizeApiLang(selectedLanguage)
      : lockedLanguage
      ? normalizeApiLang(lockedLanguage)
      : 'indic-auto'
  const effectiveConversationLanguage =
    selectedLanguage !== 'indic-auto' ? selectedLanguage : lockedLanguage || 'en-IN'

  const lockLanguageFromFirstTurn = (detectedLang?: string) => {
    if (!detectedLang || detectedLang === 'indic-auto') return
    if (selectedLanguage === 'indic-auto' && !lockedLanguage) {
      setLockedLanguage(detectedLang)
    }
  }

  // Merge newly extracted fields with existing captured fields so already spoken fields are NEVER lost or re-asked
  const mergeExtractedFields = (
    prevFields: ClaimField[],
    incomingFields: ClaimField[],
  ): { merged: ClaimField[]; remainingMissing: string[] } => {
    const incomingMap = new Map(incomingFields.map((f) => [f.name, f]))
    const merged = prevFields.map((existing) => {
      const inc = incomingMap.get(existing.name)
      const existingHasValue = existing.confidence !== 'missing' && Boolean(existing.value)
      const incomingHasValue = inc && inc.confidence !== 'missing' && Boolean(inc.value)

      if (incomingHasValue && inc) {
        return {
          ...existing,
          value: inc.value,
          confidence: 'high' as const,
          follow_up_question: null,
        }
      }
      if (existingHasValue) {
        return existing
      }
      return inc || existing
    })

    const remainingMissing = merged
      .filter((f) => f.confidence === 'missing' || !f.value)
      .map((f) => f.name)

    return { merged, remainingMissing }
  }

  // Audio Recording (Main Claim Description)
  const [isRecording, setIsRecording] = useState(false)
  const [recordingSeconds, setRecordingSeconds] = useState(0)
  const [audioVolume, setAudioVolume] = useState(0)
  const recorderRef = useRef<WavRecorder | null>(null)
  const timerRef = useRef<number | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  // Voice Answer Recording (Missing Details)
  const [isAnswerRecording, setIsAnswerRecording] = useState(false)
  const [answerRecordingSeconds, setAnswerRecordingSeconds] = useState(0)
  const [isProcessingAnswerVoice, setIsProcessingAnswerVoice] = useState(false)
  const answerRecorderRef = useRef<WavRecorder | null>(null)
  const answerTimerRef = useRef<number | null>(null)

  // Speech Synthesis (Gnani Timbre TTS)
  const [isSynthesizing, setIsSynthesizing] = useState(false)
  const [isPlayingAudio, setIsPlayingAudio] = useState(false)
  const [activeSpeechText, setActiveSpeechText] = useState<string | null>(null)
  const [lastSpokenSpeech, setLastSpokenSpeech] = useState<{ text: string; language?: string } | null>(null)
  const [activePillKey, setActivePillKey] = useState<string>('auto')
  const [evidenceNarration, setEvidenceNarration] = useState<{ spoken: string; lang: string } | null>(null)

  // Step 2: Evidence Collection & Guided Live Camera Capture state
  const [evidenceList, setEvidenceList] = useState<EvidenceAssetRecord[]>([])
  const [evidenceAiDecisions, setEvidenceAiDecisions] = useState<Record<string, 'PASS' | 'REVIEW' | 'REJECT'>>({})
  const [uploadingEvidence, setUploadingEvidence] = useState(false)
  const [captureSession, setCaptureSession] = useState<CaptureSessionResponse | null>(null)
  const [cameraActive, setCameraActive] = useState(false)
  const videoPreviewRef = useRef<HTMLVideoElement | null>(null)
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const evidenceInputRef = useRef<HTMLInputElement | null>(null)

  // Sprint 1.8 / 2.0 / 2.1: 5-Stage AI Evidence Intelligence, Identity Binding, Live-Camera Lock & DPDP Consent
  const [claimedVehicleType, setClaimedVehicleType] = useState<'four_wheeler' | 'two_wheeler'>('four_wheeler')
  const [vehicleMakeModel, setVehicleMakeModel] = useState<string>('')
  const [whatsappHandoff, setWhatsappHandoff] = useState<WhatsappHandoffResponse | null>(null)
  const [isHandoffCameraLocked, setIsHandoffCameraLocked] = useState<boolean>(false)
  const [dpdpPreCaptureConsent, setDpdpPreCaptureConsent] = useState<boolean>(true)
  const [aiVerificationResult, setAiVerificationResult] = useState<EvidenceVerificationReport | null>(null)
  const [isVerifyingEvidence, setIsVerifyingEvidence] = useState(false)
  const [selectedEvidenceFile, setSelectedEvidenceFile] = useState<File | null>(null)
  const [evidencePreviewUrl, setEvidencePreviewUrl] = useState<string | null>(null)
  const speechSessionIdRef = useRef<number>(0)
  const activeSpeechTextRef = useRef<string | null>(null)
  const verificationReqIdRef = useRef<number>(0)
  const narrationTimerRef = useRef<number | null>(null)

  // Conversation scroll container ref
  const chatScrollRef = useRef<HTMLDivElement | null>(null)

  // Revoke object URL on unmount / change
  useEffect(() => {
    return () => {
      if (evidencePreviewUrl) URL.revokeObjectURL(evidencePreviewUrl)
    }
  }, [evidencePreviewUrl])

  // Parse tokenized WhatsApp -> Stage 5 Live Camera URL query params and enforce camera-only lock
  useEffect(() => {
    if (typeof window === 'undefined') return
    const params = new URLSearchParams(window.location.search)
    const handoffSession = params.get('capture_session_id')
    const urlClaimId = params.get('claim_id')
    const urlStep = params.get('step')
    if (handoffSession) {
      setIsHandoffCameraLocked(true)
      setCaptureSession({
        session_id: handoffSession,
        claim_id: urlClaimId,
        instructions: [
          'Step 1 (Identity Binding): Show the front or rear vehicle registration plate alongside odometer / VIN.',
          'Step 2 (Impact Inspection): Hold steady on damaged area at a 45-degree angle.',
          'Step 3 (Context & RC/DL): Capture vehicle side profile with RC and Driver License.',
        ],
        created_at: new Date().toISOString(),
        expires_in_seconds: 900,
      })
      if (urlClaimId) setActiveClaimId(urlClaimId)
      if (urlStep === '2') setWizardStep(2)
    }
  }, [])

  // Helper: map any Step-1 vehicle_type string strictly to two_wheeler | four_wheeler | null
  const deriveVehicleCategoryFromField = (raw?: string | null): 'two_wheeler' | 'four_wheeler' | null => {
    const vtField = (raw || '').trim().toLowerCase()
    if (!vtField) return null
    if (
      vtField.includes('bike') ||
      vtField.includes('motorbike') ||
      vtField.includes('motorcycle') ||
      vtField.includes('two wheeler') ||
      vtField.includes('two-wheeler') ||
      vtField.includes('two_wheeler') ||
      vtField.includes('2 wheeler') ||
      vtField.includes('2-wheeler') ||
      vtField.includes('2w') ||
      vtField.includes('scooter') ||
      vtField.includes('scooty') ||
      vtField.includes('moped') ||
      vtField.includes('activa') ||
      vtField.includes('pulsar') ||
      vtField.includes('bullet') ||
      vtField.includes('royal enfield') ||
      vtField.includes('बाइक') ||
      vtField.includes('బైక్') ||
      vtField.includes('ಬೈಕ್') ||
      vtField.includes('பைக்')
    ) {
      return 'two_wheeler'
    }
    if (
      vtField.includes('car') ||
      vtField.includes('sedan') ||
      vtField.includes('suv') ||
      vtField.includes('hatchback') ||
      vtField.includes('four wheeler') ||
      vtField.includes('four-wheeler') ||
      vtField.includes('four_wheeler') ||
      vtField.includes('4 wheeler') ||
      vtField.includes('4-wheeler') ||
      vtField.includes('4w') ||
      vtField.includes('कार') ||
      vtField.includes('కార్') ||
      vtField.includes('ಕಾರ್') ||
      vtField.includes('கார்')
    ) {
      return 'four_wheeler'
    }
    return null
  }

  // Synchronize claimed vehicle category from conversational vehicle_type field
  useEffect(() => {
    const vtRaw = fields.find((f) => f.name === 'vehicle_type')?.value
    const mapped = deriveVehicleCategoryFromField(vtRaw)
    if (mapped) {
      setClaimedVehicleType(mapped)
    }
  }, [fields])

  useEffect(() => {
    handsFreeModeRef.current = handsFreeMode
  }, [handsFreeMode])

  useEffect(() => {
    isPlayingAudioRef.current = isPlayingAudio
  }, [isPlayingAudio])

  useEffect(() => {
    isRecordingRef.current = isRecording
  }, [isRecording])

  useEffect(() => {
    isAnswerRecordingRef.current = isAnswerRecording
  }, [isAnswerRecording])

  useEffect(() => {
    hasStartedIntakeRef.current = hasStartedIntake
  }, [hasStartedIntake])

  useEffect(() => {
    missingFieldsRef.current = missingFields
  }, [missingFields])

  useEffect(() => {
    wizardStepRef.current = wizardStep
  }, [wizardStep])

  useEffect(() => {
    api
      .health()
      .then((h) => {
        if (h.gnani_stt_model) setActiveModel(h.gnani_stt_model)
      })
      .catch(() => {
        // Keep real input mode even if health probe fails temporarily
      })

    return () => {
      stopAudio()
      stopLiveCamera()
      stopBrowserSpeechCapture()
      if (autoListenTimerRef.current) clearTimeout(autoListenTimerRef.current)
      if (narrationTimerRef.current) clearTimeout(narrationTimerRef.current)
      if (timerRef.current) clearInterval(timerRef.current)
      if (recorderRef.current) recorderRef.current.cancel()
      if (answerTimerRef.current) clearInterval(answerTimerRef.current)
      if (answerRecorderRef.current) answerRecorderRef.current.cancel()
    }
  }, [])

  useEffect(() => {
    if (chatScrollRef.current) {
      chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight
    }
  }, [messages, isRecording, isAnswerRecording])

  const [extractedSlotsSummary, setExtractedSlotsSummary] = useState<{
    vehicleType?: 'two_wheeler' | 'four_wheeler' | null
    makeModel?: string | null
    registration?: string | null
    damages?: string[]
    motorSlots?: VoiceIntakeMotorSlots | null
  } | null>(null)

  const syncExtractedSlots = (slots: {
    claimed_vehicle_type?: 'two_wheeler' | 'four_wheeler' | null
    vehicle_make_model?: string | null
    vehicle_registration?: string | null
    claimed_registration?: string | null
    motor_slots?: VoiceIntakeMotorSlots | null
    policy_reference?: string | null
    incident_date?: string | null
    incident_location?: string | null
    damage_keywords?: string[]
    incident_description?: string | null
  }) => {
    const resolvedMakeModel = slots.vehicle_make_model || slots.motor_slots?.vehicle_make_model || null
    if (resolvedMakeModel) {
      setVehicleMakeModel(resolvedMakeModel)
    }
    if (slots.claimed_vehicle_type === 'two_wheeler' || slots.claimed_vehicle_type === 'four_wheeler') {
      const vt = slots.claimed_vehicle_type
      setClaimedVehicleType(vt)
      setFields((prev) =>
        prev.map((f) =>
          f.name === 'vehicle_type' && (!f.value || f.confidence === 'missing')
            ? { ...f, value: vt === 'two_wheeler' ? 'Two-Wheeler (Bike)' : 'Four-Wheeler (Car)', confidence: 'high' }
            : f
        )
      )
      setMissingFields((prev) => prev.filter((m) => m !== 'vehicle_type'))
    }
    const resolvedReg = slots.claimed_registration || slots.vehicle_registration || slots.policy_reference
    if (resolvedReg) {
      setVehicleRegistration((prev) => (slots.vehicle_registration ? slots.vehicle_registration : prev || resolvedReg))
      setFields((prev) =>
        prev.map((f) =>
          f.name === 'policy_reference' && (!f.value || f.confidence === 'missing')
            ? { ...f, value: resolvedReg, confidence: 'high' }
            : f
        )
      )
      setMissingFields((prev) => prev.filter((m) => m !== 'policy_reference'))
    }
    if (slots.incident_date) {
      setIncidentTime((prev) => prev || slots.incident_date!)
    }
    if (slots.incident_location) {
      setMotorForm((prev) => (prev.declaration_place ? prev : { ...prev, declaration_place: slots.incident_location || '' }))
    }

    const ms = slots.motor_slots
    if (ms && Object.keys(ms).length > 0) {
      setMotorSlots((prev) => ({ ...prev, ...ms }))
      if (ms.incident_time) {
        setIncidentTime((prev) => prev || ms.incident_time || '')
      }
      if (ms.injury_or_third_party_flag === true) {
        setInjuriesReported('Injury / Third-party involvement reported')
      }
      if (ms.police_fir_lodged_flag === true) {
        setPoliceFirInfo('FIR / Police Report Lodged')
      } else if (ms.police_fir_lodged_flag === false) {
        setPoliceFirInfo('Not filed')
      }
      setMotorForm((prev) => ({
        ...prev,
        loss_type: ms.loss_type ?? prev.loss_type,
        incident_time: ms.incident_time || prev.incident_time,
        vehicle_usage_type: ms.vehicle_usage_type ?? prev.vehicle_usage_type,
        pillion_rider_present: ms.pillion_rider_present !== undefined && ms.pillion_rider_present !== null ? ms.pillion_rider_present : prev.pillion_rider_present,
        occupants_count: ms.occupants_count !== undefined && ms.occupants_count !== null ? ms.occupants_count : prev.occupants_count,
        driver_was_owner: ms.driver_was_owner !== undefined && ms.driver_was_owner !== null ? ms.driver_was_owner : prev.driver_was_owner,
        driver_name: ms.driver_name || (ms.driver_was_owner === true ? prev.claimant_name || prev.driver_name : prev.driver_name),
        driver_relationship: ms.driver_relationship ?? prev.driver_relationship,
        injury_or_third_party_flag: ms.injury_or_third_party_flag !== undefined && ms.injury_or_third_party_flag !== null ? ms.injury_or_third_party_flag : prev.injury_or_third_party_flag,
        police_fir_lodged_flag: ms.police_fir_lodged_flag !== undefined && ms.police_fir_lodged_flag !== null ? ms.police_fir_lodged_flag : prev.police_fir_lodged_flag,
        inspection_location: ms.inspection_location || prev.inspection_location,
      }))
    }

    if (slots.claimed_vehicle_type || resolvedMakeModel || slots.vehicle_registration || (slots.damage_keywords && slots.damage_keywords.length > 0) || (ms && Object.keys(ms).length > 0)) {
      setExtractedSlotsSummary((prev) => ({
        vehicleType: slots.claimed_vehicle_type || prev?.vehicleType || null,
        makeModel: resolvedMakeModel || prev?.makeModel || null,
        registration: slots.claimed_registration || slots.vehicle_registration || prev?.registration || null,
        damages: slots.damage_keywords?.length ? slots.damage_keywords : prev?.damages || [],
        motorSlots: ms ? { ...(prev?.motorSlots || {}), ...ms } : prev?.motorSlots || null,
      }))
    }
  }

  const cancelAllSpeechOutput = () => {
    speechSessionIdRef.current += 1
    stopAudio()
    if (autoListenTimerRef.current) {
      clearTimeout(autoListenTimerRef.current)
      autoListenTimerRef.current = null
    }
    if (narrationTimerRef.current) {
      clearTimeout(narrationTimerRef.current)
      narrationTimerRef.current = null
    }
    if (browserSpeechResolveRef.current) {
      const r = browserSpeechResolveRef.current
      browserSpeechResolveRef.current = null
      r(false)
    }
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel()
    }
    isPlayingAudioRef.current = false
    activeSpeechTextRef.current = null
    setIsSynthesizing(false)
    setIsPlayingAudio(false)
    setActiveSpeechText(null)
  }

  const speakViaBrowserSpeech = (
    text: string,
    targetLang: string,
    rate = 1.0,
    pitch = 1.0,
    sessionId?: number,
  ): Promise<boolean> => {
    const cleanSpeech = (text || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
    if (!cleanSpeech || typeof window === 'undefined' || !('speechSynthesis' in window)) {
      return Promise.resolve(false)
    }
    if (sessionId !== undefined && sessionId !== speechSessionIdRef.current) {
      return Promise.resolve(false)
    }
    return new Promise((resolve) => {
      try {
        stopAudio()
        window.speechSynthesis.cancel()
        browserSpeechResolveRef.current = resolve
        const utter = new SpeechSynthesisUtterance(cleanSpeech)
        utter.lang = targetLang
        utter.rate = rate
        utter.pitch = pitch
        utter.onend = () => {
          browserSpeechResolveRef.current = null
          isPlayingAudioRef.current = false
          activeSpeechTextRef.current = null
          setIsPlayingAudio(false)
          setActiveSpeechText(null)
          resolve(sessionId === undefined || sessionId === speechSessionIdRef.current)
        }
        utter.onerror = () => {
          browserSpeechResolveRef.current = null
          isPlayingAudioRef.current = false
          activeSpeechTextRef.current = null
          setIsPlayingAudio(false)
          setActiveSpeechText(null)
          resolve(false)
        }
        isPlayingAudioRef.current = true
        setIsPlayingAudio(true)
        window.speechSynthesis.speak(utter)
      } catch {
        browserSpeechResolveRef.current = null
        isPlayingAudioRef.current = false
        resolve(false)
      }
    })
  }

  // ── Speech Synthesis with Gnani Timbre v3 + Browser speechSynthesis Fallback ──
  const speakText = async (
    text: string,
    langCode?: string,
    rate = 1.0,
    pitch = 1.0,
    options?: { toggleIfSame?: boolean },
  ): Promise<boolean> => {
    if (options?.toggleIfSame && isPlayingAudioRef.current && activeSpeechTextRef.current === text) {
      cancelAllSpeechOutput()
      return false
    }

    cancelAllSpeechOutput()
    const mySessionId = ++speechSessionIdRef.current

    setLastSpokenSpeech({ text, language: langCode })
    setIsSynthesizing(true)
    activeSpeechTextRef.current = text
    setActiveSpeechText(text)
    setError('')

    const code = (langCode || effectiveConversationLanguage || 'en-IN').toLowerCase()
    const targetLang = code.startsWith('te')
      ? 'te-IN'
      : code.startsWith('kn')
      ? 'kn-IN'
      : code.startsWith('hi')
      ? 'hi-IN'
      : code.startsWith('ta')
      ? 'ta-IN'
      : code.startsWith('mr')
      ? 'mr-IN'
      : 'en-IN'

    try {
      const audioBlob = await api.synthesizeSpeech(text, {
        demo: isDemoMode,
        language: targetLang,
        speed: rate,
      })
      if (mySessionId !== speechSessionIdRef.current) {
        return false
      }
      setIsSynthesizing(false)
      isPlayingAudioRef.current = true
      setIsPlayingAudio(true)

      const completedNaturally = await playAudioBlob(audioBlob)
      if (mySessionId !== speechSessionIdRef.current) {
        return false
      }
      isPlayingAudioRef.current = false
      activeSpeechTextRef.current = null
      setIsPlayingAudio(false)
      setActiveSpeechText(null)
      return completedNaturally
    } catch {
      if (mySessionId !== speechSessionIdRef.current) {
        return false
      }
      setIsSynthesizing(false)
      const spokeNaturally = await speakViaBrowserSpeech(text, targetLang, rate, pitch, mySessionId)
      if (mySessionId !== speechSessionIdRef.current) {
        return false
      }
      isPlayingAudioRef.current = false
      activeSpeechTextRef.current = null
      setIsPlayingAudio(false)
      setActiveSpeechText(null)
      return spokeNaturally
    }
  }

  const handleReplayLastVoice = () => {
    if (isPlayingAudioRef.current) {
      cancelAllSpeechOutput()
      return
    }
    if (lastSpokenSpeech) {
      void speakText(lastSpokenSpeech.text, lastSpokenSpeech.language, 1.0, 1.0, { toggleIfSame: true })
    } else {
      const lastMsg = [...messages].reverse().find((m) => m.sender === 'assistant' && (m.audioText || m.text))
      if (lastMsg) {
        void speakText(lastMsg.audioText || lastMsg.text, lastMsg.language, 1.0, 1.0, { toggleIfSame: true })
      }
    }
  }

  // ── Unified Stateful Conversation Updater ──
  const applyConversationResult = (
    res: {
      transcript: string
      no_speech_detected?: boolean
      is_complete?: boolean
      detected_language?: string | null
      assistant_language?: string | null
      assistant_dialogue?: string | null
      assistant_speech_text?: string | null
      reply_text?: string | null
      fields: ClaimField[]
      missing_fields: string[]
      model?: string
      request_metadata?: { duration_seconds?: number; processing_time?: number }
      claimed_vehicle_type?: 'two_wheeler' | 'four_wheeler' | null
      vehicle_make_model?: string | null
      vehicle_registration?: string | null
      claimed_registration?: string | null
      motor_slots?: VoiceIntakeMotorSlots | null
      damage_keywords?: string[]
      incident_description?: string | null
      reasoning_trace?: ConversationalReasoningTrace | null
    },
    procTurnId?: string,
  ) => {
    if (res.no_speech_detected || !(res.transcript || '').trim()) {
      if (procTurnId) {
        setMessages((prev) => prev.filter((m) => m.id !== procTurnId))
      }
      setVoiceNotice('No clear speech was detected — tap the mic and speak clearly whenever you are ready.')
      return
    }

    setVoiceNotice('')
    setHasStartedIntake(true)
    const detectedLang =
      res.assistant_language ||
      res.detected_language ||
      (selectedLanguage !== 'indic-auto' ? selectedLanguage : 'en-IN')

    lockLanguageFromFirstTurn(detectedLang)

    setTranscript((prev) => (prev ? `${prev} ${res.transcript}` : res.transcript))
    const { merged, remainingMissing } = mergeExtractedFields(fields, res.fields)
    setFields(merged)
    setMissingFields(remainingMissing)
    if (res.model) setActiveModel(res.model)
    setActiveMissingIndex(0)

    const mergedVehicleCat = deriveVehicleCategoryFromField(
      merged.find((f) => f.name === 'vehicle_type')?.value || null,
    )
    syncExtractedSlots({
      claimed_vehicle_type: res.claimed_vehicle_type || mergedVehicleCat,
      vehicle_make_model: res.vehicle_make_model,
      vehicle_registration: res.vehicle_registration,
      claimed_registration: res.claimed_registration,
      motor_slots: res.motor_slots,
      policy_reference: merged.find((f) => f.name === 'policy_reference')?.value || null,
      incident_date: merged.find((f) => f.name === 'incident_date')?.value || null,
      incident_location: merged.find((f) => f.name === 'incident_location')?.value || null,
      damage_keywords: res.damage_keywords,
      incident_description: res.incident_description,
    })

    if (res.reasoning_trace?.drivability_assessment === 'non_drivable_towing_recommended') {
      setDrivableStatus((prev) => prev || 'No — Towing Recommended (Critical Damage)')
    } else if (res.reasoning_trace?.drivability_assessment === 'likely_drivable') {
      setDrivableStatus((prev) => prev || 'Yes — Drivable (Minor Exterior Damage)')
    }

    const userTurn: MessageTurn = {
      id: 'user-' + Date.now(),
      sender: 'user',
      text: res.transcript,
      language: detectedLang,
      audioDuration: res.request_metadata?.duration_seconds,
      latencyMs: res.request_metadata?.processing_time
        ? Math.round(res.request_metadata.processing_time * 1000)
        : undefined,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }

    const assistantText =
      res.reply_text ||
      res.assistant_dialogue ||
      'I caught that — let me know what else you would like to add.'
    const assistantSpeech = res.assistant_speech_text || assistantText
    const speechRate = res.reasoning_trace?.speech_rate ?? 1.0
    const speechPitch = res.reasoning_trace?.speech_pitch ?? 1.0

    const assistantTurn: MessageTurn = {
      id: 'assistant-' + Date.now(),
      sender: 'assistant',
      text: assistantText,
      audioText: assistantSpeech,
      language: detectedLang,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      reasoningTrace: res.reasoning_trace || null,
    }

    setMessages((prev) => [
      ...(procTurnId ? prev.filter((m) => m.id !== procTurnId) : prev),
      userTurn,
      assistantTurn,
    ])

    const shouldAutoFollowListen =
      handsFreeModeRef.current &&
      wizardStepRef.current === 1 &&
      !res.is_complete &&
      remainingMissing.length > 0

    if (res.is_complete && handsFreeModeRef.current) {
      setHandsFreeMode(false)
    }

    const triggerHandsFreeReopen = () => {
      autoListenTimerRef.current = window.setTimeout(() => {
        if (
          handsFreeModeRef.current &&
          wizardStepRef.current === 1 &&
          !isProcessingTurnRef.current &&
          !isRecordingRef.current &&
          !isAnswerRecordingRef.current
        ) {
          if (hasStartedIntakeRef.current && missingFieldsRef.current.length > 0) {
            void startAnswerRecordingRef.current()
          } else {
            void startRecordingRef.current()
          }
        }
      }, 450)
    }

    if (autoVoiceEnabled && assistantSpeech) {
      cancelAllSpeechOutput()
      autoListenTimerRef.current = window.setTimeout(async () => {
        const completedNaturally = await speakText(assistantSpeech, detectedLang, speechRate, speechPitch)
        if (completedNaturally && shouldAutoFollowListen && handsFreeModeRef.current && !isProcessingTurnRef.current) {
          triggerHandsFreeReopen()
        }
      }, 200)
    } else if (shouldAutoFollowListen) {
      triggerHandsFreeReopen()
    }
  }

  const toggleHandsFreeMode = () => {
    const next = !handsFreeModeRef.current
    handsFreeModeRef.current = next
    setHandsFreeMode(next)
    setVoiceNotice('')
    if (next) {
      recorderRef.current?.setAutoStopOnSilence(true)
      answerRecorderRef.current?.setAutoStopOnSilence(true)
      if (
        !isRecordingRef.current &&
        !isAnswerRecordingRef.current &&
        !isProcessingTurnRef.current &&
        !isPlayingAudioRef.current &&
        !isSynthesizing &&
        wizardStepRef.current === 1
      ) {
        if (hasStartedIntakeRef.current && missingFieldsRef.current.length > 0) {
          void startAnswerRecordingRef.current()
        } else {
          void startRecordingRef.current()
        }
      }
    } else {
      if (autoListenTimerRef.current) {
        clearTimeout(autoListenTimerRef.current)
        autoListenTimerRef.current = null
      }
      recorderRef.current?.setAutoStopOnSilence(false)
      answerRecorderRef.current?.setAutoStopOnSilence(false)
    }
  }

  // ── Main Voice Intake Recording ──
  const startRecording = async () => {
    if (recorderRef.current || answerRecorderRef.current) return
    cancelAllSpeechOutput()
    setError('')
    setVoiceNotice('')
    setVadState('calibrating')
    try {
      const recorder = new WavRecorder(16000, (vol) => setAudioVolume(vol), {
        autoStopOnSilence: handsFreeModeRef.current,
        silenceDurationMs: 1500,
        minSpeechMs: 280,
        maxInitialSilenceMs: 12000,
        onVadStateChange: setVadState,
        onAutoSilenceStop: () => {
          void stopRecordingRef.current()
        },
        onInitialSilenceTimeout: () => {
          cancelRecordingRef.current()
          setHandsFreeMode(false)
          setVoiceNotice('Hands-free paused after 12s of silence — toggle Hands-Free or tap the mic when ready.')
        },
      })
      recorderRef.current = recorder
      await recorder.start()
      startBrowserSpeechCapture(effectiveSttLanguage)

      isRecordingRef.current = true
      setIsRecording(true)
      setRecordingSeconds(0)

      timerRef.current = window.setInterval(() => {
        setRecordingSeconds((prev) => {
          if (prev >= 29) {
            void stopRecordingRef.current()
            return 30
          }
          return prev + 1
        })
      }, 1000)
    } catch (err: any) {
      recorderRef.current = null
      isRecordingRef.current = false
      setError(err.message || 'Microphone access denied. Grant permission or upload audio.')
      setIsRecording(false)
    }
  }

  const stopRecording = async () => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    const browserCapturedText = stopBrowserSpeechCapture()

    if (!recorderRef.current) return
    const activeRecorder = recorderRef.current
    recorderRef.current = null
    isRecordingRef.current = false
    setIsRecording(false)
    setAudioVolume(0)

    try {
      const stats = activeRecorder.getStats()
      const audioBlob = await activeRecorder.stop()
      if (!stats.hasSpeech && !browserCapturedText) {
        setVoiceNotice("I didn't hear any speech in that clip — tap the mic whenever you're ready to speak.")
        return
      }
      await handleProcessMainAudio(audioBlob, 'recording.wav', browserCapturedText)
    } catch (err: any) {
      setError(err.message || 'Failed to capture recorded audio.')
    }
  }

  const cancelRecording = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    stopBrowserSpeechCapture()
    if (recorderRef.current) {
      recorderRef.current.cancel()
      recorderRef.current = null
    }
    isRecordingRef.current = false
    setIsRecording(false)
    setRecordingSeconds(0)
    setAudioVolume(0)
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setError('')
    setVoiceNotice('')
    await handleProcessMainAudio(file, file.name)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  // ── Process Spoken Intake with Live Gnani STT + Stateful Conversation ──
  const handleProcessMainAudio = async (
    blob: Blob | File,
    filename: string,
    browserFallbackTranscript: string = '',
  ) => {
    setError('')
    setVoiceNotice('')
    isProcessingTurnRef.current = true

    const procTurnId = 'proc-' + Date.now()
    setMessages((prev) => [
      ...prev,
      {
        id: procTurnId,
        sender: 'assistant',
        text: 'Listening and thinking about what you shared...',
        timestamp: 'Just now',
        isStreaming: true,
      },
    ])

    const knownMap = getKnownFieldsMap()
    const historyList = getHistoryPayload()
    const expectedField = missingFields.length > 0 ? missingFields[activeMissingIndex] : null
    const mergedMotorContext = {
      ...motorSlots,
      ...(vehicleMakeModel.trim() ? { vehicle_make_model: vehicleMakeModel.trim() } : {}),
    }

    try {
      const data: VoiceTranscribeResponse = await api.transcribeVoice(
        blob,
        filename,
        false,
        effectiveSttLanguage,
        knownMap,
        historyList,
        expectedField,
        mergedMotorContext,
      )
      if ((data.no_speech_detected || !(data.transcript || '').trim()) && browserFallbackTranscript) {
        const conv = await api.converseClaimTurn({
          message: browserFallbackTranscript,
          language: effectiveSttLanguage,
          known_fields: knownMap,
          known_motor_slots: mergedMotorContext,
          history: historyList,
          expected_field: expectedField,
        })
        applyConversationResult(conv, procTurnId)
        return
      }
      applyConversationResult(data, procTurnId)
    } catch (err: any) {
      if (browserFallbackTranscript) {
        try {
          const conv = await api.converseClaimTurn({
            message: browserFallbackTranscript,
            language: effectiveSttLanguage,
            known_fields: knownMap,
            known_motor_slots: mergedMotorContext,
            history: historyList,
            expected_field: expectedField,
          })
          applyConversationResult(conv, procTurnId)
          return
        } catch (convErr: any) {
          setMessages((prev) => prev.filter((m) => m.id !== procTurnId))
          setError(convErr.message || 'Could not process voice input.')
          return
        }
      }
      setMessages((prev) => prev.filter((m) => m.id !== procTurnId))
      setError(err.message || 'Speech transcription failed. Please type your details below or retry speaking.')
    } finally {
      isProcessingTurnRef.current = false
    }
  }

  // ── Process Typed Natural Conversation Turn ──
  const handleProcessTextIntake = async (customText?: string) => {
    const raw = (customText ?? textIntakeInput).trim()
    if (!raw) return
    cancelAllSpeechOutput()
    setError('')
    setVoiceNotice('')
    setTextIntakeInput('')
    isProcessingTurnRef.current = true

    try {
      const data = await api.converseClaimTurn({
        message: raw,
        language: effectiveSttLanguage,
        known_fields: getKnownFieldsMap(),
        known_motor_slots: {
          ...motorSlots,
          ...(vehicleMakeModel.trim() ? { vehicle_make_model: vehicleMakeModel.trim() } : {}),
        },
        history: getHistoryPayload(),
        expected_field: missingFields.length > 0 ? missingFields[activeMissingIndex] : null,
      })
      applyConversationResult(data)
    } catch (err: any) {
      setError(err.message || 'Failed to process your message.')
    } finally {
      isProcessingTurnRef.current = false
    }
  }

  // ── Follow-Up Voice Recording ──
  const startAnswerRecording = async () => {
    if (recorderRef.current || answerRecorderRef.current) return
    cancelAllSpeechOutput()
    setError('')
    setVoiceNotice('')
    setVadState('calibrating')
    try {
      const recorder = new WavRecorder(16000, (vol) => setAudioVolume(vol), {
        autoStopOnSilence: handsFreeModeRef.current,
        silenceDurationMs: 1500,
        minSpeechMs: 280,
        maxInitialSilenceMs: 12000,
        onVadStateChange: setVadState,
        onAutoSilenceStop: () => {
          void stopAnswerRecordingRef.current()
        },
        onInitialSilenceTimeout: () => {
          cancelAnswerRecordingRef.current()
          setHandsFreeMode(false)
          setVoiceNotice('Hands-free paused after 12s of silence — toggle Hands-Free or tap the mic when ready.')
        },
      })
      answerRecorderRef.current = recorder
      await recorder.start()
      startBrowserSpeechCapture(effectiveSttLanguage)

      isAnswerRecordingRef.current = true
      setIsAnswerRecording(true)
      setAnswerRecordingSeconds(0)

      answerTimerRef.current = window.setInterval(() => {
        setAnswerRecordingSeconds((s) => {
          if (s >= 29) {
            void stopAnswerRecordingRef.current()
            return 30
          }
          return s + 1
        })
      }, 1000)
    } catch (err: any) {
      answerRecorderRef.current = null
      isAnswerRecordingRef.current = false
      setError(err.message || 'Microphone access denied for answer.')
      setIsAnswerRecording(false)
    }
  }

  const stopAnswerRecording = async () => {
    if (answerTimerRef.current) {
      clearInterval(answerTimerRef.current)
      answerTimerRef.current = null
    }
    const browserCaptured = stopBrowserSpeechCapture()
    if (!answerRecorderRef.current) return

    const activeRecorder = answerRecorderRef.current
    answerRecorderRef.current = null
    isAnswerRecordingRef.current = false
    setIsAnswerRecording(false)
    setAudioVolume(0)

    const stats = activeRecorder.getStats()
    const audioBlob = await activeRecorder.stop()
    if (!stats.hasSpeech && !browserCaptured) {
      setVoiceNotice('No speech detected in your answer — tap the mic again or type below.')
      return
    }

    setIsProcessingAnswerVoice(true)
    isProcessingTurnRef.current = true

    const knownMap = getKnownFieldsMap()
    const historyList = getHistoryPayload()
    const expectedField = missingFields[activeMissingIndex] || null
    const mergedMotorContext = {
      ...motorSlots,
      ...(vehicleMakeModel.trim() ? { vehicle_make_model: vehicleMakeModel.trim() } : {}),
    }

    try {
      const resp = await api.transcribeVoice(
        audioBlob,
        'answer.wav',
        false,
        effectiveSttLanguage,
        knownMap,
        historyList,
        expectedField,
        mergedMotorContext,
      )
      setIsProcessingAnswerVoice(false)

      if (!resp.no_speech_detected && (resp.transcript || '').trim()) {
        applyConversationResult(resp)
      } else if (browserCaptured) {
        const conv = await api.converseClaimTurn({
          message: browserCaptured,
          language: effectiveSttLanguage,
          known_fields: knownMap,
          known_motor_slots: mergedMotorContext,
          history: historyList,
          expected_field: expectedField,
        })
        applyConversationResult(conv)
      } else {
        setVoiceNotice('No speech detected in your answer — please tap the mic again or type below.')
      }
    } catch (err: any) {
      if (browserCaptured) {
        try {
          const conv = await api.converseClaimTurn({
            message: browserCaptured,
            language: effectiveSttLanguage,
            known_fields: knownMap,
            known_motor_slots: mergedMotorContext,
            history: historyList,
            expected_field: expectedField,
          })
          setIsProcessingAnswerVoice(false)
          applyConversationResult(conv)
          return
        } catch {}
      }
      setIsProcessingAnswerVoice(false)
      setError(err.message || 'Failed to process voice answer. Please type below or retry.')
    } finally {
      isProcessingTurnRef.current = false
    }
  }

  const cancelAnswerRecording = () => {
    if (answerTimerRef.current) {
      clearInterval(answerTimerRef.current)
      answerTimerRef.current = null
    }
    stopBrowserSpeechCapture()
    if (answerRecorderRef.current) {
      answerRecorderRef.current.cancel()
      answerRecorderRef.current = null
    }
    isAnswerRecordingRef.current = false
    setIsAnswerRecording(false)
    setAnswerRecordingSeconds(0)
    setAudioVolume(0)
  }

  startRecordingRef.current = startRecording
  stopRecordingRef.current = stopRecording
  cancelRecordingRef.current = cancelRecording
  startAnswerRecordingRef.current = startAnswerRecording
  stopAnswerRecordingRef.current = stopAnswerRecording
  cancelAnswerRecordingRef.current = cancelAnswerRecording

  const vadStatusLabel =
    vadState === 'calibrating'
      ? 'Calibrating mic...'
      : vadState === 'speaking'
      ? 'Hearing you — pause to send'
      : vadState === 'pausing'
      ? 'Pause detected — sending...'
      : 'Speak anytime...'

  const handleApplyAnswer = async (value: string) => {
    const clean = (value || '').trim()
    if (!clean) return
    cancelAllSpeechOutput()
    setError('')
    setVoiceNotice('')
    isProcessingTurnRef.current = true
    try {
      const conv = await api.converseClaimTurn({
        message: clean,
        language: effectiveSttLanguage,
        known_fields: getKnownFieldsMap(),
        known_motor_slots: {
          ...motorSlots,
          ...(vehicleMakeModel.trim() ? { vehicle_make_model: vehicleMakeModel.trim() } : {}),
        },
        history: getHistoryPayload(),
        expected_field: missingFields[activeMissingIndex] || null,
      })
      applyConversationResult(conv)
    } catch (err: any) {
      setError(err.message || 'Failed to process answer.')
    } finally {
      isProcessingTurnRef.current = false
    }
  }

  const handleEditField = (name: string, value: string) => {
    setFields((prev) => {
      const next = prev.map((f) =>
        f.name === name ? { ...f, value, confidence: value.trim() ? ('high' as const) : ('missing' as const), is_edited: true } : f,
      )
      setMissingFields(next.filter((f) => f.confidence === 'missing' || !f.value).map((f) => f.name))
      return next
    })
    if (name === 'vehicle_type') {
      const cat = deriveVehicleCategoryFromField(value)
      if (cat) setClaimedVehicleType(cat)
    }
  }

  // ── Transition from Step 1 (Conversation) -> Step 2 (Evidence Collection & Screening) ──
  const handleProceedToEvidenceStep = async () => {
    setError('')
    const fieldMap = Object.fromEntries(fields.map((f) => [f.name, f.value || '']))
    if (
      !fieldMap.policy_reference ||
      !fieldMap.incident_location ||
      !fieldMap.incident_date ||
      !fieldMap.vehicle_type ||
      !fieldMap.damage_description
    ) {
      setError('Please complete all 5 core claim fields (by voice, text, or clicking the pencil icon) before proceeding to Evidence Screening.')
      return
    }
    const lockedCat = deriveVehicleCategoryFromField(fieldMap.vehicle_type)
    if (lockedCat) {
      setClaimedVehicleType(lockedCat)
    }

    if (!activeClaimId) {
      setIsSubmitting(true)
      try {
        const storedUser = getStoredUser()
        const created = await api.createClaim({
          customer_id: storedUser?.customer_id,
          insurer_name: storedUser?.declared_insurer || 'Bharat General Insurance',
          policy_reference: fieldMap.policy_reference,
          claimed_registration: vehicleRegistration || undefined,
          incident_location: fieldMap.incident_location,
          incident_date: fieldMap.incident_date,
          vehicle_type: fieldMap.vehicle_type,
          vehicle_make_model: vehicleMakeModel || undefined,
          claimed_vehicle_type: lockedCat || claimedVehicleType,
          damage_description: fieldMap.damage_description,
          injuries_reported: injuriesReported,
          people_involved: motorForm.driver_name ? `${motorForm.driver_name} (${motorForm.driver_relationship || 'Driver'})` : `Policyholder (${storedUser?.name || 'Driver'})`,
          transcript: transcript || 'Customer conversational intake completed.',
          motor_claim_form: {
            ...motorForm,
            pillion_rider_present: (lockedCat || claimedVehicleType) === 'two_wheeler' ? motorForm.pillion_rider_present : undefined,
            occupants_count: (lockedCat || claimedVehicleType) === 'four_wheeler' ? motorForm.occupants_count : undefined,
          },
        })
        setActiveClaimId(created.id)
      } catch (err: any) {
        setError(err.message || 'Failed to initialize claim case.')
        setIsSubmitting(false)
        return
      }
      setIsSubmitting(false)
    }

    cancelAllSpeechOutput()
    setHandsFreeMode(false)
    setWizardStep(2)
  }

  // ── Step 2: 5-Stage AI Verification Pipeline & Legacy Upload ──
  const runAiVerificationOnFile = async (
    file: File,
    overrideVehicleType?: 'four_wheeler' | 'two_wheeler',
    overrideMakeModel?: string,
    liveOptions?: { captureSessionId?: string; captureMethod?: string; lockSessionOnVerify?: boolean },
  ): Promise<EvidenceVerificationReport | null> => {
    const reqId = ++verificationReqIdRef.current
    const vType = overrideVehicleType || claimedVehicleType
    const activeMakeModel = overrideMakeModel !== undefined ? overrideMakeModel : vehicleMakeModel
    const activeReg =
      vehicleRegistration ||
      fields.find((f) => f.name === 'policy_reference')?.value ||
      ''
    cancelAllSpeechOutput()
    setEvidenceNarration(null)
    setSelectedEvidenceFile(file)
    if (evidencePreviewUrl) URL.revokeObjectURL(evidencePreviewUrl)
    setEvidencePreviewUrl(URL.createObjectURL(file))
    setIsVerifyingEvidence(true)
    setError('')
    try {
      const res = await api.verifyEvidenceV1(
        file,
        vType,
        activeMakeModel,
        activeReg,
        liveOptions?.captureSessionId,
        liveOptions?.captureMethod || 'upload_photo',
        Boolean(liveOptions?.lockSessionOnVerify),
      )
      if (reqId !== verificationReqIdRef.current) return null
      setAiVerificationResult(res)
      if (res.decision === 'REJECT') {
        const isMism =
          Boolean(res.vehicle_category_mismatch) ||
          Boolean(res.reasons?.some((r) => r.includes('VEHICLE_CATEGORY_MISMATCH')))
        if (isMism) {
          setError(
            `Vehicle Category Mismatch: You claimed ${formatCategoryLabel(vType)} in Step 1, but the AI detected a ${formatCategoryLabel(res.detected_vehicle_category)} in the uploaded photo. This photo was NOT added to your claim.`,
          )
        } else if (res.reasons?.some((r) => r.includes('NON_VEHICLE_PERSON_SELFIE'))) {
          setError('No Vehicle Detected (Person/Selfie): This image was rejected and was NOT added to your claim.')
        } else if (res.reasons?.some((r) => r.includes('NO_VEHICLE_DETECTED_REJECTED') || r.includes('NON_VEHICLE_OBJECT_DETECTED'))) {
          setError('No Bike or Car Detected: Non-vehicle images are rejected and are NOT added to your claim.')
        } else {
          setError(`Evidence Rejected: ${res.reasons.join(', ')}`)
        }
      }

      // Multimodal Evidence Narration (Spoken Indic Feedback - Sprint 1.8)
      const isMism =
        Boolean(res.vehicle_category_mismatch) ||
        Boolean(res.reasons?.some((r) => r.includes('VEHICLE_CATEGORY_MISMATCH')))
      try {
        const narration = await api.narrateEvidence({
          decision: res.decision,
          claimed_vehicle_type: vType,
          detected_vehicle_category: res.detected_vehicle_category,
          vehicle_category_mismatch: isMism,
          total_estimated_inr: res.cost_estimate?.total_estimated_inr || 0,
          damages: res.cost_estimate?.line_items || [],
          language: lockedLanguage || selectedLanguage || 'hi-IN',
          reasons: res.reasons || [],
        })
        if (reqId !== verificationReqIdRef.current) return res
        if (narration?.spoken_narration) {
          setEvidenceNarration({
            spoken: narration.spoken_narration,
            lang: narration.language,
          })
          if (autoVoiceEnabled) {
            if (narrationTimerRef.current) clearTimeout(narrationTimerRef.current)
            narrationTimerRef.current = window.setTimeout(() => {
              if (reqId === verificationReqIdRef.current) {
                void speakText(narration.spoken_narration, narration.language)
              }
            }, 250)
          }
        }
      } catch (narrationErr) {
        console.warn('Evidence narration failed:', narrationErr)
      }
      return res
    } catch (err: any) {
      if (reqId !== verificationReqIdRef.current) return null
      setError(err.message || '5-Stage AI evidence verification failed.')
      return null
    } finally {
      if (reqId === verificationReqIdRef.current) {
        setIsVerifyingEvidence(false)
      }
    }
  }

  const handleToggleVehicleCategory = async (newType: 'four_wheeler' | 'two_wheeler') => {
    setClaimedVehicleType(newType)
    if (selectedEvidenceFile) {
      await runAiVerificationOnFile(selectedEvidenceFile, newType)
    }
  }

  const handleGenerateWhatsappHandoff = async () => {
    setError('')
    try {
      const storedUser = getStoredUser()
      const activeReg =
        vehicleRegistration ||
        fields.find((f) => f.name === 'policy_reference')?.value ||
        ''
      const handoff = await api.createWhatsappLiveCameraHandoff(
        activeClaimId,
        storedUser?.phone,
        activeReg,
      )
      setWhatsappHandoff(handoff)
      setIsHandoffCameraLocked(true)
      setCaptureSession({
        session_id: handoff.session_id,
        claim_id: handoff.claim_id,
        instructions: handoff.instructions,
        created_at: new Date().toISOString(),
        expires_in_seconds: handoff.expires_in_seconds,
      })
    } catch (err: any) {
      setError(err.message || 'Failed to generate WhatsApp Stage 5 Live Camera handoff link.')
    }
  }

  const handleUploadEvidenceFile = async (
    file: Blob | File,
    filename: string,
    captureMethod: string = 'upload_photo',
    sessionId?: string,
    aiDecision?: 'PASS' | 'REVIEW' | 'REJECT',
  ) => {
    if (!activeClaimId) return
    setUploadingEvidence(true)
    setError('')
    try {
      const asset = await api.uploadEvidence(
        activeClaimId,
        file,
        filename,
        captureMethod,
        sessionId,
      )
      setEvidenceList((prev) => [...prev, asset])
      if (aiDecision) {
        setEvidenceAiDecisions((prev) => ({ ...prev, [asset.evidence_id]: aiDecision }))
      }
    } catch (err: any) {
      setError(err.message || 'Evidence upload & integrity check failed.')
    } finally {
      setUploadingEvidence(false)
    }
  }

  const handleEvidenceInputChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return
    for (let i = 0; i < files.length; i++) {
      const f = files[i]
      const isVideo = f.type.startsWith('video/') || /\.(mp4|mov|webm|avi)$/i.test(f.name)
      let aiDecision: 'PASS' | 'REVIEW' | 'REJECT' | undefined
      if (!isVideo) {
        const aiRes = await runAiVerificationOnFile(f)
        if (!aiRes || aiRes.decision === 'REJECT') {
          // Never push rejected non-vehicle, person/selfie, or mismatched photos into Claim Evidence Inventory
          continue
        }
        aiDecision = aiRes.decision
      }
      await handleUploadEvidenceFile(f, f.name, isVideo ? 'upload_video' : 'upload_photo', undefined, aiDecision)
    }
    if (evidenceInputRef.current) evidenceInputRef.current.value = ''
  }

  // ── Step 2: Guided Live Camera Capture (Step 5 & 6D of PDF) ──
  const startGuidedCameraSession = async () => {
    if (!activeClaimId) return
    setError('')
    try {
      const session = await api.startCaptureSession(activeClaimId, 'guided_video_and_photo')
      setCaptureSession(session)

      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 640 }, height: { ideal: 480 } },
        audio: false,
      })
      mediaStreamRef.current = stream
      setCameraActive(true)
      setTimeout(() => {
        if (videoPreviewRef.current) {
          videoPreviewRef.current.srcObject = stream
          videoPreviewRef.current.play().catch(() => {})
        }
      }, 100)
    } catch (err: any) {
      setError(
        `Live Camera Note: ${err.message || 'Camera unavailable'}. Capture session ${captureSession?.session_id || ''} was still created on the server — you can use 'Simulate Guided Live Capture' below if no physical webcam is attached.`,
      )
    }
  }

  const stopLiveCamera = () => {
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop())
      mediaStreamRef.current = null
    }
    setCameraActive(false)
  }

  const captureLiveFrameFromCamera = async () => {
    if (!activeClaimId) return
    let session = captureSession
    if (!session) {
      session = await api.startCaptureSession(activeClaimId, 'guided_video_and_photo')
      setCaptureSession(session)
    }

    const canvas = document.createElement('canvas')
    canvas.width = 640
    canvas.height = 480
    const ctx = canvas.getContext('2d')!

    if (videoPreviewRef.current && cameraActive) {
      ctx.drawImage(videoPreviewRef.current, 0, 0, 640, 480)
    } else {
      // Render realistic vehicle damage capture with session watermark
      drawSimulatedVehicleDamageCanvas(ctx, 640, 480, session.session_id, Date.now())
    }

    canvas.toBlob(
      async (blob) => {
        if (blob) {
          const fname = `live_capture_${session!.session_id}.jpg`
          const fileObj = new File([blob], fname, { type: 'image/jpeg' })
          const aiRes = await runAiVerificationOnFile(fileObj, claimedVehicleType, vehicleMakeModel, {
            captureSessionId: session!.session_id,
            captureMethod: 'live_photo',
            lockSessionOnVerify: isHandoffCameraLocked,
          })
          if (!aiRes || aiRes.decision === 'REJECT') {
            return
          }
          await handleUploadEvidenceFile(
            blob,
            fname,
            'live_photo',
            session!.session_id,
            aiRes.decision,
          )
        }
      },
      'image/jpeg',
      0.92,
    )
  }

  // ── Built-in Evidence Integrity Lab Generators (Master Test Cases 4, 5, 6, 7, 8) ──
  const handleRunIntegrityLabScenario = async (
    scenario: 'unique' | 'exact_dup' | 'resized_dup' | 'c2pa_ai' | 'synthid_ai',
  ) => {
    if (!activeClaimId) return
    const canvas = document.createElement('canvas')
    const isResized = scenario === 'resized_dup'
    canvas.width = isResized ? 320 : 480
    canvas.height = isResized ? 240 : 360
    const ctx = canvas.getContext('2d')!

    // Deterministic visual pattern for duplicate tests vs unique seed
    const seed = scenario === 'unique' ? Date.now() : 20261015
    drawSimulatedVehicleDamageCanvas(ctx, canvas.width, canvas.height, activeClaimId, seed)

    canvas.toBlob(
      async (blob) => {
        if (!blob) return
        let finalBlob: Blob = blob
        let filename = `vehicle_damage_${scenario}.jpg`

        if (scenario === 'c2pa_ai') {
          const buf = await blob.arrayBuffer()
          const marker = new TextEncoder().encode(
            'c2pa.assertions urn:c2pa:99887766 c2pa.actions.digitalSourceType=trainedAlgorithmicMedia Adobe Firefly',
          )
          finalBlob = new Blob([new Uint8Array(buf), marker], { type: 'image/jpeg' })
          filename = 'ai_edited_bumper_c2pa.jpg'
        } else if (scenario === 'synthid_ai') {
          const buf = await blob.arrayBuffer()
          const marker = new TextEncoder().encode(
            'SynthID Google DeepMind SynthID-v1 digitalSourceType=trainedAlgorithmicMedia',
          )
          finalBlob = new Blob([new Uint8Array(buf), marker], { type: 'image/jpeg' })
          filename = 'synthid_generated_damage.jpg'
        }

        const fileObj = new File([finalBlob], filename, { type: 'image/jpeg' })
        await runAiVerificationOnFile(fileObj)
        await handleUploadEvidenceFile(finalBlob, filename, 'upload_photo')
      },
      'image/jpeg',
      isResized ? 0.65 : 0.92,
    )
  }

  // ── Step 3: Final Customer Confirmation & 9-Section Dossier Generation ──
  const handleFinalizeAndGenerateDossier = async () => {
    if (!activeClaimId) return
    if (!motorForm.dpdp_consent_granted) {
      setError('Please grant the compulsory DPDP Act 2025 consent before submitting your claim dossier.')
      return
    }
    if (!declarationChecked || !motorForm.truthfulness_declaration_accepted) {
      setError('Please confirm the truthfulness declaration to certify your claim details.')
      return
    }
    if (motorForm.claim_settlement_mode === 'reimbursement') {
      if (!motorForm.bank_account_holder_name?.trim() || !motorForm.bank_account_number?.trim() || !motorForm.bank_ifsc_code?.trim()) {
        setOpenAccordion('conditional')
        setError('Reimbursement selected: Please complete Account Holder Name, Bank Account Number, and IFSC Code.')
        return
      }
    }
    if (motorForm.police_fir_lodged_flag) {
      if (!motorForm.fir_or_gd_number?.trim() || !motorForm.police_station_name?.trim()) {
        setOpenAccordion('conditional')
        setError('Police FIR is marked lodged: Please enter FIR / GD Number and Police Station Name.')
        return
      }
    }
    if (motorForm.loss_type === 'theft' && motorForm.financier_hypothecated && !motorForm.financier_name?.trim()) {
      setOpenAccordion('conditional')
      setError('Please specify the Financier Name for the hypothecated stolen vehicle.')
      return
    }
    if (aiVerificationResult?.decision === 'REJECT') {
      setError('Cannot submit claim with REJECTED evidence. Please return to Step 2 and upload valid vehicle evidence.')
      return
    }
    setIsSubmitting(true)
    setError('')

    const fieldMap = Object.fromEntries(fields.map((f) => [f.name, f.value || '']))
    const consentTs = motorForm.dpdp_consent_timestamp || new Date().toISOString()
    const payloadMotorForm: MotorClaimFormDetails = {
      ...motorForm,
      incident_time: incidentTime || motorForm.incident_time,
      pillion_rider_present: claimedVehicleType === 'two_wheeler' ? Boolean(motorForm.pillion_rider_present) : null,
      occupants_count: claimedVehicleType === 'four_wheeler' ? (motorForm.occupants_count ?? 1) : null,
      dpdp_consent_granted: true,
      dpdp_consent_timestamp: consentTs,
      truthfulness_declaration_accepted: true,
      insured_digital_signature: motorForm.insured_digital_signature?.trim() || motorForm.claimant_name?.trim() || '',
    }
    try {
      await api.updateAndConfirmClaim(activeClaimId, {
        policy_reference: fieldMap.policy_reference,
        claimed_registration: vehicleRegistration || undefined,
        incident_location: fieldMap.incident_location,
        incident_date: fieldMap.incident_date,
        vehicle_type: fieldMap.vehicle_type,
        vehicle_make_model: vehicleMakeModel || undefined,
        damage_description: fieldMap.damage_description,
        injuries_reported: injuriesReported,
        customer_confirmation: true,
        evidence_id: aiVerificationResult?.id,
        verification_decision: aiVerificationResult?.decision,
        claimed_vehicle_type: claimedVehicleType,
        total_estimated_inr: aiVerificationResult?.cost_estimate?.total_estimated_inr,
        cost_estimate: aiVerificationResult?.cost_estimate,
        motor_claim_form: payloadMotorForm,
      })
      await api.generateReport(activeClaimId)
      navigate(`/claims/${activeClaimId}`)
    } catch (err: any) {
      setIsSubmitting(false)
      setError(err.message || 'Failed to confirm claim and generate dossier.')
    }
  }

  // Computed state
  const capturedCount = fields.filter((f) => f.confidence !== 'missing' && f.value).length
  const isAllCaptured = capturedCount === 5
  const currentMissingFieldName = missingFields.length > 0 ? missingFields[activeMissingIndex] : null
  const currentMissingField = fields.find((f) => f.name === currentMissingFieldName)

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* ── WIZARD PROGRESS STEPPER (9-STEP PRODUCT FLOW) ── */}
      <div className="bg-white border border-gray-200 rounded-3xl p-4 shadow-xs flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2 sm:gap-4">
          {[
            { step: 1, title: t('step1_title'), sub: t('step1_sub') },
            { step: 2, title: t('step2_title'), sub: t('step2_sub') },
            { step: 3, title: t('step3_title'), sub: t('step3_sub') },
          ].map((item, idx) => {
            const active = wizardStep === item.step
            const done = wizardStep > item.step
            return (
              <div key={item.step} className="flex items-center gap-2 sm:gap-3">
                <button
                  type="button"
                  onClick={() => {
                    if (item.step === 1) setWizardStep(1)
                    if (item.step === 2 && isAllCaptured) handleProceedToEvidenceStep()
                    if (item.step === 3 && activeClaimId) {
                      if (!aiVerificationResult || aiVerificationResult.decision === 'REJECT') {
                        setError('Advancement blocked: Valid 5-stage verified vehicle evidence is required before proceeding to Customer Review.')
                        return
                      }
                      setWizardStep(3)
                    }
                  }}
                  className={`flex items-center gap-2.5 px-3.5 py-2 rounded-2xl text-left transition-all ${
                    active
                      ? 'bg-brand-600 text-white shadow-xs'
                      : done
                      ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                      : 'bg-gray-50 text-gray-500 border border-gray-200'
                  }`}
                >
                  <span
                    className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                      active
                        ? 'bg-white text-brand-700'
                        : done
                        ? 'bg-emerald-600 text-white'
                        : 'bg-gray-200 text-gray-600'
                    }`}
                  >
                    {done ? '✓' : item.step}
                  </span>
                  <div>
                    <div className="text-xs font-bold leading-tight">{item.title}</div>
                    <div
                      className={`text-[10px] hidden md:block ${
                        active ? 'text-blue-100' : 'text-gray-400'
                      }`}
                    >
                      {item.sub}
                    </div>
                  </div>
                </button>
                {idx < 2 && <ChevronRight className="w-4 h-4 text-gray-300 hidden sm:block" />}
              </div>
            )
          })}
        </div>

        {activeClaimId && (
          <div className="text-xs font-bold px-3 py-1.5 rounded-xl bg-blue-50 text-blue-800 border border-blue-200">
            Active Claim ID: <span className="font-mono">{activeClaimId}</span>
          </div>
        )}
      </div>

      {/* ── ERROR BANNER ── */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-2xl p-4 shadow-xs flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <h4 className="text-sm font-semibold text-red-800">Notice</h4>
            <p className="text-xs text-red-700 mt-0.5">{error}</p>
          </div>
          <button
            type="button"
            onClick={() => setError('')}
            className="text-xs text-red-600 hover:text-red-800 font-semibold underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* =====================================================================
          STEP 1: MULTILINGUAL VOICE & TEXT CONVERSATIONAL INTAKE (STEPS 2–4)
         ===================================================================== */}
      {wizardStep === 1 && (
        <>
          {/* Header & Provider Controls */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white border border-gray-200 rounded-3xl p-5 shadow-xs">
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-xl font-bold text-gray-900">
                  {t('step1_heading')}
                </h1>
                <ProviderBadge isMock={isDemoMode} model={activeModel} />
              </div>
              <p className="text-xs text-gray-500 mt-1">
                {t('step1_desc')}
              </p>
            </div>

            <div className="flex flex-col items-start sm:items-end gap-2.5">
              <div className="flex flex-wrap items-center gap-2">
                {/* Voice Assistant Audio Control (Mute / Unmute) */}
                <button
                  type="button"
                  onClick={() => {
                    if (autoVoiceEnabled) {
                      cancelAllSpeechOutput()
                      setAutoVoiceEnabled(false)
                    } else {
                      setAutoVoiceEnabled(true)
                    }
                  }}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all ${
                    autoVoiceEnabled
                      ? 'bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100'
                      : 'bg-rose-50 border-rose-200 text-rose-700 hover:bg-rose-100'
                  }`}
                  title={autoVoiceEnabled ? 'Voice output is active. Click to mute.' : 'Voice output is muted. Click to unmute.'}
                >
                  {autoVoiceEnabled ? <Volume2 className="w-3.5 h-3.5" /> : <VolumeX className="w-3.5 h-3.5" />}
                  <span>{autoVoiceEnabled ? 'Voice: ON' : 'Voice: MUTED'}</span>
                </button>

                {/* Hands-Free Auto-Pause Conversational Mode */}
                <button
                  type="button"
                  onClick={toggleHandsFreeMode}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all ${
                    handsFreeMode
                      ? 'bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100'
                      : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-100'
                  }`}
                  title="Automatically sends when you pause speaking and re-opens the mic after the assistant replies"
                >
                  <Radio className={`w-3.5 h-3.5 ${handsFreeMode ? 'animate-pulse text-blue-600' : ''}`} />
                  <span>{handsFreeMode ? 'Hands-Free: ON' : 'Hands-Free: OFF'}</span>
                </button>

                {/* Replay Last Voice Response */}
                <button
                  type="button"
                  onClick={handleReplayLastVoice}
                  disabled={isSynthesizing}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all ${
                    isPlayingAudio
                      ? 'bg-amber-500 border-amber-600 text-white animate-pulse'
                      : 'bg-white border-gray-200 text-blue-700 hover:bg-blue-50'
                  }`}
                  title="Replay the last spoken assistant response"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>{isPlayingAudio ? 'Stop Playing' : 'Replay Voice'}</span>
                </button>

                {/* Active Live Voice Engine Indicator */}
                <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  Live Natural Voice
                </span>
              </div>

              {/* Code-Mixed Indic Language Selector Pills (Sprint 1.8) */}
              <div className="flex flex-wrap items-center gap-1.5 pt-1">
                {CODE_MIXED_LANGUAGE_PILLS.map((pill) => {
                  const isSelected = activePillKey === pill.key
                  return (
                    <button
                      key={pill.key}
                      type="button"
                      onClick={() => {
                        setActivePillKey(pill.key)
                        setSelectedLanguage(pill.code)
                        setLockedLanguage(pill.code === 'indic-auto' ? null : pill.code)
                      }}
                      className={`px-2.5 py-1 rounded-xl text-xs font-semibold transition-all ${
                        isSelected
                          ? 'bg-blue-600 text-white shadow-xs ring-1 ring-blue-700'
                          : 'bg-gray-50 border border-gray-200 text-gray-700 hover:bg-gray-100'
                      }`}
                    >
                      {pill.label}
                    </button>
                  )
                })}

                {selectedLanguage === 'indic-auto' && lockedLanguage && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-xl bg-emerald-50 border border-emerald-200 text-[11px] font-bold text-emerald-800">
                    🔒 Locked: {lockedLanguage}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="grid lg:grid-cols-12 gap-6 items-start">
            {/* LEFT COLUMN: ACTIVE CONVERSATION THREAD */}
            <div className="lg:col-span-7 bg-white rounded-3xl border border-gray-200 p-6 shadow-xs flex flex-col h-[580px]">
              <div
                ref={chatScrollRef}
                className="flex-1 overflow-y-auto space-y-4 pr-1"
              >
                {messages.map((turn) => {
                  const isAssistant = turn.sender === 'assistant'
                  const isTurnSpeaking = isPlayingAudio && activeSpeechText === (turn.audioText || turn.text)

                  return (
                    <div
                      key={turn.id}
                      className={`flex items-start gap-3 ${
                        isAssistant ? 'justify-start' : 'justify-end'
                      }`}
                    >
                      {isAssistant && (
                        <div className="w-9 h-9 rounded-2xl bg-blue-600 flex items-center justify-center text-white shrink-0 shadow-xs">
                          <Bot className="w-5 h-5" />
                        </div>
                      )}

                      <div
                        className={`max-w-[85%] rounded-2xl p-4 text-xs leading-relaxed shadow-xs ${
                          isAssistant
                            ? 'bg-blue-50/80 border border-blue-200 text-gray-800'
                            : 'bg-blue-600 text-white'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-3 mb-1.5">
                          <span
                            className={`font-bold ${
                              isAssistant ? 'text-blue-900' : 'text-blue-100'
                            }`}
                          >
                            {isAssistant ? 'ClaimSathi Voice Assistant' : 'You'}
                          </span>

                          {isAssistant && turn.audioText && (
                            <button
                              type="button"
                              onClick={() => void speakText(turn.audioText!, turn.language, 1.0, 1.0, { toggleIfSame: true })}
                              disabled={isSynthesizing}
                              className="inline-flex items-center gap-1 text-[11px] font-semibold text-blue-700 hover:text-blue-950"
                            >
                              {isTurnSpeaking ? (
                                <>
                                  <VolumeX className="w-3.5 h-3.5 text-red-600 animate-pulse" /> Stop
                                </>
                              ) : (
                                <>
                                  <Volume2 className="w-3.5 h-3.5" /> Listen
                                </>
                              )}
                            </button>
                          )}
                        </div>

                        <p className={`text-xs ${isAssistant ? 'text-gray-800' : 'text-white'}`}>
                          {turn.text}
                        </p>

                        {(turn.latencyMs || turn.audioDuration || turn.language) && (
                          <div className="flex items-center gap-2 mt-2 pt-2 border-t border-black/10 text-[10px] opacity-75">
                            {turn.language && <span>Lang: {turn.language}</span>}
                            {turn.audioDuration && <span>&bull; Audio: {turn.audioDuration}s</span>}
                            {turn.latencyMs && <span>&bull; Latency: {turn.latencyMs}ms</span>}
                          </div>
                        )}
                      </div>

                      {!isAssistant && (
                        <div className="w-9 h-9 rounded-2xl bg-gray-800 flex items-center justify-center text-white shrink-0 shadow-xs">
                          <User className="w-5 h-5" />
                        </div>
                      )}
                    </div>
                  )
                })}

                {isRecording && (
                  <div className="flex items-center gap-3 justify-end animate-pulse">
                    <div className="bg-red-50 border border-red-300 rounded-2xl p-3 text-xs text-red-700 flex items-center gap-2">
                      <Radio className="w-4 h-4 text-red-600 animate-ping" />
                      <span>
                        Listening to your claim... (00:
                        {recordingSeconds < 10 ? `0${recordingSeconds}` : recordingSeconds})
                      </span>
                    </div>
                  </div>
                )}

                {isAnswerRecording && (
                  <div className="flex items-center gap-3 justify-end animate-pulse">
                    <div className="bg-red-50 border border-red-300 rounded-2xl p-3 text-xs text-red-700 flex items-center gap-2">
                      <Radio className="w-4 h-4 text-red-600 animate-ping" />
                      <span>
                        Listening to your answer... (00:
                        {answerRecordingSeconds < 10 ? `0${answerRecordingSeconds}` : answerRecordingSeconds})
                      </span>
                    </div>
                  </div>
                )}

                {isProcessingAnswerVoice && (
                  <div className="flex items-center gap-3 justify-start">
                    <div className="bg-gray-50 border border-gray-200 rounded-2xl p-3 text-xs text-gray-600 flex items-center gap-2">
                      <Spinner size="sm" />
                      <span>Understanding your voice answer with Gnani Prisma...</span>
                    </div>
                  </div>
                )}
              </div>

              {/* BOTTOM VOICE & TEXT CONTROLS */}
              <div className="mt-4 pt-4 border-t border-gray-200 space-y-3">
                {voiceNotice && (
                  <div className="flex items-center justify-between gap-2 bg-gray-50 border border-gray-200 text-gray-700 rounded-xl px-3.5 py-2 text-xs">
                    <span>{voiceNotice}</span>
                    <button
                      type="button"
                      onClick={() => setVoiceNotice('')}
                      className="text-[11px] font-semibold text-gray-500 hover:text-gray-800"
                    >
                      Dismiss
                    </button>
                  </div>
                )}

                {!hasStartedIntake ? (
                  <>
                    {!isRecording ? (
                      <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
                        <button
                          type="button"
                          onClick={startRecording}
                          className="w-full sm:w-auto inline-flex items-center justify-center gap-2.5 px-7 py-3 rounded-2xl bg-blue-600 text-white font-bold text-xs shadow-xs hover:bg-blue-700 transition-all"
                        >
                          <Mic className="w-4 h-4" /> {t('speak_claim_btn')}
                        </button>

                        <label className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-4 py-3 rounded-2xl border border-gray-300 text-gray-700 font-medium hover:bg-gray-50 transition-colors cursor-pointer text-xs">
                          <Upload className="w-4 h-4 text-gray-500" /> {t('upload_audio_btn')}
                          <input
                            ref={fileInputRef}
                            type="file"
                            accept=".wav,.mp3,.ogg,.flac,.aac,.m4a"
                            className="hidden"
                            onChange={handleFileUpload}
                          />
                        </label>
                      </div>
                    ) : (
                      <div className="flex flex-col items-center justify-center">
                        <div className="flex items-center gap-3 mb-1.5">
                          <span className="w-3 h-3 rounded-full bg-red-600 animate-ping" />
                          <span className="text-xs font-bold text-gray-700">
                            Recording (00:{recordingSeconds < 10 ? `0${recordingSeconds}` : recordingSeconds} / 00:30)
                            {handsFreeMode && <span className="ml-2 text-blue-700 font-semibold">&bull; {vadStatusLabel}</span>}
                          </span>
                        </div>
                        <div className="w-48 h-1.5 bg-red-100 rounded-full overflow-hidden mb-2.5">
                          <div
                            className="h-full bg-red-500 transition-all duration-75"
                            style={{ width: `${Math.max(8, Math.round(audioVolume * 100))}%` }}
                          />
                        </div>
                        <div className="flex items-center gap-3">
                          <button
                            type="button"
                            onClick={stopRecording}
                            className="inline-flex items-center gap-2 px-6 py-2 rounded-xl bg-red-600 text-white font-semibold text-xs shadow-xs hover:bg-red-700"
                          >
                            <Square className="w-4 h-4 fill-white" /> Finish &amp; Transcribe
                          </button>
                          <button
                            type="button"
                            onClick={cancelRecording}
                            className="px-4 py-2 rounded-xl border border-gray-300 text-xs font-medium text-gray-600 hover:bg-gray-50"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Direct Text Narrative Input */}
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={textIntakeInput}
                        onChange={(e) => setTextIntakeInput(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleProcessTextIntake()}
                        placeholder={t('type_placeholder')}
                        className="flex-1 rounded-xl border border-gray-300 px-3.5 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                      <button
                        type="button"
                        onClick={() => handleProcessTextIntake()}
                        disabled={!textIntakeInput.trim()}
                        className="px-4 py-2 rounded-xl bg-gray-900 text-white text-xs font-semibold disabled:opacity-40 hover:bg-gray-800"
                      >
                        {t('extract_btn')}
                      </button>
                    </div>
                  </>
                ) : missingFields.length > 0 && currentMissingField ? (
                  <div className="bg-blue-50/60 rounded-2xl border border-blue-200 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-bold text-blue-900">
                        {t('answering_followup')}: {t(`field_${currentMissingField.name}`)}
                      </span>
                      <span className="text-[10px] bg-blue-200/80 text-blue-900 font-bold px-2 py-0.5 rounded-full">
                        Question {activeMissingIndex + 1} of {missingFields.length}
                      </span>
                    </div>

                    {!isAnswerRecording && !isProcessingAnswerVoice ? (
                      <div className="flex flex-col sm:flex-row items-center gap-3">
                        <button
                          type="button"
                          onClick={startAnswerRecording}
                          className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-600 text-white font-bold text-xs shadow-xs hover:bg-emerald-700 shrink-0"
                        >
                          <Mic className="w-4 h-4" /> {t('speak_answer_btn')}
                        </button>

                        <div className="w-full flex-1">
                          <MissingFieldInput onSubmit={(val) => handleApplyAnswer(val)} />
                        </div>
                      </div>
                    ) : isAnswerRecording ? (
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-red-600 flex items-center gap-1.5">
                            <Radio className="w-4 h-4 animate-ping" /> Listening (00:
                            {answerRecordingSeconds < 10 ? `0${answerRecordingSeconds}` : answerRecordingSeconds})
                            {handsFreeMode && <span className="ml-1.5 text-blue-700 font-semibold">&bull; {vadStatusLabel}</span>}
                          </span>
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={stopAnswerRecording}
                              className="px-4 py-1.5 rounded-xl bg-red-600 text-white text-xs font-bold"
                            >
                              <Square className="w-3.5 h-3.5 fill-white inline mr-1" /> {t('done_speaking_btn')}
                            </button>
                            <button
                              type="button"
                              onClick={cancelAnswerRecording}
                              className="px-3 py-1.5 rounded-xl border border-gray-300 text-xs text-gray-600"
                            >
                              {t('cancel_btn')}
                            </button>
                          </div>
                        </div>
                        <div className="w-full h-1.5 bg-red-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-red-500 transition-all duration-75"
                            style={{ width: `${Math.max(8, Math.round(audioVolume * 100))}%` }}
                          />
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center justify-center gap-2 text-xs text-gray-600 py-1">
                        <Spinner size="sm" /> Transcribing your spoken answer...
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-emerald-50 border border-emerald-200 rounded-2xl p-4">
                    <div className="flex items-center gap-2 text-emerald-800 text-xs font-bold">
                      <CheckCircle className="w-5 h-5 text-emerald-600 shrink-0" />
                      <span>{t('all_captured_banner')}</span>
                    </div>

                    <div className="flex items-center gap-2 w-full sm:w-auto">
                      <button
                        type="button"
                        onClick={() => {
                          cancelAllSpeechOutput()
                          setHasStartedIntake(false)
                          setHandsFreeMode(false)
                          setVoiceNotice('')
                          setTranscript('')
                          setMissingFields([])
                          setLockedLanguage(null)
                          setExtractedSlotsSummary(null)
                          setVehicleMakeModel('')
                          setVehicleRegistration('')
                          setIncidentTime('')
                          setDrivableStatus('')
                          setMessages([])
                          setFields([
                            { name: 'policy_reference', label: 'Policy / Vehicle Number', value: null, confidence: 'missing', is_edited: false, follow_up_question: null },
                            { name: 'vehicle_type', label: 'Vehicle Type', value: null, confidence: 'missing', is_edited: false, follow_up_question: null },
                            { name: 'incident_location', label: 'Incident Location', value: null, confidence: 'missing', is_edited: false, follow_up_question: null },
                            { name: 'incident_date', label: 'Incident Date', value: null, confidence: 'missing', is_edited: false, follow_up_question: null },
                            { name: 'damage_description', label: 'Damage Description', value: null, confidence: 'missing', is_edited: false, follow_up_question: null },
                          ])
                        }}
                        className="px-3 py-2 text-xs font-semibold text-gray-600 hover:text-gray-900 border rounded-xl bg-white"
                      >
                        {t('reset_btn')}
                      </button>
                      <button
                        type="button"
                        onClick={handleProceedToEvidenceStep}
                        disabled={isSubmitting}
                        className="flex-1 sm:flex-initial inline-flex items-center justify-center gap-1.5 px-5 py-2.5 rounded-xl bg-brand-600 text-white font-bold text-xs shadow-xs hover:bg-brand-700"
                      >
                        {isSubmitting ? 'Initializing Claim...' : t('next_evidence_btn')}
                        <ChevronRight className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                )}

                {extractedSlotsSummary && (
                  <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-dashed border-gray-200 text-[11px]">
                    <span className="font-bold text-emerald-800">Auto-Synced Wizard Slots:</span>
                    {extractedSlotsSummary.vehicleType && (
                      <span className="px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-900 font-semibold">
                        {formatCategoryLabel(extractedSlotsSummary.vehicleType)}
                      </span>
                    )}
                    {extractedSlotsSummary.makeModel && (
                      <span className="px-2.5 py-0.5 rounded-full bg-teal-100 text-teal-900 font-semibold">
                        Model: {extractedSlotsSummary.makeModel}
                      </span>
                    )}
                    {extractedSlotsSummary.registration && (
                      <span className="px-2.5 py-0.5 rounded-full bg-blue-100 text-blue-900 font-mono font-bold">
                        {extractedSlotsSummary.registration}
                      </span>
                    )}
                    {extractedSlotsSummary.damages && extractedSlotsSummary.damages.length > 0 && (
                      <span className="px-2.5 py-0.5 rounded-full bg-amber-100 text-amber-900 font-semibold">
                        Damages: {extractedSlotsSummary.damages.join(', ')}
                      </span>
                    )}
                    {extractedSlotsSummary.motorSlots?.loss_type && (
                      <span className="px-2.5 py-0.5 rounded-full bg-purple-100 text-purple-900 font-semibold">
                        Loss: {extractedSlotsSummary.motorSlots.loss_type.replace(/_/g, ' ')}
                      </span>
                    )}
                    {extractedSlotsSummary.motorSlots?.incident_time && (
                      <span className="px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-800 font-semibold">
                        Time: {extractedSlotsSummary.motorSlots.incident_time}
                      </span>
                    )}
                    {extractedSlotsSummary.motorSlots?.driver_was_owner === false && (
                      <span className="px-2.5 py-0.5 rounded-full bg-indigo-100 text-indigo-900 font-semibold">
                        Driver: {extractedSlotsSummary.motorSlots.driver_name || extractedSlotsSummary.motorSlots.driver_relationship || 'Other Driver'}
                      </span>
                    )}
                    {extractedSlotsSummary.motorSlots?.police_fir_lodged_flag !== undefined && extractedSlotsSummary.motorSlots?.police_fir_lodged_flag !== null && (
                      <span className="px-2.5 py-0.5 rounded-full bg-gray-100 text-gray-800 font-semibold">
                        FIR: {extractedSlotsSummary.motorSlots.police_fir_lodged_flag ? 'Yes' : 'No'}
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* RIGHT COLUMN: LIVE CLAIM HUD / 5 STRUCTURED FIELDS */}
            <div className="lg:col-span-5 bg-white rounded-3xl border border-gray-200 p-6 shadow-xs space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-sm text-gray-900">{t('extracted_fields_title')}</h3>
                  <p className="text-[11px] text-gray-400">{t('extracted_fields_sub')}</p>
                </div>
                <div className="flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                  <ShieldCheck className="w-4 h-4" />
                  <span>{capturedCount} / 5 {t('captured_badge')}</span>
                </div>
              </div>

              <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden border border-gray-200">
                <div
                  className={`h-full transition-all duration-500 ${
                    isAllCaptured ? 'bg-emerald-500' : 'bg-blue-600'
                  }`}
                  style={{ width: `${(capturedCount / 5) * 100}%` }}
                />
              </div>

              <div className="space-y-2.5">
                {fields.map((field) => {
                  const isMissing = field.confidence === 'missing' || !field.value
                  const isCurrentAnswering = field.name === currentMissingFieldName
                  const localizedField = {
                    ...field,
                    label: t(`field_${field.name}`),
                  }
                  return (
                    <FieldRow
                      key={field.name}
                      field={localizedField}
                      isMissing={isMissing}
                      isAnswering={isCurrentAnswering}
                      onEdit={handleEditField}
                    />
                  )
                })}

                {/* Vehicle Make / Model Input (Captured in Step 1 for backend pricing only) */}
                <div
                  className={`rounded-2xl border p-3.5 transition-all ${
                    vehicleMakeModel.trim()
                      ? 'bg-emerald-50/50 border-emerald-200'
                      : 'bg-white border-gray-200'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <span className="text-[11px] font-bold uppercase tracking-wide text-gray-500">
                      Vehicle Model / Name
                    </span>
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                        vehicleMakeModel.trim()
                          ? 'bg-emerald-100 text-emerald-800'
                          : 'bg-gray-100 text-gray-500'
                      }`}
                    >
                      {vehicleMakeModel.trim() ? 'Captured' : 'Optional'}
                    </span>
                  </div>
                  <input
                    type="text"
                    value={vehicleMakeModel}
                    onChange={(e) => setVehicleMakeModel(e.target.value)}
                    placeholder="e.g. Bajaj Pulsar 220, Maruti Swift, Honda Activa"
                    className="w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-xs font-medium text-gray-800 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                </div>
              </div>

              {isAllCaptured && (
                <button
                  type="button"
                  onClick={handleProceedToEvidenceStep}
                  disabled={isSubmitting}
                  className="w-full inline-flex items-center justify-center gap-2 py-3 rounded-2xl bg-brand-600 text-white font-bold text-xs shadow-xs hover:bg-brand-700 transition-colors"
                >
                  {t('continue_step2_btn')} <ChevronRight className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        </>
      )}

      {/* =====================================================================
          STEP 2: EVIDENCE COLLECTION, LIVE CAMERA & INTEGRITY ENGINE (STEPS 5–6)
         ===================================================================== */}
      {wizardStep === 2 && (
        <div className="space-y-6">
          <div className="bg-white rounded-3xl border border-gray-200 p-6 shadow-xs">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
              <div>
                <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
                  <Fingerprint className="w-6 h-6 text-brand-600" />
                  Step 2: Evidence Collection &amp; Integrity Engine (Steps 5 &amp; 6)
                </h2>
                <p className="text-xs text-gray-500 mt-1">
                  Every uploaded photo or video is inspected for magic-byte file integrity, C2PA Content Credentials, Google SynthID watermarks, SHA-256 exact matches, and 64-bit DCT perceptual hash (pHash) visual reuse across claims.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    cancelAllSpeechOutput()
                    setWizardStep(1)
                  }}
                  className="px-3.5 py-2 rounded-xl border border-gray-200 text-xs font-semibold text-gray-600 hover:bg-gray-50"
                >
                  &larr; Back to Conversation
                </button>
                <button
                  type="button"
                  disabled={!aiVerificationResult || aiVerificationResult.decision === 'REJECT' || isVerifyingEvidence}
                  onClick={() => {
                    if (!aiVerificationResult) {
                      setError('Please upload vehicle damage evidence to run 5-stage AI verification before advancing.')
                      return
                    }
                    if (aiVerificationResult.decision === 'REJECT') {
                      setError('Advancement blocked: Evidence was rejected by the 5-stage AI engine. Please upload a valid photo of the claimed vehicle.')
                      return
                    }
                    cancelAllSpeechOutput()
                    setWizardStep(3)
                  }}
                  className="inline-flex items-center gap-1.5 px-5 py-2 rounded-xl bg-brand-600 text-white text-xs font-bold hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed shadow-xs"
                >
                  Proceed to Step 3: Customer Review <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Claimed Vehicle Category & Registration Identity Binding */}
            {(() => {
              const step1VehicleValue = fields.find((f) => f.name === 'vehicle_type')?.value
              const step1LockedCat = deriveVehicleCategoryFromField(step1VehicleValue)
              const isVehicleLockedFromStep1 = Boolean(step1LockedCat)
              return (
                <div className="bg-gray-50/90 border border-gray-200 rounded-2xl p-4 mb-6 space-y-3">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                    <label className="block text-xs font-bold text-gray-800">
                      Claimed Vehicle &amp; Registration Details
                    </label>
                    <span className="text-[11px] font-semibold text-gray-500">
                      {isVehicleLockedFromStep1
                        ? `Constrained to ${formatCategoryLabel(step1LockedCat!)} from Step 1 • Cross-vehicle & non-vehicle photos rejected`
                        : 'Cross-vehicle mismatch (Car vs. Bike) is strictly rejected'}
                    </span>
                  </div>
                  <div className="grid sm:grid-cols-3 gap-3">
                    {isVehicleLockedFromStep1 ? (
                      <div className="sm:col-span-2 flex items-center justify-between gap-3 px-4 py-2.5 rounded-xl border border-brand-600 bg-brand-50 text-brand-900 shadow-xs">
                        <div className="flex items-center gap-2.5 min-w-0">
                          {claimedVehicleType === 'two_wheeler' ? (
                            <Bike className="w-4 h-4 text-brand-700 shrink-0" />
                          ) : (
                            <Car className="w-4 h-4 text-brand-700 shrink-0" />
                          )}
                          <div className="min-w-0">
                            <div className="text-xs font-extrabold truncate">
                              Locked from Step 1: {formatCategoryLabel(claimedVehicleType)}
                              {vehicleMakeModel.trim() ? ` • ${vehicleMakeModel.trim()}` : ''}
                            </div>
                            <div className="text-[10px] font-medium text-brand-700">
                              Only {claimedVehicleType === 'two_wheeler' ? 'Two-Wheeler (Bike)' : 'Four-Wheeler (Car)'} photos accepted
                            </div>
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            cancelAllSpeechOutput()
                            setWizardStep(1)
                          }}
                          className="text-[11px] font-bold text-brand-700 underline hover:text-brand-900 shrink-0"
                        >
                          Change in Step 1
                        </button>
                      </div>
                    ) : (
                      <>
                        <button
                          type="button"
                          disabled={isVerifyingEvidence}
                          onClick={() => handleToggleVehicleCategory('four_wheeler')}
                          className={`flex items-center justify-center gap-2 px-3.5 py-2.5 rounded-xl border text-xs font-bold transition-all disabled:opacity-60 disabled:cursor-not-allowed ${
                            claimedVehicleType === 'four_wheeler'
                              ? 'bg-brand-50 border-brand-600 text-brand-800 shadow-xs'
                              : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-100'
                          }`}
                        >
                          <Car className="w-4 h-4" />
                          Four-Wheeler (Car)
                        </button>
                        <button
                          type="button"
                          disabled={isVerifyingEvidence}
                          onClick={() => handleToggleVehicleCategory('two_wheeler')}
                          className={`flex items-center justify-center gap-2 px-3.5 py-2.5 rounded-xl border text-xs font-bold transition-all disabled:opacity-60 disabled:cursor-not-allowed ${
                            claimedVehicleType === 'two_wheeler'
                              ? 'bg-brand-50 border-brand-600 text-brand-800 shadow-xs'
                              : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-100'
                          }`}
                        >
                          <Bike className="w-4 h-4" />
                          Two-Wheeler (Bike)
                        </button>
                      </>
                    )}

                    <div>
                      <input
                        type="text"
                        value={vehicleRegistration}
                        onChange={(e) => setVehicleRegistration(e.target.value.toUpperCase())}
                        placeholder="Reg Plate (e.g. KA-01-MJ-4412)"
                        className="w-full rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-xs font-mono font-semibold text-gray-800"
                      />
                    </div>
                  </div>
                </div>
              )
            })()}

            {/* Unbundled DPDP Rules 2025 Pre-Capture Consent Bar */}
            <div className="bg-blue-50/70 border border-blue-200 rounded-2xl px-4 py-3 mb-5 flex flex-wrap items-center justify-between gap-3">
              <label className="flex items-start gap-2.5 cursor-pointer text-xs text-blue-950">
                <input
                  type="checkbox"
                  checked={dpdpPreCaptureConsent}
                  onChange={(e) => setDpdpPreCaptureConsent(e.target.checked)}
                  className="mt-0.5 w-4 h-4 rounded text-blue-600 focus:ring-blue-500"
                />
                <span>
                  <strong>DPDP 2025 Pre-Capture Consent:</strong> I consent to live camera capture &amp; plate/damage verification for this motor claim only (auto-erasure available on withdrawal).
                </span>
              </label>
              {isHandoffCameraLocked && (
                <button
                  type="button"
                  onClick={() => setIsHandoffCameraLocked(false)}
                  className="text-[11px] font-semibold text-blue-700 underline hover:text-blue-900"
                >
                  Unlock Desktop Upload
                </button>
              )}
            </div>

            {/* Upload & Live Camera Action Cards */}
            <div className="grid md:grid-cols-2 gap-5 mb-6">
              {/* Option A: Upload Photo or Video from Device (Locked when WhatsApp Handoff Active) */}
              <div
                className={`rounded-2xl border-2 border-dashed p-5 flex flex-col justify-between ${
                  isHandoffCameraLocked
                    ? 'border-gray-300 bg-gray-100/80 opacity-75'
                    : 'border-blue-200 bg-blue-50/40'
                }`}
              >
                <div>
                  <div className="flex items-center gap-2 text-blue-900 font-bold text-sm mb-1">
                    <Upload className="w-4 h-4 text-blue-600" />
                    {isHandoffCameraLocked
                      ? 'Gallery Upload Disabled (Live Camera Lock Active)'
                      : 'Upload Vehicle Damage Photos or Videos'}
                  </div>
                  <p className="text-xs text-gray-600 mb-4">
                    {isHandoffCameraLocked
                      ? 'To prevent WhatsApp metadata stripping and gallery replay, tokenized Stage 5 handoff links accept Live Camera frames only.'
                      : 'Supports JPEG, PNG, WebP images and MP4, MOV, WebM videos. Validates magic bytes, EXIF metadata, advisory provenance, SHA-256 & 64-bit DCT pHash.'}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  {isHandoffCameraLocked ? (
                    <span className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-amber-100 border border-amber-300 text-amber-900 text-xs font-bold">
                      🔒 Gallery File Picker Locked — Use Live Camera &rarr;
                    </span>
                  ) : (
                    <label className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 text-white text-xs font-bold cursor-pointer hover:bg-blue-700 shadow-xs">
                      <Upload className="w-4 h-4" /> Choose Photo / Video Files
                      <input
                        ref={evidenceInputRef}
                        type="file"
                        multiple
                        disabled={!dpdpPreCaptureConsent}
                        accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm"
                        className="hidden"
                        onChange={handleEvidenceInputChange}
                      />
                    </label>
                  )}
                  {uploadingEvidence && (
                    <span className="inline-flex items-center gap-1.5 text-xs text-blue-700 font-semibold">
                      <Spinner size="sm" /> Screening evidence...
                    </span>
                  )}
                </div>
              </div>

              {/* Option B: Guided Live Camera Capture (Step 5 & 6D of PDF) */}
              <div className="rounded-2xl border border-emerald-200 bg-emerald-50/40 p-5 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="flex items-center gap-2 text-emerald-900 font-bold text-sm">
                      <Camera className="w-4 h-4 text-emerald-600" />
                      Guided Live Camera Capture (Anti-Fraud Session)
                    </span>
                    {captureSession && (
                      <span className="text-[11px] font-mono font-bold bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full">
                        {captureSession.session_id}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-600 mb-3">
                    Generates a server-bound capture session ID with 3 randomized vehicle angle instructions to prevent pre-recorded or recycled media fraud.
                  </p>

                  {captureSession && (
                    <div className="bg-white rounded-xl border border-emerald-200 p-3 mb-3 space-y-1">
                      <div className="text-[11px] font-bold text-emerald-800 uppercase">
                        Server-Assigned Capture Prompts ({captureSession.session_id}):
                      </div>
                      {captureSession.instructions.map((inst, idx) => (
                        <div key={idx} className="text-xs text-gray-700 flex items-center gap-1.5">
                          <span className="w-4 h-4 rounded-full bg-emerald-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0">
                            {idx + 1}
                          </span>
                          <span>{typeof inst === 'string' ? inst : (inst as any).prompt}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {cameraActive && (
                    <div className="mb-3 rounded-xl overflow-hidden border border-emerald-300 bg-black">
                      <video
                        ref={videoPreviewRef}
                        autoPlay
                        playsInline
                        muted
                        className="w-full h-44 object-cover"
                      />
                    </div>
                  )}
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {!cameraActive ? (
                    <button
                      type="button"
                      onClick={startGuidedCameraSession}
                      className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-emerald-600 text-white text-xs font-bold hover:bg-emerald-700 shadow-xs"
                    >
                      <Camera className="w-4 h-4" /> Start Guided Live Camera
                    </button>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={captureLiveFrameFromCamera}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-600 text-white text-xs font-bold hover:bg-emerald-700"
                      >
                        📸 Capture Live Frame
                      </button>
                      <button
                        type="button"
                        onClick={stopLiveCamera}
                        className="px-3 py-2 rounded-xl border border-gray-300 text-xs text-gray-600 bg-white"
                      >
                        Close Camera
                      </button>
                    </>
                  )}

                  <button
                    type="button"
                    onClick={captureLiveFrameFromCamera}
                    className="inline-flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl bg-white border border-emerald-300 text-emerald-800 text-xs font-semibold hover:bg-emerald-100"
                  >
                    <Video className="w-3.5 h-3.5" /> Simulate Live Session Capture
                  </button>
                  <button
                    type="button"
                    onClick={handleGenerateWhatsappHandoff}
                    className="inline-flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl bg-white border border-blue-200 text-blue-700 text-xs font-semibold hover:bg-blue-50"
                    title="WhatsApp strips EXIF & C2PA; send a 1-tap browser link directly to Stage 5 Live Camera"
                  >
                    <Send className="w-3.5 h-3.5" /> WhatsApp &rarr; Live Camera Link
                  </button>
                </div>

                {whatsappHandoff && (
                  <div className="mt-3 p-3 rounded-xl bg-white border border-blue-200 text-[11px] space-y-1">
                    <div className="font-bold text-blue-900">
                      WhatsApp 1-Tap Browser Handoff Ready ({whatsappHandoff.session_id}) &bull; Raw WhatsApp Media Blocked
                    </div>
                    <div className="font-mono text-[10px] text-blue-700 break-all">
                      {whatsappHandoff.handoff_url}
                    </div>
                    <div className="text-gray-600">
                      DPDP Masked IDs: Phone {whatsappHandoff.masked_phone} &bull; Reg {whatsappHandoff.masked_registration}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* ── 5-Stage AI Evidence Intelligence & Repair Estimate Panel (Sprint 1.8) ── */}
            {isVerifyingEvidence && (
              <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6 text-center space-y-2 mb-6">
                <Spinner size="md" />
                <div className="text-sm font-bold text-blue-900">
                  Running 5-Stage AI Evidence Screening &amp; YOLO Damage Estimation...
                </div>
                <p className="text-xs text-blue-700">
                  Inspecting magic bytes, EXIF metadata, YOLOv8 vehicle &amp; damage detectors, and EfficientNetV2 spoof risk.
                </p>
              </div>
            )}

            {aiVerificationResult && !isVerifyingEvidence && (
              <div className="bg-white rounded-2xl border border-gray-200 p-5 shadow-xs space-y-5 mb-6">
                {/* Decision Banner */}
                {aiVerificationResult.decision === 'REJECT' && (
                  <div className="flex items-start gap-3 bg-red-50 border-2 border-red-300 text-red-900 rounded-2xl p-4">
                    <XCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
                    <div className="space-y-1">
                      <div className="font-extrabold text-sm text-red-950">
                        Evidence Rejected — Cannot Proceed with Claim
                      </div>
                      {aiVerificationResult.vehicle_category_mismatch ||
                      aiVerificationResult.reasons?.some((r) => r.includes('VEHICLE_CATEGORY_MISMATCH')) ? (
                        <p className="text-xs text-red-800 leading-relaxed">
                          <strong>Vehicle Category Mismatch:</strong> You selected{' '}
                          <strong>{formatCategoryLabel(claimedVehicleType)}</strong>, but the AI vision pipeline detected a{' '}
                          <strong>{formatCategoryLabel(aiVerificationResult.detected_vehicle_category)}</strong> in the uploaded photo.
                          Please upload a photo of the claimed {formatCategoryLabel(claimedVehicleType)}.
                        </p>
                      ) : aiVerificationResult.reasons?.some((r) => r.includes('NON_VEHICLE_PERSON_SELFIE')) ? (
                        <p className="text-xs text-red-800 leading-relaxed">
                          <strong>No Vehicle Detected (Person / Selfie Captured):</strong> The camera captured a person rather than a motor vehicle. If you are testing on a laptop front webcam, please upload a vehicle photo or use the <strong>WhatsApp &rarr; Live Camera Link</strong> on your phone to point at your damaged vehicle.
                        </p>
                      ) : aiVerificationResult.reasons?.some((r) => r.includes('NO_VEHICLE_DETECTED_REJECTED') || r.includes('NON_VEHICLE_OBJECT_DETECTED')) ? (
                        <p className="text-xs text-red-800 leading-relaxed">
                          <strong>No Vehicle Detected — Photo Rejected:</strong> No bike, car, or vehicle damage was detected in this photo. Only clear photos of your claimed{' '}
                          <strong>{formatCategoryLabel(claimedVehicleType)}</strong> are accepted — this image was NOT added to your claim.
                        </p>
                      ) : (
                        <p className="text-xs text-red-800 leading-relaxed">
                          {aiVerificationResult.reasons.join(', ')}
                        </p>
                      )}
                      <div className="text-[11px] font-semibold text-red-700 pt-0.5">
                        🚫 Wizard advancement to Step 3 is blocked until valid vehicle evidence is uploaded.
                      </div>
                    </div>
                  </div>
                )}

                {aiVerificationResult.decision === 'PASS' && (
                  <div className="flex items-center justify-between flex-wrap gap-2 bg-emerald-50 border border-emerald-300 text-emerald-900 rounded-2xl p-4">
                    <div className="flex items-center gap-2.5">
                      <CheckCircle className="w-5 h-5 text-emerald-600 shrink-0" />
                      <div>
                        <div className="text-xs font-bold text-emerald-950">
                          Evidence Passed 5-Stage Screening — Approved for Auto-Estimate
                        </div>
                        <div className="text-[11px] text-emerald-700">
                          {formatCategoryLabel(aiVerificationResult.claimed_vehicle_type || claimedVehicleType)} verified &bull; Spoof Risk: {(aiVerificationResult.spoof_risk * 100).toFixed(1)}% &bull; Detected Damages: {aiVerificationResult.damage_count}
                        </div>
                      </div>
                    </div>
                    <span className="px-3 py-1 rounded-full text-xs font-extrabold bg-emerald-600 text-white shadow-xs">
                      PASS (Approved)
                    </span>
                  </div>
                )}

                {aiVerificationResult.decision === 'REVIEW' && (
                  <div className="flex items-center justify-between flex-wrap gap-2 bg-amber-50 border border-amber-300 text-amber-900 rounded-2xl p-4">
                    <div className="flex items-center gap-2.5">
                      <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
                      <div>
                        <div className="text-xs font-bold text-amber-950">
                          {!aiVerificationResult.vehicle_detected && aiVerificationResult.damage_count === 0
                            ? 'No Vehicle Detected — Please Capture a Clear Vehicle Photo'
                            : 'Flagged for Human Adjuster Review — Provisional Estimate Generated'}
                        </div>
                        <div className="text-[11px] text-amber-800">
                          {aiVerificationResult.reasons.join(' • ')}
                        </div>
                      </div>
                    </div>
                    <span className="px-3 py-1 rounded-full text-xs font-extrabold bg-amber-600 text-white shadow-xs">
                      REVIEW (Provisional)
                    </span>
                  </div>
                )}

                {/* Spoken Indic Evidence Narration (Sprint 1.8) */}
                {evidenceNarration && (
                  <div className="p-3.5 rounded-2xl bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 flex items-center justify-between gap-3">
                    <div className="flex items-start gap-2.5">
                      <Volume2 className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
                      <div>
                        <div className="text-[11px] font-bold text-blue-950 uppercase tracking-wide flex items-center gap-1.5">
                          <span>AI Spoken Evidence Narration ({evidenceNarration.lang})</span>
                          <span className="w-1.5 h-1.5 rounded-full bg-blue-600" />
                          <span className="text-[10px] text-blue-700 font-semibold lowercase">gnani timbre tts</span>
                        </div>
                        <p className="text-xs text-blue-900 mt-0.5 italic">"{evidenceNarration.spoken}"</p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => void speakText(evidenceNarration.spoken, evidenceNarration.lang, 1.0, 1.0, { toggleIfSame: true })}
                      className="shrink-0 px-3.5 py-1.5 rounded-xl bg-blue-600 text-white font-semibold text-xs hover:bg-blue-700 shadow-xs flex items-center gap-1.5 transition-all"
                    >
                      <Volume2 className="w-3.5 h-3.5" />
                      <span>{isPlayingAudio && activeSpeechText === evidenceNarration.spoken ? 'Stop' : 'Replay Audio'}</span>
                    </button>
                  </div>
                )}

                {/* Dual Grid: Preview with Bounding Boxes + Itemized INR Estimate */}
                <div className="grid lg:grid-cols-2 gap-5">
                  {/* Box A: Image Preview with Bounding Boxes */}
                  <div className="space-y-2">
                    <div className="text-xs font-bold text-gray-700 flex items-center justify-between">
                      <span>AI Vision Detection Overlays</span>
                      <span className="text-[11px] text-gray-500 font-mono">
                        {aiVerificationResult.filename}
                      </span>
                    </div>
                    <div className="bg-gray-50 border border-gray-200 rounded-xl p-2 min-h-[220px] flex items-center justify-center overflow-hidden">
                      {evidencePreviewUrl ? (
                        <div className="relative inline-block max-w-full">
                          <img
                            src={evidencePreviewUrl}
                            alt="Verified evidence preview"
                            className="max-h-64 w-auto rounded-lg object-contain block"
                          />
                          {aiVerificationResult.stage_results?.stage1_integrity?.width &&
                            aiVerificationResult.stage_results?.stage1_integrity?.height && (
                              <>
                                {(aiVerificationResult.stage_results?.stage3a_vehicle?.detections || []).map((b, idx) => {
                                  const imgW = aiVerificationResult.stage_results!.stage1_integrity!.width!
                                  const imgH = aiVerificationResult.stage_results!.stage1_integrity!.height!
                                  const [x1, y1, x2, y2] = b.bbox
                                  return (
                                    <div
                                      key={`veh-box-${idx}`}
                                      style={{
                                        left: `${(x1 / imgW) * 100}%`,
                                        top: `${(y1 / imgH) * 100}%`,
                                        width: `${((x2 - x1) / imgW) * 100}%`,
                                        height: `${((y2 - y1) / imgH) * 100}%`,
                                      }}
                                      className="absolute border-2 border-blue-500 bg-blue-500/10 pointer-events-none rounded-xs"
                                    >
                                      <span className="absolute -top-5 left-0 bg-blue-600 text-white text-[9px] font-bold px-1.5 py-0.5 rounded-xs whitespace-nowrap">
                                        {b.class_name} {(b.confidence * 100).toFixed(0)}%
                                      </span>
                                    </div>
                                  )
                                })}
                                {(aiVerificationResult.stage_results?.stage3b_damage?.detections || []).map((b, idx) => {
                                  const imgW = aiVerificationResult.stage_results!.stage1_integrity!.width!
                                  const imgH = aiVerificationResult.stage_results!.stage1_integrity!.height!
                                  const [x1, y1, x2, y2] = b.bbox
                                  return (
                                    <div
                                      key={`dmg-box-${idx}`}
                                      style={{
                                        left: `${(x1 / imgW) * 100}%`,
                                        top: `${(y1 / imgH) * 100}%`,
                                        width: `${((x2 - x1) / imgW) * 100}%`,
                                        height: `${((y2 - y1) / imgH) * 100}%`,
                                      }}
                                      className="absolute border-2 border-red-500 bg-red-500/15 pointer-events-none rounded-xs"
                                    >
                                      <span className="absolute -top-5 left-0 bg-red-600 text-white text-[9px] font-bold px-1.5 py-0.5 rounded-xs whitespace-nowrap">
                                        {b.class_name} {(b.confidence * 100).toFixed(0)}%
                                      </span>
                                    </div>
                                  )
                                })}
                              </>
                            )}
                        </div>
                      ) : (
                        <div className="text-gray-400 text-xs">Preview unavailable</div>
                      )}
                    </div>
                  </div>

                  {/* Box B: Itemized Cost Estimate Table */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-gray-700 flex items-center gap-1.5">
                        <IndianRupee className="w-3.5 h-3.5 text-brand-600" />
                        Itemized Repair Cost Estimate (INR)
                      </span>
                      {aiVerificationResult.cost_estimate && (
                        <span className="text-[11px] font-bold px-2 py-0.5 rounded-md bg-gray-100 text-gray-700">
                          Severity: {aiVerificationResult.cost_estimate.overall_severity}
                        </span>
                      )}
                    </div>

                    <div className="overflow-x-auto border border-gray-200 rounded-xl">
                      <table className="w-full text-left border-collapse text-xs">
                        <thead>
                          <tr className="border-b border-gray-200 bg-gray-50/80 text-gray-500 text-[11px]">
                            <th className="py-2 px-3 font-semibold">Damage Type</th>
                            <th className="py-2 px-2 font-semibold">Severity</th>
                            <th className="py-2 px-2 font-semibold">Base + Labor</th>
                            <th className="py-2 px-3 font-semibold text-right">Subtotal</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {(!aiVerificationResult.cost_estimate?.line_items ||
                            aiVerificationResult.cost_estimate.line_items.length === 0) ? (
                            <tr>
                              <td colSpan={4} className="py-4 text-center text-gray-400 text-xs">
                                {aiVerificationResult.decision === 'REJECT'
                                  ? 'Upload rejected — ₹0 estimate issued.'
                                  : !aiVerificationResult.vehicle_detected
                                  ? 'No motor vehicle detected in this photo.'
                                  : 'No damages detected on this vehicle.'}
                              </td>
                            </tr>
                          ) : (
                            aiVerificationResult.cost_estimate.line_items.map((item, idx) => (
                              <tr key={idx} className="hover:bg-gray-50/60">
                                <td className="py-2 px-3 font-medium text-gray-900 capitalize">
                                  {item.damage_type.replace('_', ' ')}
                                </td>
                                <td className="py-2 px-2">
                                  <span
                                    className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold ${
                                      item.severity === 'Severe'
                                        ? 'bg-red-100 text-red-700'
                                        : item.severity === 'Moderate'
                                          ? 'bg-amber-100 text-amber-700'
                                          : 'bg-blue-100 text-blue-700'
                                    }`}
                                  >
                                    {item.severity}
                                  </span>
                                </td>
                                <td className="py-2 px-2 text-gray-600">
                                  {formatInr(item.base_part_inr)} + {formatInr(item.labor_inr)}
                                </td>
                                <td className="py-2 px-3 font-bold text-gray-900 text-right">
                                  {formatInr(item.subtotal_inr)}
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>

                    <div className="flex items-center justify-between p-3 rounded-xl bg-gray-50 border border-gray-200">
                      <div>
                        <span className="text-xs font-bold text-gray-700 block">
                          Preliminary Repair Estimate:
                        </span>
                        <span className="text-[11px] text-gray-500">
                          {aiVerificationResult.cost_estimate?.estimate_band_min_inr ? (
                            <>Estimated Range: {formatInr(aiVerificationResult.cost_estimate.estimate_band_min_inr)} &ndash; {formatInr(aiVerificationResult.cost_estimate.estimate_band_max_inr || aiVerificationResult.cost_estimate.total_estimated_inr)}</>
                          ) : (
                            'Surveyor verification pending'
                          )}
                        </span>
                      </div>
                      <span className="text-lg font-extrabold text-brand-700">
                        {formatInr(aiVerificationResult.cost_estimate?.total_estimated_inr || 0)}
                      </span>
                    </div>

                    {aiVerificationResult.vehicle_identity && (
                      <div className="p-2.5 rounded-xl bg-blue-50/70 border border-blue-200 text-[11px] text-blue-900 space-y-0.5">
                        <div className="font-bold">
                          Vehicle Identity Binding: {aiVerificationResult.vehicle_identity.plate_match_status}
                          {aiVerificationResult.vehicle_identity.claimed_registration ? ` (${aiVerificationResult.vehicle_identity.claimed_registration})` : ''}
                        </div>
                        <div>{aiVerificationResult.vehicle_identity.identity_note}</div>
                      </div>
                    )}

                    <div className="text-[10px] text-gray-500 leading-snug space-y-0.5">
                      <div>
                        {aiVerificationResult.cost_estimate?.bfsi_regulatory_disclaimer ||
                          'Preliminary AI Repair Cost Band for Surveyor/Adjuster Review Only. Final settlement rests with the licensed insurer/TPA.'}
                      </div>
                      {aiVerificationResult.stage_results?.stage2_metadata?.provenance_disclaimer && (
                        <div>{aiVerificationResult.stage_results.stage2_metadata.provenance_disclaimer}</div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Built-in Integrity Verification Lab (1-Click Master Test Scenarios 4, 5, 6, 7, 8) */}
            <div className="bg-gray-50 rounded-2xl border border-gray-200 p-4 mb-6">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5">
                <span className="text-xs font-bold text-gray-800 flex items-center gap-1.5">
                  <Sparkles className="w-4 h-4 text-purple-600" />
                  1-Click Evidence Integrity Test Lab (Generates real binary images &amp; runs live backend inspection):
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => handleRunIntegrityLabScenario('unique')}
                  disabled={uploadingEvidence}
                  className="px-3 py-1.5 rounded-xl bg-white border border-gray-300 text-xs font-semibold text-gray-800 hover:bg-gray-100"
                >
                  1. Upload Valid Unique Photo (Test 4)
                </button>
                <button
                  type="button"
                  onClick={() => handleRunIntegrityLabScenario('exact_dup')}
                  disabled={uploadingEvidence}
                  className="px-3 py-1.5 rounded-xl bg-white border border-amber-300 text-xs font-semibold text-amber-900 hover:bg-amber-50"
                >
                  <Copy className="w-3 h-3 inline mr-1" />
                  2. Upload Exact Duplicate Photo (Click twice for SHA-256 Match - Test 5)
                </button>
                <button
                  type="button"
                  onClick={() => handleRunIntegrityLabScenario('resized_dup')}
                  disabled={uploadingEvidence}
                  className="px-3 py-1.5 rounded-xl bg-white border border-orange-300 text-xs font-semibold text-orange-900 hover:bg-orange-50"
                >
                  <RefreshCw className="w-3 h-3 inline mr-1" />
                  3. Upload Resized/Recompressed Duplicate (64-bit pHash Match - Test 6)
                </button>
                <button
                  type="button"
                  onClick={() => handleRunIntegrityLabScenario('c2pa_ai')}
                  disabled={uploadingEvidence}
                  className="px-3 py-1.5 rounded-xl bg-white border border-red-300 text-xs font-semibold text-red-800 hover:bg-red-50"
                >
                  4. Upload C2PA AI-Generated Image (Test 7)
                </button>
                <button
                  type="button"
                  onClick={() => handleRunIntegrityLabScenario('synthid_ai')}
                  disabled={uploadingEvidence}
                  className="px-3 py-1.5 rounded-xl bg-white border border-purple-300 text-xs font-semibold text-purple-800 hover:bg-purple-50"
                >
                  5. Upload Google SynthID Image (Test 7)
                </button>
              </div>
            </div>

            {/* Screened Evidence Inventory List */}
            <div>
              <h3 className="font-bold text-sm text-gray-900 mb-3">
                Screened Evidence Inventory ({evidenceList.length} items)
              </h3>
              {evidenceList.length === 0 ? (
                <div className="text-center py-10 bg-gray-50 rounded-2xl border border-gray-200 text-xs text-gray-500">
                  No evidence uploaded yet. Upload a photo/video or click one of the 1-Click Evidence Integrity Test Lab buttons above.
                </div>
              ) : (
                <div className="grid sm:grid-cols-2 gap-4">
                  {evidenceList.map((ev) => {
                    const scr = ev.screening
                    const aiDec = evidenceAiDecisions[ev.evidence_id]
                    const isFlagged = Boolean(scr?.requires_human_review) || aiDec === 'REVIEW'
                    return (
                      <div
                        key={ev.evidence_id}
                        className={`rounded-2xl border p-4 flex gap-4 ${
                          isFlagged
                            ? 'bg-amber-50/60 border-amber-300'
                            : 'bg-white border-gray-200'
                        }`}
                      >
                        {ev.media_type === 'image' && activeClaimId ? (
                          <img
                            src={api.getEvidenceFileUrl(activeClaimId, ev.evidence_id)}
                            alt={ev.label}
                            className="w-24 h-24 rounded-xl object-cover border border-gray-200 shrink-0 bg-gray-100"
                          />
                        ) : (
                          <div className="w-24 h-24 rounded-xl bg-slate-900 text-white flex flex-col items-center justify-center text-xs font-bold shrink-0">
                            <Video className="w-6 h-6 mb-1 text-blue-400" />
                            {ev.label}
                          </div>
                        )}

                        <div className="flex-1 min-w-0 space-y-1">
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-bold text-xs text-gray-900">
                              {ev.label} &bull; {ev.original_filename}
                            </span>
                            <span
                              className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                                isFlagged
                                  ? 'bg-red-100 text-red-800'
                                  : 'bg-emerald-100 text-emerald-800'
                              }`}
                            >
                              {isFlagged ? '⚠️ Human Review Flag' : '✓ Passed'}
                            </span>
                          </div>

                          {scr && (
                            <>
                              <p className="text-xs font-semibold text-gray-800">
                                {scr.screening_outcome_label}
                              </p>
                              <p className="text-[11px] text-gray-600">
                                {scr.provenance_result} &rarr; <strong>{scr.provenance_system_response}</strong>
                              </p>
                              <div className="text-[10px] font-mono text-gray-500 space-y-0.5 pt-1">
                                <div className="truncate">
                                  SHA-256: {scr.sha256_hash.slice(0, 24)}...
                                </div>
                                {scr.perceptual_hash && (
                                  <div>
                                    64-bit DCT pHash: <span className="font-bold">{scr.perceptual_hash}</span>
                                    {scr.hamming_distance !== null &&
                                      scr.hamming_distance !== undefined && (
                                        <span className="ml-2 text-amber-800 font-bold">
                                          (Hamming dist: {scr.hamming_distance})
                                        </span>
                                      )}
                                  </div>
                                )}
                                <div>
                                  Duplicate Check:{' '}
                                  <strong className="uppercase">{scr.duplicate_status}</strong>
                                  {scr.matched_claim_reference && (
                                    <span className="ml-1 text-red-700">
                                      (Matched {scr.matched_claim_reference})
                                    </span>
                                  )}
                                </div>
                              </div>
                            </>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          STEP 3: CUSTOMER REVIEW, DECLARATION & DOSSIER GENERATION (STEPS 7–8)
         ===================================================================== */}
      {wizardStep === 3 && (
        <div className="bg-white rounded-3xl border border-gray-200 p-6 shadow-xs space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-gray-100 pb-4">
            <div>
              <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
                <FileCheck className="w-6 h-6 text-emerald-600" />
                Step 3: Customer Review, Declaration &amp; 9-Section Dossier Generation
              </h2>
              <p className="text-xs text-gray-500 mt-1">
                Review and edit any field below, verify supplemental motor details, and confirm your declaration to generate the 9-Section Professional Claim Dossier.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setWizardStep(2)}
              className="px-3.5 py-2 rounded-xl border border-gray-200 text-xs font-semibold text-gray-600 hover:bg-gray-50"
            >
              &larr; Back to Evidence Screening
            </button>
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            {/* Core Extracted Fields */}
            <div className="space-y-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-gray-500">
                Core Extracted Incident Fields (Editable)
              </h3>
              {fields.map((field) => (
                <FieldRow
                  key={field.name}
                  field={field}
                  isMissing={!field.value}
                  isAnswering={false}
                  onEdit={handleEditField}
                />
              ))}
            </div>

            {/* Supplemental & Formal Indian Motor Claim Form (Groups B & C — Zero Group D Fields) */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-gray-500">
                  Formal Motor Claim Details (IRDAI 2W / 4W Standard)
                </h3>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                  {claimedVehicleType === 'two_wheeler' ? '2-Wheeler Schema' : '4-Wheeler Schema'}
                </span>
              </div>

              {/* 1. Claimant & Policy Identification */}
              <div className="rounded-2xl border border-gray-200 overflow-hidden">
                <button
                  type="button"
                  onClick={() => setOpenAccordion(openAccordion === 'claimant' ? '' : 'claimant')}
                  className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-50 text-left text-xs font-bold text-gray-800"
                >
                  <span>1. Claimant &amp; Policy Identification</span>
                  <ChevronDown className={`w-4 h-4 transition-transform ${openAccordion === 'claimant' ? 'rotate-180' : ''}`} />
                </button>
                {openAccordion === 'claimant' && (
                  <div className="p-3.5 space-y-2.5 bg-white text-xs">
                    <div className="grid sm:grid-cols-2 gap-2.5">
                      <div>
                        <label className="block font-semibold text-gray-600 mb-1">Full Name (on Policy / RC)</label>
                        <input
                          type="text"
                          value={motorForm.claimant_name || ''}
                          onChange={(e) => updateMotorForm({ claimant_name: e.target.value })}
                          className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                        />
                      </div>
                      <div>
                        <label className="block font-semibold text-gray-600 mb-1">Registered Mobile (RMN)</label>
                        <input
                          type="text"
                          value={motorForm.registered_mobile || ''}
                          onChange={(e) => updateMotorForm({ registered_mobile: e.target.value })}
                          className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                        />
                      </div>
                    </div>
                    <div className="grid sm:grid-cols-2 gap-2.5">
                      <div>
                        <label className="block font-semibold text-gray-600 mb-1">Claimant Email</label>
                        <input
                          type="email"
                          value={motorForm.claimant_email || ''}
                          onChange={(e) => updateMotorForm({ claimant_email: e.target.value })}
                          className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                        />
                      </div>
                      <div>
                        <label className="block font-semibold text-gray-600 mb-1">Vehicle Registration Number</label>
                        <input
                          type="text"
                          value={vehicleRegistration}
                          onChange={(e) => setVehicleRegistration(e.target.value)}
                          placeholder="e.g. KA-01-MJ-4412"
                          className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs font-mono"
                        />
                      </div>
                    </div>
                    <div className="grid sm:grid-cols-3 gap-2.5">
                      <div className="sm:col-span-2">
                        <label className="block font-semibold text-gray-600 mb-1">Residential Address</label>
                        <input
                          type="text"
                          value={motorForm.residential_address || ''}
                          onChange={(e) => updateMotorForm({ residential_address: e.target.value })}
                          placeholder="House/Flat No, Street, City"
                          className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                        />
                      </div>
                      <div>
                        <label className="block font-semibold text-gray-600 mb-1">Pincode</label>
                        <input
                          type="text"
                          maxLength={6}
                          value={motorForm.pincode || ''}
                          onChange={(e) => updateMotorForm({ pincode: e.target.value })}
                          placeholder="560001"
                          className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs font-mono"
                        />
                      </div>
                    </div>
                    <label className="flex items-center gap-2 text-xs text-gray-700 pt-1">
                      <input
                        type="checkbox"
                        checked={Boolean(motorForm.other_insurance_exists)}
                        onChange={(e) => updateMotorForm({ other_insurance_exists: e.target.checked })}
                        className="rounded text-brand-600"
                      />
                      Other active motor insurance policy exists on this vehicle
                    </label>
                    {motorForm.other_insurance_exists && (
                      <input
                        type="text"
                        value={motorForm.other_insurance_details || ''}
                        onChange={(e) => updateMotorForm({ other_insurance_details: e.target.value })}
                        placeholder="Insurer name & policy number"
                        className="w-full rounded-xl border border-amber-300 bg-amber-50/40 px-3 py-1.5 text-xs"
                      />
                    )}
                  </div>
                )}
              </div>

              {/* 2. Incident & Vehicle Usage Details */}
              <div className="rounded-2xl border border-gray-200 overflow-hidden">
                <button
                  type="button"
                  onClick={() => setOpenAccordion(openAccordion === 'incident' ? '' : 'incident')}
                  className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-50 text-left text-xs font-bold text-gray-800"
                >
                  <span>2. Incident, Vehicle Usage &amp; Safety Triggers</span>
                  <ChevronDown className={`w-4 h-4 transition-transform ${openAccordion === 'incident' ? 'rotate-180' : ''}`} />
                </button>
                {openAccordion === 'incident' && (
                  <div className="p-3.5 space-y-2.5 bg-white text-xs">
                    <div className="grid sm:grid-cols-2 gap-2.5">
                      <div>
                        <label className="block font-semibold text-gray-600 mb-1">Loss Type</label>
                        <select
                          value={motorForm.loss_type || 'own_damage_accident'}
                          onChange={(e) => updateMotorForm({ loss_type: e.target.value as MotorLossType })}
                          className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs bg-white"
                        >
                          <option value="own_damage_accident">Own Damage / Accident</option>
                          <option value="theft">Vehicle Theft</option>
                          <option value="fire_natural_calamity">Fire / Flood / Natural Calamity</option>
                          <option value="third_party">Third-Party Liability</option>
                        </select>
                      </div>
                      <div>
                        <label className="block font-semibold text-gray-600 mb-1">Approximate Incident Time</label>
                        <input
                          type="text"
                          value={incidentTime}
                          onChange={(e) => {
                            setIncidentTime(e.target.value)
                            updateMotorForm({ incident_time: e.target.value })
                          }}
                          placeholder="e.g. 7:30 PM"
                          className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                        />
                      </div>
                    </div>

                    <div className="grid sm:grid-cols-2 gap-2.5">
                      <div>
                        <label className="block font-semibold text-gray-600 mb-1">Vehicle Usage Type</label>
                        <select
                          value={motorForm.vehicle_usage_type || 'private_social_domestic'}
                          onChange={(e) => updateMotorForm({ vehicle_usage_type: e.target.value as MotorUsageType })}
                          className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs bg-white"
                        >
                          <option value="private_social_domestic">Private / Social / Domestic</option>
                          <option value="commercial_hire_reward">Commercial / Hire &amp; Reward</option>
                        </select>
                      </div>
                      {claimedVehicleType === 'two_wheeler' ? (
                        <div className="flex items-end pb-1">
                          <label className="flex items-center gap-2 font-semibold text-gray-700 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={Boolean(motorForm.pillion_rider_present)}
                              onChange={(e) => updateMotorForm({ pillion_rider_present: e.target.checked })}
                              className="rounded text-brand-600"
                            />
                            Pillion Rider Present (2W)
                          </label>
                        </div>
                      ) : (
                        <div>
                          <label className="block font-semibold text-gray-600 mb-1">Occupants Count (4W)</label>
                          <input
                            type="number"
                            min={1}
                            max={12}
                            value={motorForm.occupants_count ?? 1}
                            onChange={(e) => updateMotorForm({ occupants_count: Math.max(1, Number(e.target.value) || 1) })}
                            className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                          />
                        </div>
                      )}
                    </div>

                    <div>
                      <label className="block font-semibold text-gray-600 mb-1">Is the Vehicle Currently Drivable?</label>
                      <input
                        type="text"
                        value={drivableStatus}
                        onChange={(e) => setDrivableStatus(e.target.value)}
                        placeholder="Yes / No — note if towing is needed"
                        className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                      />
                    </div>

                    <div className="grid sm:grid-cols-3 gap-2 pt-1">
                      <label className="flex items-center gap-1.5 text-gray-700 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={Boolean(motorForm.vehicle_was_parked_unattended)}
                          onChange={(e) => updateMotorForm({ vehicle_was_parked_unattended: e.target.checked })}
                          className="rounded text-brand-600"
                        />
                        Parked Unattended
                      </label>
                      <label className="flex items-center gap-1.5 text-gray-700 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={Boolean(motorForm.injury_or_third_party_flag)}
                          onChange={(e) => {
                            const checked = e.target.checked
                            updateMotorForm({ injury_or_third_party_flag: checked })
                            setInjuriesReported(checked ? 'Third-party or physical injury reported' : 'No injuries reported')
                          }}
                          className="rounded text-brand-600"
                        />
                        Injury / Third-Party
                      </label>
                      <label className="flex items-center gap-1.5 text-gray-700 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={Boolean(motorForm.police_fir_lodged_flag)}
                          onChange={(e) => {
                            const checked = e.target.checked
                            updateMotorForm({ police_fir_lodged_flag: checked })
                            setPoliceFirInfo(checked ? 'FIR Lodged' : 'Not filed')
                          }}
                          className="rounded text-brand-600"
                        />
                        Police FIR Lodged
                      </label>
                    </div>
                  </div>
                )}
              </div>

              {/* 3. Driver Details (Skipped cleanly if theft or parked unattended) */}
              <div className="rounded-2xl border border-gray-200 overflow-hidden">
                <button
                  type="button"
                  onClick={() => setOpenAccordion(openAccordion === 'driver' ? '' : 'driver')}
                  className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-50 text-left text-xs font-bold text-gray-800"
                >
                  <span>3. Driver Details at Time of Incident</span>
                  <ChevronDown className={`w-4 h-4 transition-transform ${openAccordion === 'driver' ? 'rotate-180' : ''}`} />
                </button>
                {openAccordion === 'driver' && (
                  <div className="p-3.5 bg-white text-xs space-y-2.5">
                    {motorForm.loss_type === 'theft' || motorForm.vehicle_was_parked_unattended ? (
                      <div className="bg-blue-50 border border-blue-200 rounded-xl p-3 text-blue-900 text-xs">
                        Driver details are not required because the claim is marked as{' '}
                        <strong>{motorForm.loss_type === 'theft' ? 'Theft' : 'Parked Unattended'}</strong>.
                      </div>
                    ) : (
                      <>
                        <label className="flex items-center gap-2 font-semibold text-emerald-800 bg-emerald-50/70 border border-emerald-200 rounded-xl px-3 py-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={Boolean(motorForm.driver_was_owner)}
                            onChange={(e) => updateMotorForm({ driver_was_owner: e.target.checked })}
                            className="rounded text-emerald-600"
                          />
                          Driver was the Policyholder / Owner (auto-fill name &amp; address)
                        </label>
                        <div className="grid sm:grid-cols-3 gap-2.5">
                          <div>
                            <label className="block font-semibold text-gray-600 mb-1">Driver Name</label>
                            <input
                              type="text"
                              value={motorForm.driver_name || ''}
                              onChange={(e) => updateMotorForm({ driver_name: e.target.value })}
                              className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                            />
                          </div>
                          <div>
                            <label className="block font-semibold text-gray-600 mb-1">Driver Age</label>
                            <input
                              type="number"
                              min={18}
                              max={95}
                              value={motorForm.driver_age ?? ''}
                              onChange={(e) => updateMotorForm({ driver_age: e.target.value ? Number(e.target.value) : undefined })}
                              className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                            />
                          </div>
                          <div>
                            <label className="block font-semibold text-gray-600 mb-1">Relationship</label>
                            <select
                              value={motorForm.driver_relationship || 'owner'}
                              onChange={(e) => updateMotorForm({ driver_relationship: e.target.value as MotorDriverRelationship })}
                              className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs bg-white"
                            >
                              <option value="owner">Owner / Self</option>
                              <option value="relative_or_friend">Relative or Friend</option>
                              <option value="paid_driver">Paid Driver</option>
                            </select>
                          </div>
                        </div>
                        <div>
                          <label className="block font-semibold text-gray-600 mb-1">Driver Address</label>
                          <input
                            type="text"
                            value={motorForm.driver_address || ''}
                            onChange={(e) => updateMotorForm({ driver_address: e.target.value })}
                            className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                          />
                        </div>
                        <div className="grid sm:grid-cols-2 gap-2.5">
                          <div>
                            <label className="block font-semibold text-gray-600 mb-1">Driving License Number (Manual)</label>
                            <input
                              type="text"
                              value={motorForm.driver_license_number || ''}
                              onChange={(e) => updateMotorForm({ driver_license_number: e.target.value.toUpperCase() })}
                              placeholder="KA01 20200012345"
                              className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs font-mono"
                            />
                          </div>
                          <div>
                            <label className="block font-semibold text-gray-600 mb-1">DL Expiry Date</label>
                            <input
                              type="date"
                              value={motorForm.driver_license_expiry || ''}
                              onChange={(e) => updateMotorForm({ driver_license_expiry: e.target.value })}
                              className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                            />
                          </div>
                        </div>
                        <div className="grid sm:grid-cols-2 gap-2.5">
                          <div>
                            <label className="block font-semibold text-gray-600 mb-1">DL Vehicle Class</label>
                            <select
                              value={motorForm.driver_license_class || ''}
                              onChange={(e) => updateMotorForm({ driver_license_class: (e.target.value || undefined) as MotorLicenseClass })}
                              className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs bg-white"
                            >
                              <option value="">Select DL Class...</option>
                              <option value="MCWG">MCWG (2W with Gear)</option>
                              <option value="MCWOG">MCWOG (Gearless 2W)</option>
                              <option value="LMV">LMV (4W Light Motor Vehicle)</option>
                              <option value="HMV">HMV (Heavy Motor Vehicle)</option>
                              <option value="other">Other</option>
                            </select>
                          </div>
                          <div>
                            <label className="block font-semibold text-gray-600 mb-1">Issuing RTO</label>
                            <input
                              type="text"
                              value={motorForm.driver_issuing_rto || ''}
                              onChange={(e) => updateMotorForm({ driver_issuing_rto: e.target.value })}
                              placeholder="e.g. Koramangala KA-01"
                              className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                            />
                          </div>
                        </div>
                        {((claimedVehicleType === 'two_wheeler' && (motorForm.driver_license_class === 'LMV' || motorForm.driver_license_class === 'HMV')) ||
                          (claimedVehicleType === 'four_wheeler' && (motorForm.driver_license_class === 'MCWG' || motorForm.driver_license_class === 'MCWOG'))) && (
                          <div className="bg-amber-50 border border-amber-300 rounded-xl p-2.5 text-amber-900 font-semibold text-[11px]">
                            ⚠️ Potential License Class Mismatch: Selected DL class ({motorForm.driver_license_class}) normally does not cover a{' '}
                            {claimedVehicleType === 'two_wheeler' ? 'Two-Wheeler (MCWG/MCWOG)' : 'Four-Wheeler (LMV)'}.
                          </div>
                        )}
                        <div className="flex flex-wrap gap-4 pt-1">
                          <label className="flex items-center gap-1.5 text-gray-700 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={Boolean(motorForm.driver_under_intoxication)}
                              onChange={(e) => updateMotorForm({ driver_under_intoxication: e.target.checked })}
                              className="rounded text-brand-600"
                            />
                            Driver Under Alcohol / Drugs
                          </label>
                          <label className="flex items-center gap-1.5 text-gray-700 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={Boolean(motorForm.driver_injured)}
                              onChange={(e) => updateMotorForm({ driver_injured: e.target.checked })}
                              className="rounded text-brand-600"
                            />
                            Driver Injured
                          </label>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>

              {/* 4. Inspection, Settlement Mode & Workshop Details */}
              <div className="rounded-2xl border border-gray-200 overflow-hidden">
                <button
                  type="button"
                  onClick={() => setOpenAccordion(openAccordion === 'workshop' ? '' : 'workshop')}
                  className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-50 text-left text-xs font-bold text-gray-800"
                >
                  <span>4. Settlement Mode, Inspection &amp; Workshop Details</span>
                  <ChevronDown className={`w-4 h-4 transition-transform ${openAccordion === 'workshop' ? 'rotate-180' : ''}`} />
                </button>
                {openAccordion === 'workshop' && (
                  <div className="p-3.5 bg-white text-xs space-y-2.5">
                    <div className="grid sm:grid-cols-2 gap-2.5">
                      <div>
                        <label className="block font-semibold text-gray-600 mb-1">Claim Settlement Mode</label>
                        <select
                          value={motorForm.claim_settlement_mode || 'cashless'}
                          onChange={(e) => updateMotorForm({ claim_settlement_mode: e.target.value as ClaimSettlementMode })}
                          className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs bg-white"
                        >
                          <option value="cashless">Cashless (Network Garage)</option>
                          <option value="reimbursement">Reimbursement (Bank NEFT)</option>
                        </select>
                      </div>
                      <div>
                        <label className="block font-semibold text-gray-600 mb-1">Preferred Inspection Date/Time</label>
                        <input
                          type="datetime-local"
                          value={motorForm.preferred_inspection_datetime || ''}
                          onChange={(e) => updateMotorForm({ preferred_inspection_datetime: e.target.value })}
                          className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="block font-semibold text-gray-600 mb-1">Inspection Location / Address</label>
                      <input
                        type="text"
                        value={motorForm.inspection_location || ''}
                        onChange={(e) => updateMotorForm({ inspection_location: e.target.value })}
                        placeholder="Garage address or spot where vehicle is parked"
                        className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                      />
                    </div>
                    <div className="grid sm:grid-cols-2 gap-2.5">
                      <div>
                        <label className="block font-semibold text-gray-600 mb-1">Workshop / Garage Name</label>
                        <input
                          type="text"
                          value={motorForm.workshop_name || ''}
                          onChange={(e) => updateMotorForm({ workshop_name: e.target.value })}
                          className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                        />
                      </div>
                      <div>
                        <label className="block font-semibold text-gray-600 mb-1">Workshop Contact</label>
                        <input
                          type="text"
                          value={motorForm.workshop_contact || ''}
                          onChange={(e) => updateMotorForm({ workshop_contact: e.target.value })}
                          className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                        />
                      </div>
                    </div>
                    <div className="grid sm:grid-cols-2 gap-2.5">
                      <div>
                        <label className="block font-semibold text-gray-600 mb-1">Workshop Address</label>
                        <input
                          type="text"
                          value={motorForm.workshop_address || ''}
                          onChange={(e) => updateMotorForm({ workshop_address: e.target.value })}
                          className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                        />
                      </div>
                      <div>
                        <label className="block font-semibold text-gray-600 mb-1">Garage Estimate INR (Optional)</label>
                        <input
                          type="number"
                          min={0}
                          value={motorForm.approx_estimated_repair_cost_inr ?? ''}
                          onChange={(e) => updateMotorForm({ approx_estimated_repair_cost_inr: e.target.value ? Number(e.target.value) : undefined })}
                          placeholder="e.g. 12500"
                          className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                        />
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* 5. Conditional Disclosures (Group C — rendered ONLY when triggered!) */}
              {(motorForm.claim_settlement_mode === 'reimbursement' ||
                motorForm.police_fir_lodged_flag ||
                motorForm.loss_type === 'theft' ||
                motorForm.injury_or_third_party_flag ||
                motorForm.driver_injured ||
                motorForm.loss_type === 'fire_natural_calamity') && (
                <div className="rounded-2xl border border-amber-300 overflow-hidden bg-amber-50/30">
                  <button
                    type="button"
                    onClick={() => setOpenAccordion(openAccordion === 'conditional' ? '' : 'conditional')}
                    className="w-full flex items-center justify-between px-4 py-2.5 bg-amber-50 text-left text-xs font-bold text-amber-900"
                  >
                    <span>5. Additional Required Details (Triggered Conditions)</span>
                    <ChevronDown className={`w-4 h-4 transition-transform ${openAccordion === 'conditional' ? 'rotate-180' : ''}`} />
                  </button>
                  <div className="p-3.5 space-y-3 text-xs bg-white">
                    {/* Trigger 1: Reimbursement Bank / NEFT Details */}
                    {motorForm.claim_settlement_mode === 'reimbursement' && (
                      <div className="space-y-2 border-b border-gray-100 pb-3">
                        <div className="font-bold text-gray-800">Bank / NEFT Details (Reimbursement Settlement)</div>
                        <div className="grid sm:grid-cols-2 gap-2">
                          <input
                            type="text"
                            value={motorForm.bank_account_holder_name || ''}
                            onChange={(e) => updateMotorForm({ bank_account_holder_name: e.target.value })}
                            placeholder="Account Holder Name *"
                            className="rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                          />
                          <input
                            type="text"
                            value={motorForm.bank_account_number || ''}
                            onChange={(e) => updateMotorForm({ bank_account_number: e.target.value })}
                            placeholder="Bank Account Number *"
                            className="rounded-xl border border-gray-300 px-3 py-1.5 text-xs font-mono"
                          />
                          <input
                            type="text"
                            value={motorForm.bank_ifsc_code || ''}
                            onChange={(e) => updateMotorForm({ bank_ifsc_code: e.target.value.toUpperCase() })}
                            placeholder="IFSC Code *"
                            className="rounded-xl border border-gray-300 px-3 py-1.5 text-xs font-mono"
                          />
                          <input
                            type="text"
                            value={motorForm.bank_branch_name || ''}
                            onChange={(e) => updateMotorForm({ bank_branch_name: e.target.value })}
                            placeholder="Bank & Branch Name"
                            className="rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                          />
                        </div>
                      </div>
                    )}

                    {/* Trigger 2: FIR Details */}
                    {motorForm.police_fir_lodged_flag && (
                      <div className="space-y-2 border-b border-gray-100 pb-3">
                        <div className="font-bold text-gray-800">Police FIR / GD Entry Details</div>
                        <div className="grid sm:grid-cols-2 gap-2">
                          <input
                            type="text"
                            value={motorForm.fir_or_gd_number || ''}
                            onChange={(e) => updateMotorForm({ fir_or_gd_number: e.target.value })}
                            placeholder="FIR / GD Number *"
                            className="rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                          />
                          <input
                            type="text"
                            value={motorForm.police_station_name || ''}
                            onChange={(e) => updateMotorForm({ police_station_name: e.target.value })}
                            placeholder="Police Station Name *"
                            className="rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                          />
                          <input
                            type="date"
                            value={motorForm.fir_report_date || ''}
                            onChange={(e) => updateMotorForm({ fir_report_date: e.target.value })}
                            className="rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                          />
                          <input
                            type="text"
                            value={motorForm.fir_complainant_name || ''}
                            onChange={(e) => updateMotorForm({ fir_complainant_name: e.target.value })}
                            placeholder="Complainant Name"
                            className="rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                          />
                        </div>
                      </div>
                    )}

                    {/* Trigger 3: Theft-Specific Details */}
                    {motorForm.loss_type === 'theft' && (
                      <div className="space-y-2 border-b border-gray-100 pb-3">
                        <div className="font-bold text-gray-800">Theft-Specific Requirements</div>
                        <div className="grid sm:grid-cols-2 gap-2">
                          <select
                            value={motorForm.non_traceable_report_status || 'pending'}
                            onChange={(e) => updateMotorForm({ non_traceable_report_status: e.target.value as any })}
                            className="rounded-xl border border-gray-300 px-3 py-1.5 text-xs bg-white"
                          >
                            <option value="pending">Non-Traceable Report: Pending</option>
                            <option value="obtained">Non-Traceable Report: Obtained</option>
                            <option value="not_applicable">Non-Traceable Report: N/A</option>
                          </select>
                          <label className="flex items-center gap-2 text-gray-700">
                            <input
                              type="checkbox"
                              checked={Boolean(motorForm.all_original_keys_available)}
                              onChange={(e) => updateMotorForm({ all_original_keys_available: e.target.checked })}
                              className="rounded text-brand-600"
                            />
                            All Original Keys Available
                          </label>
                        </div>
                        <div className="flex flex-wrap items-center gap-3">
                          <label className="flex items-center gap-2 text-gray-700">
                            <input
                              type="checkbox"
                              checked={Boolean(motorForm.financier_hypothecated)}
                              onChange={(e) => updateMotorForm({ financier_hypothecated: e.target.checked })}
                              className="rounded text-brand-600"
                            />
                            Vehicle Hypothecated / Financed
                          </label>
                          {motorForm.financier_hypothecated && (
                            <input
                              type="text"
                              value={motorForm.financier_name || ''}
                              onChange={(e) => updateMotorForm({ financier_name: e.target.value })}
                              placeholder="Financier / Bank Name *"
                              className="flex-1 rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                            />
                          )}
                        </div>
                        <input
                          type="text"
                          value={motorForm.stolen_accessories_details || ''}
                          onChange={(e) => updateMotorForm({ stolen_accessories_details: e.target.value })}
                          placeholder="Stolen accessories details (optional)"
                          className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                        />
                      </div>
                    )}

                    {/* Trigger 4: Injury / Third-Party Details */}
                    {(motorForm.injury_or_third_party_flag || motorForm.driver_injured) && (
                      <div className="space-y-2 border-b border-gray-100 pb-3">
                        <div className="font-bold text-gray-800">Injury / Third-Party &amp; Witness Details</div>
                        <div className="grid sm:grid-cols-2 gap-2">
                          <select
                            value={motorForm.third_party_loss_type || 'injury'}
                            onChange={(e) => updateMotorForm({ third_party_loss_type: e.target.value as any })}
                            className="rounded-xl border border-gray-300 px-3 py-1.5 text-xs bg-white"
                          >
                            <option value="injury">Third-Party Injury</option>
                            <option value="death">Third-Party Fatality</option>
                            <option value="property_damage">Third-Party Property Damage</option>
                            <option value="driver_or_occupant_only">Driver / Occupant Only</option>
                          </select>
                          <input
                            type="number"
                            min={0}
                            value={motorForm.third_party_injured_count ?? 0}
                            onChange={(e) => updateMotorForm({ third_party_injured_count: Number(e.target.value) || 0 })}
                            placeholder="Injured Persons Count"
                            className="rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                          />
                          <input
                            type="text"
                            value={motorForm.hospital_and_treatment_details || ''}
                            onChange={(e) => updateMotorForm({ hospital_and_treatment_details: e.target.value })}
                            placeholder="Hospital & Treatment Details"
                            className="rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                          />
                          <input
                            type="text"
                            value={motorForm.third_party_vehicle_reg || ''}
                            onChange={(e) => updateMotorForm({ third_party_vehicle_reg: e.target.value })}
                            placeholder="Third-Party Vehicle Reg No"
                            className="rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                          />
                          <input
                            type="text"
                            value={motorForm.third_party_policy_details || ''}
                            onChange={(e) => updateMotorForm({ third_party_policy_details: e.target.value })}
                            placeholder="Third-Party Policy Details"
                            className="rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                          />
                          <input
                            type="text"
                            value={motorForm.third_party_damage_summary || ''}
                            onChange={(e) => updateMotorForm({ third_party_damage_summary: e.target.value })}
                            placeholder="Third-Party Damage Summary"
                            className="rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                          />
                          <input
                            type="text"
                            value={motorForm.witness_name || ''}
                            onChange={(e) => updateMotorForm({ witness_name: e.target.value })}
                            placeholder="Witness Name"
                            className="rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                          />
                          <input
                            type="text"
                            value={motorForm.witness_contact || ''}
                            onChange={(e) => updateMotorForm({ witness_contact: e.target.value })}
                            placeholder="Witness Contact"
                            className="rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                          />
                        </div>
                      </div>
                    )}

                    {/* Trigger 5: Fire / Natural Calamity */}
                    {motorForm.loss_type === 'fire_natural_calamity' && (
                      <div className="space-y-1.5">
                        <div className="font-bold text-gray-800">Fire / Natural Calamity Report</div>
                        <input
                          type="text"
                          value={motorForm.fire_brigade_report_number || ''}
                          onChange={(e) => updateMotorForm({ fire_brigade_report_number: e.target.value })}
                          placeholder="Fire Brigade / Calamity Report Number (Optional)"
                          className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                        />
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* ── Sprint 1.8: AI Evidence & Approved Repair Estimate Summary Card ── */}
          {aiVerificationResult && (
            <div className="bg-brand-50/50 border border-brand-200 rounded-2xl p-4 space-y-3">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="w-5 h-5 text-brand-600" />
                  <h3 className="text-sm font-bold text-brand-950">
                    5-Stage AI Evidence Intelligence &amp; Cost Estimate Summary
                  </h3>
                </div>
                <span
                  className={`px-3 py-1 rounded-full text-xs font-extrabold ${
                    aiVerificationResult.decision === 'PASS'
                      ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                      : 'bg-amber-100 text-amber-800 border border-amber-300'
                  }`}
                >
                  {aiVerificationResult.decision === 'PASS' ? 'APPROVED AUTO-ESTIMATE' : 'PROVISIONAL UNDER REVIEW'}
                </span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div className="bg-white p-2.5 rounded-xl border border-brand-100">
                  <div className="text-gray-500 text-[11px]">Vehicle Category</div>
                  <div className="font-bold text-gray-900 mt-0.5">{formatCategoryLabel(claimedVehicleType)}</div>
                </div>
                <div className="bg-white p-2.5 rounded-xl border border-brand-100">
                  <div className="text-gray-500 text-[11px]">Spoof Screening</div>
                  <div className="font-bold text-gray-900 mt-0.5">
                    {(aiVerificationResult.spoof_risk * 100).toFixed(1)}% Risk
                  </div>
                </div>
                <div className="bg-white p-2.5 rounded-xl border border-brand-100">
                  <div className="text-gray-500 text-[11px]">Damages Detected</div>
                  <div className="font-bold text-gray-900 mt-0.5">{aiVerificationResult.damage_count} instance(s)</div>
                </div>
                <div className="bg-white p-2.5 rounded-xl border border-brand-100">
                  <div className="text-gray-500 text-[11px]">Total AI Estimate</div>
                  <div className="font-bold text-brand-700 text-sm mt-0.5">
                    {formatInr(aiVerificationResult.cost_estimate?.total_estimated_inr || 0)}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Legal Declarations & Compulsory DPDP Act 2025 Consent (Step 3 before Submit) */}
          <div className="bg-emerald-50/70 border border-emerald-200 rounded-2xl p-4 space-y-4">
            <div className="grid sm:grid-cols-3 gap-3 text-xs">
              <div>
                <label className="block font-semibold text-emerald-950 mb-1">Declaration Place</label>
                <input
                  type="text"
                  value={motorForm.declaration_place || ''}
                  onChange={(e) => updateMotorForm({ declaration_place: e.target.value })}
                  placeholder="City / Town"
                  className="w-full rounded-xl border border-emerald-200 bg-white px-3 py-1.5 text-xs"
                />
              </div>
              <div>
                <label className="block font-semibold text-emerald-950 mb-1">Declaration Date</label>
                <input
                  type="date"
                  value={motorForm.declaration_date || ''}
                  onChange={(e) => updateMotorForm({ declaration_date: e.target.value })}
                  className="w-full rounded-xl border border-emerald-200 bg-white px-3 py-1.5 text-xs"
                />
              </div>
              <div>
                <label className="block font-semibold text-emerald-950 mb-1">Insured Digital Signature (Typed Full Name)</label>
                <input
                  type="text"
                  value={motorForm.insured_digital_signature || ''}
                  onChange={(e) => updateMotorForm({ insured_digital_signature: e.target.value })}
                  placeholder="Type your full name"
                  className="w-full rounded-xl border border-emerald-200 bg-white px-3 py-1.5 text-xs font-medium"
                />
              </div>
            </div>

            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-1 border-t border-emerald-200/80">
              <div className="space-y-2">
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={Boolean(motorForm.dpdp_consent_granted)}
                    onChange={(e) =>
                      updateMotorForm({
                        dpdp_consent_granted: e.target.checked,
                        dpdp_consent_timestamp: e.target.checked ? new Date().toISOString() : '',
                      })
                    }
                    className="mt-1 w-4 h-4 rounded text-emerald-600 focus:ring-emerald-500"
                  />
                  <span className="text-xs text-emerald-950 leading-relaxed">
                    <strong>DPDP Act 2025 Consent (Required):</strong> I explicitly consent to the processing of my claim data, vehicle details, and forensic evidence for insurer claim verification.
                  </span>
                </label>

                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={declarationChecked && Boolean(motorForm.truthfulness_declaration_accepted)}
                    onChange={(e) => {
                      setDeclarationChecked(e.target.checked)
                      updateMotorForm({ truthfulness_declaration_accepted: e.target.checked })
                    }}
                    className="mt-1 w-4 h-4 rounded text-emerald-600 focus:ring-emerald-500"
                  />
                  <span className="text-xs text-emerald-950 leading-relaxed">
                    <strong>Customer Confirmation &amp; Declaration (Section 9):</strong> I confirm that all declared incident details, driver particulars, and {evidenceList.length} uploaded evidence file(s) are true and accurate.
                  </span>
                </label>
              </div>

              <button
                type="button"
                onClick={handleFinalizeAndGenerateDossier}
                disabled={isSubmitting || !motorForm.dpdp_consent_granted}
                className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-2xl bg-emerald-600 text-white font-bold text-xs shadow-sm hover:bg-emerald-700 disabled:opacity-50 shrink-0"
              >
                {isSubmitting ? (
                  <>
                    <Spinner size="sm" /> Generating 9-Section Dossier...
                  </>
                ) : (
                  <>
                    <Check className="w-4 h-4" /> Confirm &amp; Generate 9-Section Claim Dossier
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/* ── Helper: Draw Realistic Patterned Vehicle Damage Canvas for Live/Lab Testing ── */
function drawSimulatedVehicleDamageCanvas(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  tag: string,
  seed: number,
) {
  ctx.fillStyle = '#e2e8f0'
  ctx.fillRect(0, 0, w, h)

  // Road surface
  ctx.fillStyle = '#334155'
  ctx.fillRect(0, Math.floor(h * 0.65), w, Math.floor(h * 0.35))

  // Vehicle body silhouette
  const offset = (seed % 17) * 2
  ctx.fillStyle = '#1e40af'
  ctx.fillRect(Math.floor(w * 0.15) + offset, Math.floor(h * 0.3), Math.floor(w * 0.7), Math.floor(h * 0.38))

  // Headlamp & dent highlight
  ctx.fillStyle = '#f59e0b'
  ctx.beginPath()
  ctx.arc(Math.floor(w * 0.75), Math.floor(h * 0.45), Math.floor(w * 0.06), 0, Math.PI * 2)
  ctx.fill()

  // Scratch/dent crosshatch lines for high DCT spatial frequency
  ctx.strokeStyle = '#dc2626'
  ctx.lineWidth = 3
  for (let i = 0; i < 6; i++) {
    ctx.beginPath()
    ctx.moveTo(Math.floor(w * 0.55) + i * 10, Math.floor(h * 0.35))
    ctx.lineTo(Math.floor(w * 0.65) + i * 8, Math.floor(h * 0.6))
    ctx.stroke()
  }

  ctx.fillStyle = '#ffffff'
  ctx.font = 'bold 13px monospace'
  ctx.fillText(`ClaimSathi Evidence | ${tag}`, 14, h - 16)
}

/* ── Inline Editable Field Row Subcomponent ── */
function FieldRow({
  field,
  isMissing,
  isAnswering,
  onEdit,
}: {
  field: ClaimField
  isMissing: boolean
  isAnswering: boolean
  onEdit: (name: string, value: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(field.value || '')

  const handleSave = () => {
    onEdit(field.name, draft)
    setEditing(false)
  }

  return (
    <div
      className={`rounded-2xl p-3.5 border transition-all ${
        isAnswering
          ? 'bg-amber-50/70 border-amber-300 ring-2 ring-amber-300/40'
          : isMissing
          ? 'bg-gray-50/80 border-gray-200'
          : 'bg-emerald-50/40 border-emerald-200'
      }`}
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider">
          {field.label}
        </span>
        <div className="flex items-center gap-1.5">
          {isMissing ? (
            <span className="text-[10px] font-semibold text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full">
              {isAnswering ? '⏳ Asking now' : 'Missing'}
            </span>
          ) : (
            <>
              <ConfidenceBadge confidence={field.confidence} />
              {field.is_edited && (
                <span className="text-[10px] text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded font-medium border border-blue-200">
                  edited
                </span>
              )}
            </>
          )}

          {!editing && (
            <button
              type="button"
              onClick={() => {
                setDraft(field.value || '')
                setEditing(true)
              }}
              title="Click to edit value"
              className="text-gray-400 hover:text-blue-600 p-0.5 transition-colors"
            >
              <Edit3 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {editing ? (
        <div className="flex items-center gap-2 mt-1">
          <input
            autoFocus
            className="flex-1 bg-white border border-blue-400 rounded-lg px-2.5 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSave()}
            onBlur={handleSave}
          />
          <button
            type="button"
            onClick={handleSave}
            className="px-2.5 py-1 rounded-lg bg-blue-600 text-white text-xs font-semibold"
          >
            Save
          </button>
        </div>
      ) : (
        <p className={`text-xs font-medium ${isMissing ? 'text-gray-400 italic' : 'text-gray-900'}`}>
          {field.value || 'Not provided yet'}
        </p>
      )}
    </div>
  )
}

function MissingFieldInput({ onSubmit }: { onSubmit: (val: string) => void }) {
  const [val, setVal] = useState('')

  const handleSend = () => {
    if (val.trim()) {
      onSubmit(val.trim())
      setVal('')
    }
  }

  return (
    <div className="flex items-center gap-1.5">
      <input
        className="flex-1 rounded-xl border border-gray-300 bg-white px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500 shadow-xs"
        placeholder="Or type answer here..."
        value={val}
        onChange={(e) => setVal(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleSend()}
      />
      <button
        type="button"
        onClick={handleSend}
        disabled={!val.trim()}
        className="px-3.5 py-2 rounded-xl bg-blue-600 text-white text-xs font-semibold disabled:opacity-40 hover:bg-blue-700 transition-colors"
      >
        <Send className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}
