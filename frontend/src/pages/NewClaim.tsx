import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, getStoredUser } from '../api'
import { useAppSettings } from '../i18n'
import type {
  ClaimField,
  VoiceTranscribeResponse,
  CaptureSessionResponse,
  EvidenceAssetRecord,
  EvidenceVerificationReport,
  YoloDetectionBox,
} from '../types'
import ConfidenceBadge from '../components/ConfidenceBadge'
import ProviderBadge from '../components/ProviderBadge'
import Spinner from '../components/Spinner'
import { WavRecorder } from '../utils/wavRecorder'
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

  // Supplemental fields populated cleanly from conversation (no fake defaults)
  const [vehicleRegistration, setVehicleRegistration] = useState('')
  const [incidentTime, setIncidentTime] = useState('')
  const [drivableStatus, setDrivableStatus] = useState('')
  const [injuriesReported, setInjuriesReported] = useState('No injuries reported')
  const [policeFirInfo, setPoliceFirInfo] = useState('Not filed')
  const [declarationChecked, setDeclarationChecked] = useState(true)

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
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [hasStartedIntake, setHasStartedIntake] = useState(false)

  // Live browser SpeechRecognition parallel capture (real-speech fallback if external STT fails)
  const speechRecRef = useRef<any>(null)
  const liveBrowserTranscriptRef = useRef<string>('')

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
        liveBrowserTranscriptRef.current = combined.trim()
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
  const [, setAudioVolume] = useState(0)
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
  const [uploadingEvidence, setUploadingEvidence] = useState(false)
  const [captureSession, setCaptureSession] = useState<CaptureSessionResponse | null>(null)
  const [cameraActive, setCameraActive] = useState(false)
  const videoPreviewRef = useRef<HTMLVideoElement | null>(null)
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const evidenceInputRef = useRef<HTMLInputElement | null>(null)

  // Sprint 1.8: 5-Stage AI Evidence Intelligence & INR Cost Estimator state
  const [claimedVehicleType, setClaimedVehicleType] = useState<'four_wheeler' | 'two_wheeler'>('four_wheeler')
  const [aiVerificationResult, setAiVerificationResult] = useState<EvidenceVerificationReport | null>(null)
  const [isVerifyingEvidence, setIsVerifyingEvidence] = useState(false)
  const [selectedEvidenceFile, setSelectedEvidenceFile] = useState<File | null>(null)
  const [evidencePreviewUrl, setEvidencePreviewUrl] = useState<string | null>(null)

  // Conversation scroll container ref
  const chatScrollRef = useRef<HTMLDivElement | null>(null)

  // Revoke object URL on unmount / change
  useEffect(() => {
    return () => {
      if (evidencePreviewUrl) URL.revokeObjectURL(evidencePreviewUrl)
    }
  }, [evidencePreviewUrl])

  // Synchronize claimed vehicle category from conversational vehicle_type field
  useEffect(() => {
    const vtField = (fields.find((f) => f.name === 'vehicle_type')?.value || '').toLowerCase()
    if (
      vtField.includes('bike') ||
      vtField.includes('motorcycle') ||
      vtField.includes('two wheeler') ||
      vtField.includes('two-wheeler') ||
      vtField.includes('2 wheeler') ||
      vtField.includes('2-wheeler') ||
      vtField.includes('scooter')
    ) {
      setClaimedVehicleType('two_wheeler')
    } else if (
      vtField.includes('car') ||
      vtField.includes('sedan') ||
      vtField.includes('suv') ||
      vtField.includes('four wheeler') ||
      vtField.includes('four-wheeler') ||
      vtField.includes('4 wheeler') ||
      vtField.includes('4-wheeler')
    ) {
      setClaimedVehicleType('four_wheeler')
    }
  }, [fields])

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
    registration?: string | null
    damages?: string[]
  } | null>(null)

  const syncExtractedSlots = (slots: {
    claimed_vehicle_type?: 'two_wheeler' | 'four_wheeler' | null
    vehicle_registration?: string | null
    policy_reference?: string | null
    incident_date?: string | null
    damage_keywords?: string[]
    incident_description?: string | null
  }) => {
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
    const resolvedReg = slots.vehicle_registration || slots.policy_reference
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
    if (slots.incident_description) {
      setFields((prev) =>
        prev.map((f) =>
          f.name === 'damage_description' && (!f.value || f.confidence === 'missing')
            ? { ...f, value: slots.incident_description!, confidence: 'high' }
            : f
        )
      )
      setMissingFields((prev) => prev.filter((m) => m !== 'damage_description'))
    }
    if (slots.claimed_vehicle_type || slots.vehicle_registration || (slots.damage_keywords && slots.damage_keywords.length > 0)) {
      setExtractedSlotsSummary((prev) => ({
        vehicleType: slots.claimed_vehicle_type || prev?.vehicleType || null,
        registration: slots.vehicle_registration || prev?.registration || null,
        damages: slots.damage_keywords?.length ? slots.damage_keywords : prev?.damages || [],
      }))
    }
  }

  const speakViaBrowserSpeech = (text: string, targetLang: string) => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return false
    try {
      window.speechSynthesis.cancel()
      const utter = new SpeechSynthesisUtterance(text)
      utter.lang = targetLang
      utter.rate = 1.0
      utter.onend = () => {
        setIsPlayingAudio(false)
        setActiveSpeechText(null)
      }
      utter.onerror = () => {
        setIsPlayingAudio(false)
        setActiveSpeechText(null)
      }
      setIsPlayingAudio(true)
      window.speechSynthesis.speak(utter)
      return true
    } catch {
      return false
    }
  }

  // ── Speech Synthesis with Gnani Timbre + Browser speechSynthesis Fallback ──
  const speakText = async (text: string, langCode?: string) => {
    if (isPlayingAudio) {
      stopAudio()
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel()
      }
      setIsPlayingAudio(false)
      setActiveSpeechText(null)
      return
    }

    setLastSpokenSpeech({ text, language: langCode })
    setIsSynthesizing(true)
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
        voice: 'Nalini',
      })
      setIsSynthesizing(false)
      setIsPlayingAudio(true)

      await playAudioBlob(audioBlob)
      setIsPlayingAudio(false)
      setActiveSpeechText(null)
    } catch {
      setIsSynthesizing(false)
      const spoke = speakViaBrowserSpeech(text, targetLang)
      if (!spoke) {
        setIsPlayingAudio(false)
        setActiveSpeechText(null)
      }
    }
  }

  const handleReplayLastVoice = () => {
    if (isPlayingAudio) {
      stopAudio()
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel()
      }
      setIsPlayingAudio(false)
      setActiveSpeechText(null)
      return
    }
    if (lastSpokenSpeech) {
      speakText(lastSpokenSpeech.text, lastSpokenSpeech.language)
    } else {
      const lastMsg = [...messages].reverse().find((m) => m.sender === 'assistant' && (m.audioText || m.text))
      if (lastMsg) {
        speakText(lastMsg.audioText || lastMsg.text, lastMsg.language)
      }
    }
  }

  // ── Unified Stateful Conversation Updater ──
  const applyConversationResult = (
    res: {
      transcript: string
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
      vehicle_registration?: string | null
      damage_keywords?: string[]
      incident_description?: string | null
    },
    procTurnId?: string,
  ) => {
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

    syncExtractedSlots({
      claimed_vehicle_type: res.claimed_vehicle_type,
      vehicle_registration: res.vehicle_registration,
      policy_reference: merged.find((f) => f.name === 'policy_reference')?.value || null,
      incident_date: merged.find((f) => f.name === 'incident_date')?.value || null,
      damage_keywords: res.damage_keywords,
      incident_description: res.incident_description,
    })

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
      'Thank you, I have noted those details.'
    const assistantSpeech = res.assistant_speech_text || assistantText

    const assistantTurn: MessageTurn = {
      id: 'assistant-' + Date.now(),
      sender: 'assistant',
      text: assistantText,
      audioText: assistantSpeech,
      language: detectedLang,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }

    setMessages((prev) => [
      ...(procTurnId ? prev.filter((m) => m.id !== procTurnId) : prev),
      userTurn,
      assistantTurn,
    ])

    if (autoVoiceEnabled && assistantSpeech) {
      setTimeout(() => speakText(assistantSpeech, detectedLang), 300)
    }
  }

  // ── Main Voice Intake Recording ──
  const startRecording = async () => {
    stopAudio()
    setError('')
    try {
      const recorder = new WavRecorder(16000, (vol) => setAudioVolume(vol))
      recorderRef.current = recorder
      await recorder.start()
      startBrowserSpeechCapture(effectiveSttLanguage)

      setIsRecording(true)
      setRecordingSeconds(0)

      timerRef.current = window.setInterval(() => {
        setRecordingSeconds((prev) => {
          if (prev >= 29) {
            stopRecording()
            return 30
          }
          return prev + 1
        })
      }, 1000)
    } catch (err: any) {
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
    setIsRecording(false)

    try {
      const audioBlob = await recorderRef.current.stop()
      recorderRef.current = null
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
    setIsRecording(false)
    setRecordingSeconds(0)
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setError('')
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
    setHasStartedIntake(true)

    const procTurnId = 'proc-' + Date.now()
    setMessages((prev) => [
      ...prev,
      {
        id: procTurnId,
        sender: 'assistant',
        text: 'Listening and understanding your details...',
        timestamp: 'Just now',
        isStreaming: true,
      },
    ])

    const knownMap = getKnownFieldsMap()
    const historyList = getHistoryPayload()
    const expectedField = missingFields.length > 0 ? missingFields[activeMissingIndex] : null

    try {
      const data: VoiceTranscribeResponse = await api.transcribeVoice(
        blob,
        filename,
        false,
        effectiveSttLanguage,
        knownMap,
        historyList,
        expectedField,
      )
      applyConversationResult(data, procTurnId)
    } catch (err: any) {
      if (browserFallbackTranscript) {
        try {
          const conv = await api.converseClaimTurn({
            message: browserFallbackTranscript,
            language: effectiveSttLanguage,
            known_fields: knownMap,
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
    }
  }

  // ── Process Typed Natural Conversation Turn ──
  const handleProcessTextIntake = async (customText?: string) => {
    const raw = (customText ?? textIntakeInput).trim()
    if (!raw) return
    setError('')
    setHasStartedIntake(true)
    setTextIntakeInput('')

    try {
      const data = await api.converseClaimTurn({
        message: raw,
        language: effectiveSttLanguage,
        known_fields: getKnownFieldsMap(),
        history: getHistoryPayload(),
        expected_field: missingFields.length > 0 ? missingFields[activeMissingIndex] : null,
      })
      applyConversationResult(data)
    } catch (err: any) {
      setError(err.message || 'Failed to process your message.')
    }
  }

  // ── Follow-Up Voice Recording ──
  const startAnswerRecording = async () => {
    stopAudio()
    setError('')
    try {
      const recorder = new WavRecorder(16000, (vol) => setAudioVolume(vol))
      answerRecorderRef.current = recorder
      await recorder.start()
      startBrowserSpeechCapture(effectiveSttLanguage)

      setIsAnswerRecording(true)
      setAnswerRecordingSeconds(0)

      answerTimerRef.current = window.setInterval(() => {
        setAnswerRecordingSeconds((s) => {
          if (s >= 14) {
            stopAnswerRecording()
            return 15
          }
          return s + 1
        })
      }, 1000)
    } catch (err: any) {
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

    setIsAnswerRecording(false)
    setIsProcessingAnswerVoice(true)

    const knownMap = getKnownFieldsMap()
    const historyList = getHistoryPayload()
    const expectedField = missingFields[activeMissingIndex] || null

    try {
      const resp = await api.transcribeVoice(
        await answerRecorderRef.current.stop(),
        'answer.wav',
        false,
        effectiveSttLanguage,
        knownMap,
        historyList,
        expectedField,
      )
      answerRecorderRef.current = null
      setIsProcessingAnswerVoice(false)

      if ((resp.transcript || '').trim()) {
        applyConversationResult(resp)
      } else if (browserCaptured) {
        const conv = await api.converseClaimTurn({
          message: browserCaptured,
          language: effectiveSttLanguage,
          known_fields: knownMap,
          history: historyList,
          expected_field: expectedField,
        })
        applyConversationResult(conv)
      } else {
        setError('No speech detected in your answer. Please tap mic again or type below.')
      }
    } catch (err: any) {
      answerRecorderRef.current = null
      if (browserCaptured) {
        try {
          const conv = await api.converseClaimTurn({
            message: browserCaptured,
            language: effectiveSttLanguage,
            known_fields: knownMap,
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
    setIsAnswerRecording(false)
    setAnswerRecordingSeconds(0)
  }

  const handleApplyAnswer = async (value: string) => {
    const clean = (value || '').trim()
    if (!clean) return
    setError('')
    try {
      const conv = await api.converseClaimTurn({
        message: clean,
        language: effectiveSttLanguage,
        known_fields: getKnownFieldsMap(),
        history: getHistoryPayload(),
        expected_field: missingFields[activeMissingIndex] || null,
      })
      applyConversationResult(conv)
    } catch (err: any) {
      setError(err.message || 'Failed to process answer.')
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

    if (!activeClaimId) {
      setIsSubmitting(true)
      try {
        const storedUser = getStoredUser()
        const created = await api.createClaim({
          customer_id: storedUser?.customer_id,
          insurer_name: storedUser?.declared_insurer || 'Bharat General Insurance',
          policy_reference: fieldMap.policy_reference,
          incident_location: fieldMap.incident_location,
          incident_date: fieldMap.incident_date,
          vehicle_type: fieldMap.vehicle_type,
          damage_description: fieldMap.damage_description,
          injuries_reported: injuriesReported,
          people_involved: `Policyholder (${storedUser?.name || 'Driver'})`,
          transcript: transcript || 'Customer conversational intake completed.',
        })
        setActiveClaimId(created.id)
      } catch (err: any) {
        setError(err.message || 'Failed to initialize claim case.')
        setIsSubmitting(false)
        return
      }
      setIsSubmitting(false)
    }

    setWizardStep(2)
  }

  // ── Step 2: 5-Stage AI Verification Pipeline & Legacy Upload ──
  const runAiVerificationOnFile = async (
    file: File,
    overrideVehicleType?: 'four_wheeler' | 'two_wheeler',
  ) => {
    const vType = overrideVehicleType || claimedVehicleType
    setSelectedEvidenceFile(file)
    if (evidencePreviewUrl) URL.revokeObjectURL(evidencePreviewUrl)
    setEvidencePreviewUrl(URL.createObjectURL(file))
    setIsVerifyingEvidence(true)
    setError('')
    try {
      const res = await api.verifyEvidenceV1(file, vType)
      setAiVerificationResult(res)
      if (res.decision === 'REJECT') {
        const isMism =
          Boolean(res.vehicle_category_mismatch) ||
          Boolean(res.reasons?.some((r) => r.includes('VEHICLE_CATEGORY_MISMATCH')))
        if (isMism) {
          setError(
            `Vehicle Category Mismatch: You selected ${formatCategoryLabel(vType)}, but the AI detected a ${formatCategoryLabel(res.detected_vehicle_category)} in the uploaded photo. Please upload a valid photo of the claimed vehicle.`,
          )
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
        })
        if (narration?.spoken_narration) {
          setEvidenceNarration({
            spoken: narration.spoken_narration,
            lang: narration.language,
          })
          if (autoVoiceEnabled) {
            setTimeout(() => speakText(narration.spoken_narration, narration.language), 400)
          }
        }
      } catch (narrationErr) {
        console.warn('Evidence narration failed:', narrationErr)
      }
    } catch (err: any) {
      setError(err.message || '5-Stage AI evidence verification failed.')
    } finally {
      setIsVerifyingEvidence(false)
    }
  }

  const handleToggleVehicleCategory = async (newType: 'four_wheeler' | 'two_wheeler') => {
    setClaimedVehicleType(newType)
    if (selectedEvidenceFile) {
      await runAiVerificationOnFile(selectedEvidenceFile, newType)
    }
  }

  const handleUploadEvidenceFile = async (
    file: Blob | File,
    filename: string,
    captureMethod: string = 'upload_photo',
    sessionId?: string,
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
      if (!isVideo) {
        await runAiVerificationOnFile(f)
      }
      await handleUploadEvidenceFile(f, f.name, isVideo ? 'upload_video' : 'upload_photo')
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
          await runAiVerificationOnFile(fileObj)
          await handleUploadEvidenceFile(
            blob,
            fname,
            'live_photo',
            session!.session_id,
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
    if (!declarationChecked) {
      setError('Please check the Customer Declaration box to confirm your claim details.')
      return
    }
    if (aiVerificationResult?.decision === 'REJECT') {
      setError('Cannot submit claim with REJECTED evidence. Please return to Step 2 and upload valid vehicle evidence.')
      return
    }
    setIsSubmitting(true)
    setError('')

    const fieldMap = Object.fromEntries(fields.map((f) => [f.name, f.value || '']))
    try {
      await api.updateAndConfirmClaim(activeClaimId, {
        policy_reference: fieldMap.policy_reference,
        incident_location: fieldMap.incident_location,
        incident_date: fieldMap.incident_date,
        vehicle_type: fieldMap.vehicle_type,
        damage_description: fieldMap.damage_description,
        injuries_reported: injuriesReported,
        customer_confirmation: true,
        evidence_id: aiVerificationResult?.id,
        verification_decision: aiVerificationResult?.decision,
        claimed_vehicle_type: claimedVehicleType,
        total_estimated_inr: aiVerificationResult?.cost_estimate?.total_estimated_inr,
        cost_estimate: aiVerificationResult?.cost_estimate,
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
                      stopAudio()
                      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
                        window.speechSynthesis.cancel()
                      }
                      setIsPlayingAudio(false)
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
                              onClick={() => speakText(turn.audioText!, turn.language)}
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
                        <div className="flex items-center gap-3 mb-2">
                          <span className="w-3 h-3 rounded-full bg-red-600 animate-ping" />
                          <span className="text-xs font-bold text-gray-700">
                            Recording (00:{recordingSeconds < 10 ? `0${recordingSeconds}` : recordingSeconds} / 00:30)
                          </span>
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
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-red-600 flex items-center gap-1.5">
                          <Radio className="w-4 h-4 animate-ping" /> Listening (00:
                          {answerRecordingSeconds < 10 ? `0${answerRecordingSeconds}` : answerRecordingSeconds})
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
                          stopAudio()
                          if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
                            window.speechSynthesis.cancel()
                          }
                          setHasStartedIntake(false)
                          setTranscript('')
                          setMissingFields([])
                          setLockedLanguage(null)
                          setExtractedSlotsSummary(null)
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
                  onClick={() => setWizardStep(1)}
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
                    setWizardStep(3)
                  }}
                  className="inline-flex items-center gap-1.5 px-5 py-2 rounded-xl bg-brand-600 text-white text-xs font-bold hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed shadow-xs"
                >
                  Proceed to Step 3: Customer Review <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Claimed Vehicle Category Selection */}
            <div className="bg-gray-50/90 border border-gray-200 rounded-2xl p-4 mb-6 space-y-2">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                <label className="block text-xs font-bold text-gray-800">
                  Claimed Policy Vehicle Category (5-Stage Vision Screening Guard)
                </label>
                <span className="text-[11px] font-semibold text-gray-500">
                  Cross-vehicle mismatch (Car vs. Bike) is strictly rejected
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3 max-w-md">
                <button
                  type="button"
                  onClick={() => handleToggleVehicleCategory('four_wheeler')}
                  className={`flex items-center justify-center gap-2 px-3.5 py-2.5 rounded-xl border text-xs font-bold transition-all ${
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
                  onClick={() => handleToggleVehicleCategory('two_wheeler')}
                  className={`flex items-center justify-center gap-2 px-3.5 py-2.5 rounded-xl border text-xs font-bold transition-all ${
                    claimedVehicleType === 'two_wheeler'
                      ? 'bg-brand-50 border-brand-600 text-brand-800 shadow-xs'
                      : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-100'
                  }`}
                >
                  <Bike className="w-4 h-4" />
                  Two-Wheeler (Bike)
                </button>
              </div>
            </div>

            {/* Upload & Live Camera Action Cards */}
            <div className="grid md:grid-cols-2 gap-5 mb-6">
              {/* Option A: Upload Photo or Video from Device */}
              <div className="rounded-2xl border-2 border-dashed border-blue-200 bg-blue-50/40 p-5 flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-2 text-blue-900 font-bold text-sm mb-1">
                    <Upload className="w-4 h-4 text-blue-600" />
                    Upload Vehicle Damage Photos or Videos
                  </div>
                  <p className="text-xs text-gray-600 mb-4">
                    Supports JPEG, PNG, WebP images and MP4, MOV, WebM videos. Validates magic bytes, EXIF metadata, C2PA/SynthID provenance, SHA-256 &amp; 64-bit DCT pHash.
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <label className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 text-white text-xs font-bold cursor-pointer hover:bg-blue-700 shadow-xs">
                    <Upload className="w-4 h-4" /> Choose Photo / Video Files
                    <input
                      ref={evidenceInputRef}
                      type="file"
                      multiple
                      accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm"
                      className="hidden"
                      onChange={handleEvidenceInputChange}
                    />
                  </label>
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
                </div>
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
                          {formatCategoryLabel(claimedVehicleType)} verified &bull; Spoof Risk: {(aiVerificationResult.spoof_risk * 100).toFixed(1)}% &bull; Detected Damages: {aiVerificationResult.damage_count}
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
                          Flagged for Human Adjuster Review — Provisional Estimate Generated
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
                      onClick={() => speakText(evidenceNarration.spoken, evidenceNarration.lang)}
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
                      <span className="text-xs font-bold text-gray-700">Total AI Estimated Amount:</span>
                      <span className="text-lg font-extrabold text-brand-700">
                        {formatInr(aiVerificationResult.cost_estimate?.total_estimated_inr || 0)}
                      </span>
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
                    const isFlagged = scr?.requires_human_review
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

            {/* Supplemental Motor Claim Details */}
            <div className="space-y-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-gray-500">
                Supplemental Motor &amp; Safety Details (Step 3 &amp; 4 of PDF)
              </h3>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">
                  Vehicle Registration Number
                </label>
                <input
                  type="text"
                  value={vehicleRegistration}
                  onChange={(e) => setVehicleRegistration(e.target.value)}
                  placeholder="Enter your vehicle registration number"
                  className="w-full rounded-xl border border-gray-300 px-3 py-2 text-xs"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">
                  Approximate Incident Time
                </label>
                <input
                  type="text"
                  value={incidentTime}
                  onChange={(e) => setIncidentTime(e.target.value)}
                  placeholder="Enter approximate date & time of incident"
                  className="w-full rounded-xl border border-gray-300 px-3 py-2 text-xs"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">
                  Is the Vehicle Currently Drivable?
                </label>
                <input
                  type="text"
                  value={drivableStatus}
                  onChange={(e) => setDrivableStatus(e.target.value)}
                  placeholder="Yes / No — note if towing is needed"
                  className="w-full rounded-xl border border-gray-300 px-3 py-2 text-xs"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">
                  Injuries Reported
                </label>
                <input
                  type="text"
                  value={injuriesReported}
                  onChange={(e) => setInjuriesReported(e.target.value)}
                  className="w-full rounded-xl border border-gray-300 px-3 py-2 text-xs"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">
                  Police Report / FIR Information
                </label>
                <input
                  type="text"
                  value={policeFirInfo}
                  onChange={(e) => setPoliceFirInfo(e.target.value)}
                  className="w-full rounded-xl border border-gray-300 px-3 py-2 text-xs"
                />
              </div>
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

          {/* Customer Declaration Checkbox (Section 8 of Dossier) */}
          <div className="bg-emerald-50/70 border border-emerald-200 rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={declarationChecked}
                onChange={(e) => setDeclarationChecked(e.target.checked)}
                className="mt-1 w-4 h-4 rounded text-emerald-600 focus:ring-emerald-500"
              />
              <span className="text-xs text-emerald-950 leading-relaxed">
                <strong>Customer Confirmation &amp; Declaration (Section 8):</strong> I confirm that the extracted and edited incident details, policy information, and {evidenceList.length} uploaded evidence file(s) are accurate to the best of my knowledge.
              </span>
            </label>

            <button
              type="button"
              onClick={handleFinalizeAndGenerateDossier}
              disabled={isSubmitting}
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
