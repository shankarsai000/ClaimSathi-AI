import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, getStoredUser } from '../api'
import type {
  ClaimField,
  VoiceTranscribeResponse,
  CaptureSessionResponse,
  EvidenceAssetRecord,
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

export default function NewClaim() {
  const navigate = useNavigate()

  // Wizard Step: 1 = Conversation, 2 = Evidence & Live Camera, 3 = Customer Review & Declaration
  const [wizardStep, setWizardStep] = useState<1 | 2 | 3>(1)
  const [activeClaimId, setActiveClaimId] = useState<string | null>(null)

  // Claim fields & conversational state
  const [fields, setFields] = useState<ClaimField[]>([
    { name: 'policy_reference', label: 'Policy Reference', value: null, confidence: 'missing', is_edited: false, follow_up_question: null },
    { name: 'vehicle_type', label: 'Vehicle Type', value: null, confidence: 'missing', is_edited: false, follow_up_question: null },
    { name: 'incident_location', label: 'Incident Location', value: null, confidence: 'missing', is_edited: false, follow_up_question: null },
    { name: 'incident_date', label: 'Incident Date', value: null, confidence: 'missing', is_edited: false, follow_up_question: null },
    { name: 'damage_description', label: 'Damage Description', value: null, confidence: 'missing', is_edited: false, follow_up_question: null },
  ])
  const [missingFields, setMissingFields] = useState<string[]>([])
  const [transcript, setTranscript] = useState('')
  const [activeMissingIndex, setActiveMissingIndex] = useState(0)
  const [textIntakeInput, setTextIntakeInput] = useState('')

  // Supplemental fields from Step 3 & 4 of PDF
  const [vehicleRegistration, setVehicleRegistration] = useState('KA-17-EA-4590')
  const [incidentTime, setIncidentTime] = useState('6:30 PM')
  const [drivableStatus, setDrivableStatus] = useState('No (Requires towing / repair)')
  const [injuriesReported, setInjuriesReported] = useState('No injuries reported')
  const [policeFirInfo, setPoliceFirInfo] = useState('Not filed')
  const [declarationChecked, setDeclarationChecked] = useState(true)

  // Conversation turns history
  const [messages, setMessages] = useState<MessageTurn[]>([
    {
      id: 'greeting',
      sender: 'assistant',
      text: 'Namaste! Welcome to ClaimSathi AI. I am your multilingual claims officer. Please tell me what happened to your vehicle — you can speak naturally or type in Telugu, Kannada, Hindi, Tamil, or English. Mention your policy number, vehicle, location, date, and damage.',
      audioText: 'Namaste! Welcome to ClaimSathi AI. Please tell me what happened to your vehicle. Mention your policy number, vehicle, location, and damage.',
      language: 'en-IN',
      timestamp: 'Just now',
    },
  ])

  // System & Environment state
  const [error, setError] = useState('')
  const [isDemoMode, setIsDemoMode] = useState(false)
  const [activeModel, setActiveModel] = useState<string>('prisma-v3.0')
  const [selectedLanguage, setSelectedLanguage] = useState<string>('indic-auto')
  const [autoVoiceEnabled, setAutoVoiceEnabled] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [hasStartedIntake, setHasStartedIntake] = useState(false)

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

  // Step 2: Evidence Collection & Guided Live Camera Capture state
  const [evidenceList, setEvidenceList] = useState<EvidenceAssetRecord[]>([])
  const [uploadingEvidence, setUploadingEvidence] = useState(false)
  const [captureSession, setCaptureSession] = useState<CaptureSessionResponse | null>(null)
  const [cameraActive, setCameraActive] = useState(false)
  const videoPreviewRef = useRef<HTMLVideoElement | null>(null)
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const evidenceInputRef = useRef<HTMLInputElement | null>(null)

  // Conversation scroll container ref
  const chatScrollRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    api
      .health()
      .then((h) => {
        if (h.gnani_stt_model) setActiveModel(h.gnani_stt_model)
        setIsDemoMode(!h.gnani_configured)
      })
      .catch(() => {
        setIsDemoMode(true)
      })

    return () => {
      stopAudio()
      stopLiveCamera()
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

  // ── Speech Synthesis with Gnani Timbre ──
  const speakText = async (text: string, langCode: string = 'en-IN') => {
    if (isPlayingAudio) {
      stopAudio()
      setIsPlayingAudio(false)
      setActiveSpeechText(null)
      return
    }

    setIsSynthesizing(true)
    setActiveSpeechText(text)
    setError('')

    try {
      const targetLang = langCode.startsWith('te')
        ? 'te-IN'
        : langCode.startsWith('kn')
        ? 'kn-IN'
        : langCode.startsWith('hi')
        ? 'hi-IN'
        : 'en-IN'
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
    } catch (err: any) {
      setIsSynthesizing(false)
      setIsPlayingAudio(false)
      setActiveSpeechText(null)
      setError(`Voice synthesis: ${err.message}`)
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

    if (!recorderRef.current) return
    setIsRecording(false)

    try {
      const audioBlob = await recorderRef.current.stop()
      recorderRef.current = null
      await handleProcessMainAudio(audioBlob, 'recording.wav')
    } catch (err: any) {
      setError(err.message || 'Failed to capture recorded audio.')
    }
  }

  const cancelRecording = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
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

  // ── Process Spoken Intake with Gnani Prisma STT ──
  const handleProcessMainAudio = async (blob: Blob | File, filename: string) => {
    setError('')
    setHasStartedIntake(true)

    const procTurnId = 'proc-' + Date.now()
    setMessages((prev) => [
      ...prev,
      {
        id: procTurnId,
        sender: 'assistant',
        text: 'Transcribing your speech with Gnani Prisma and extracting vehicle, policy, location, and damage details...',
        timestamp: 'Just now',
        isStreaming: true,
      },
    ])

    try {
      const data: VoiceTranscribeResponse = await api.transcribeVoice(
        blob,
        filename,
        isDemoMode,
        selectedLanguage,
      )

      setTranscript(data.transcript)
      setFields(data.fields)
      setMissingFields(data.missing_fields)
      if (data.model) setActiveModel(data.model)
      setActiveMissingIndex(0)

      const userTurn: MessageTurn = {
        id: 'user-' + Date.now(),
        sender: 'user',
        text: data.transcript,
        language: data.detected_language || selectedLanguage,
        audioDuration: data.request_metadata?.duration_seconds,
        latencyMs: data.request_metadata?.processing_time
          ? Math.round(data.request_metadata.processing_time * 1000)
          : undefined,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }

      const assistantText = data.assistant_dialogue || 'Thank you! I have processed your initial claim intake.'
      const assistantSpeech = data.assistant_speech_text || assistantText
      const assistantLang = data.assistant_language || data.detected_language || 'te-IN'

      const assistantTurn: MessageTurn = {
        id: 'assistant-' + Date.now(),
        sender: 'assistant',
        text: assistantText,
        audioText: assistantSpeech,
        language: assistantLang,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }

      setMessages((prev) => [...prev.filter((m) => m.id !== procTurnId), userTurn, assistantTurn])

      if (autoVoiceEnabled && assistantSpeech) {
        setTimeout(() => speakText(assistantSpeech, assistantLang), 350)
      }
    } catch (err: any) {
      setMessages((prev) => prev.filter((m) => m.id !== procTurnId))
      setError(err.message || 'Speech transcription failed.')
    }
  }

  // ── Process Typed / Sample Text Narrative (Step 2 & 3 of PDF) ──
  const handleProcessTextIntake = async (customText?: string) => {
    const raw = (customText ?? textIntakeInput).trim()
    if (!raw) return
    setError('')
    setHasStartedIntake(true)
    setTextIntakeInput('')

    try {
      const data = await api.extractTextIntake(raw, selectedLanguage)
      setTranscript(data.transcript)
      setFields(data.fields)
      setMissingFields(data.missing_fields)
      setActiveMissingIndex(0)

      const userTurn: MessageTurn = {
        id: 'user-txt-' + Date.now(),
        sender: 'user',
        text: data.transcript,
        language: data.detected_language,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }

      const assistantTurn: MessageTurn = {
        id: 'ast-txt-' + Date.now(),
        sender: 'assistant',
        text: data.assistant_dialogue,
        audioText: data.assistant_speech_text,
        language: data.assistant_language,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }

      setMessages((prev) => [...prev, userTurn, assistantTurn])
    } catch (err: any) {
      setError(err.message || 'Failed to extract fields from text.')
    }
  }

  // ── Missing Field Voice Recording ──
  const startAnswerRecording = async () => {
    stopAudio()
    setError('')
    try {
      const recorder = new WavRecorder(16000, (vol) => setAudioVolume(vol))
      answerRecorderRef.current = recorder
      await recorder.start()

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
    if (!answerRecorderRef.current) return

    setIsAnswerRecording(false)
    setIsProcessingAnswerVoice(true)

    try {
      const blob = await answerRecorderRef.current.stop()
      answerRecorderRef.current = null

      const resp = await api.transcribeVoice(
        blob,
        'answer.wav',
        isDemoMode,
        selectedLanguage,
      )
      setIsProcessingAnswerVoice(false)

      const answerText = (resp.transcript || '').trim()
      if (answerText) {
        handleApplyAnswer(answerText, 'voice')
      } else {
        setError('No speech detected in your answer. Please tap mic again or type in the box.')
      }
    } catch (err: any) {
      setIsProcessingAnswerVoice(false)
      setError(err.message || 'Failed to process voice answer.')
    }
  }

  const cancelAnswerRecording = () => {
    if (answerTimerRef.current) {
      clearInterval(answerTimerRef.current)
      answerTimerRef.current = null
    }
    if (answerRecorderRef.current) {
      answerRecorderRef.current.cancel()
      answerRecorderRef.current = null
    }
    setIsAnswerRecording(false)
    setAnswerRecordingSeconds(0)
  }

  const handleApplyAnswer = (value: string, _source: 'voice' | 'text') => {
    const targetFieldName = missingFields[activeMissingIndex]
    if (!targetFieldName) return

    setFields((prev) =>
      prev.map((f) =>
        f.name === targetFieldName
          ? { ...f, value, confidence: 'high' as const, is_edited: false }
          : f,
      ),
    )

    const userAnsTurn: MessageTurn = {
      id: 'ans-' + Date.now(),
      sender: 'user',
      text: value,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }

    const nextMissingIndex = activeMissingIndex + 1
    const hasMoreMissing = nextMissingIndex < missingFields.length

    if (hasMoreMissing) {
      setActiveMissingIndex(nextMissingIndex)
      const nextFieldName = missingFields[nextMissingIndex]
      const nextField = fields.find((f) => f.name === nextFieldName)
      const nextQ = nextField?.follow_up_question || `Please provide the details for ${nextField?.label}.`

      const nextAssistantTurn: MessageTurn = {
        id: 'ast-' + Date.now(),
        sender: 'assistant',
        text: `Noted "${value}". Next: ${nextQ}`,
        audioText: nextQ,
        language: 'te-IN',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }

      setMessages((prev) => [...prev, userAnsTurn, nextAssistantTurn])
      if (autoVoiceEnabled) {
        setTimeout(() => speakText(nextQ, 'te-IN'), 350)
      }
    } else {
      setMissingFields([])
      const completionText =
        'Thank you! All 5 core claim details have been recorded. Now proceed to Step 2 to upload or live-capture vehicle damage photos/videos for Evidence Integrity Screening.'
      const completionTe =
        'ధన్యవాదాలు! మీ క్లెయిమ్ వివరాలు నమోదయ్యాయి. ఇప్పుడు వాహన డ్యామేజ్ ఫోటోలు లేదా వీడియోలు అప్లోడ్ చేయండి.'

      const completionTurn: MessageTurn = {
        id: 'comp-' + Date.now(),
        sender: 'assistant',
        text: completionText,
        audioText: completionTe,
        language: 'te-IN',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }

      setMessages((prev) => [...prev, userAnsTurn, completionTurn])
      if (autoVoiceEnabled) {
        setTimeout(() => speakText(completionTe, 'te-IN'), 350)
      }
    }
  }

  const handleEditField = (name: string, value: string) => {
    setFields((prev) =>
      prev.map((f) =>
        f.name === name ? { ...f, value, confidence: 'high' as const, is_edited: true } : f,
      ),
    )
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
          customer_id: storedUser?.customer_id || 'USR-100001',
          policy_holder_name: storedUser?.name || 'Rahul Sharma',
          policy_reference: fieldMap.policy_reference,
          incident_location: fieldMap.incident_location,
          incident_date: fieldMap.incident_date,
          incident_time: incidentTime,
          vehicle_type: fieldMap.vehicle_type,
          vehicle_registration: vehicleRegistration,
          damage_description: fieldMap.damage_description,
          drivable_status: drivableStatus,
          injuries_reported: injuriesReported,
          police_fir_info: policeFirInfo,
          transcript: transcript || 'Customer conversational intake completed.',
          language: selectedLanguage,
          edited_fields: fields.filter((f) => f.is_edited).map((f) => f.name),
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

  // ── Step 2: Upload Photo / Video Evidence ──
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
          await handleUploadEvidenceFile(
            blob,
            `live_capture_${session!.session_id}.jpg`,
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
    setIsSubmitting(true)
    setError('')

    const fieldMap = Object.fromEntries(fields.map((f) => [f.name, f.value || '']))
    try {
      await api.confirmClaim(activeClaimId, {
        confirmed: true,
        edited_fields: fieldMap,
        vehicle_registration: vehicleRegistration,
        incident_time: incidentTime,
        drivable_status: drivableStatus,
        injuries_reported: injuriesReported,
        police_fir_info: policeFirInfo,
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
            { step: 1, title: '1. Multilingual AI Intake', sub: 'Steps 2–4: Voice/Text & Follow-ups' },
            { step: 2, title: '2. Evidence & Integrity Engine', sub: 'Steps 5–6: Live Camera, C2PA & pHash' },
            { step: 3, title: '3. Review & Generate Dossier', sub: 'Steps 7–9: 9-Section Report & Gateway' },
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
                    if (item.step === 3 && activeClaimId) setWizardStep(3)
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
                  Step 1: Multilingual Conversational Claim Intake
                </h1>
                <ProviderBadge isMock={isDemoMode} model={activeModel} />
              </div>
              <p className="text-xs text-gray-500 mt-1">
                Speak via microphone (Gnani Prisma ASR + Timbre TTS) or type your incident in Telugu, Kannada, Hindi, or English
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2.5">
              <select
                value={selectedLanguage}
                onChange={(e) => setSelectedLanguage(e.target.value)}
                className="bg-gray-50 border border-gray-200 rounded-xl px-3 py-1.5 text-xs font-semibold text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {INDIAN_LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.label}
                  </option>
                ))}
              </select>

              <button
                type="button"
                onClick={() => setAutoVoiceEnabled(!autoVoiceEnabled)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border transition-colors ${
                  autoVoiceEnabled
                    ? 'bg-blue-50 border-blue-200 text-blue-700'
                    : 'bg-gray-50 border-gray-200 text-gray-400'
                }`}
              >
                <Volume2 className="w-3.5 h-3.5" />
                <span>Voice: {autoVoiceEnabled ? 'ON' : 'OFF'}</span>
              </button>

              <div className="flex items-center bg-gray-100 rounded-xl p-1 text-xs">
                <button
                  type="button"
                  onClick={() => {
                    setIsDemoMode(false)
                    setError('')
                  }}
                  className={`px-2.5 py-1 rounded-lg font-medium transition-all ${
                    !isDemoMode ? 'bg-blue-600 text-white shadow-xs' : 'text-gray-600 hover:text-gray-900'
                  }`}
                >
                  Live Gnani AI
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setIsDemoMode(true)
                    setError('')
                  }}
                  className={`px-2.5 py-1 rounded-lg font-medium transition-all ${
                    isDemoMode ? 'bg-amber-600 text-white shadow-xs' : 'text-gray-600 hover:text-gray-900'
                  }`}
                >
                  Simulated Demo
                </button>
              </div>
            </div>
          </div>

          {/* 1-Click Quick Scenarios Bar for Testing */}
          <div className="bg-blue-50/60 border border-blue-200 rounded-2xl px-4 py-3 flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs font-bold text-blue-900 flex items-center gap-1.5">
              <Sparkles className="w-4 h-4 text-blue-600" />
              Quick Test Narratives (or use Microphone below):
            </span>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() =>
                  handleProcessTextIntake(
                    'Nanna bike accident aayitu in Davanagere yesterday evening. Policy number MOT-2026-KA-99881. Front mudguard and headlamp damaged.',
                  )
                }
                className="px-3 py-1 rounded-xl bg-white border border-blue-200 text-blue-800 text-xs font-semibold hover:bg-blue-100"
              >
                🇮🇳 Rahul Bike Scenario (Kannada/English - PDF Page 2)
              </button>
              <button
                type="button"
                onClick={() =>
                  handleProcessTextIntake(
                    'చూడండి, నా కార్ యాక్సిడెంట్ అయ్యింది. పాలసీ నంబర్ ఎంఓటీ టు థౌజండ్ ట్వంటీ ఫోర్ టీఎస్ నైన్ ఎయిట్ సెవెన్ సిక్స్ ఫైవ్. నేను హైదరాబాద్ లో మధురాపూర్ దగ్గర డ్రైవ్ చేస్తున్నప్పుడు ఒక ఆటో వచ్చి సైడ్ లో హిట్ చేసింది. లెఫ్ట్ డోర్ అండ్ బంపర్ ఫుల్ గా డ్యామేజ్ అయ్యింది.',
                  )
                }
                className="px-3 py-1 rounded-xl bg-white border border-blue-200 text-blue-800 text-xs font-semibold hover:bg-blue-100"
              >
                🇮🇳 Telugu Voice Scenario (Missing Date Follow-up)
              </button>
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
                          <Mic className="w-4 h-4" /> Speak Your Claim (Press to Talk)
                        </button>

                        <label className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-4 py-3 rounded-2xl border border-gray-300 text-gray-700 font-medium hover:bg-gray-50 transition-colors cursor-pointer text-xs">
                          <Upload className="w-4 h-4 text-gray-500" /> Upload Audio File
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
                        placeholder="Or type your accident explanation in Kannada, Telugu, Hindi, or English..."
                        className="flex-1 rounded-xl border border-gray-300 px-3.5 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                      <button
                        type="button"
                        onClick={() => handleProcessTextIntake()}
                        disabled={!textIntakeInput.trim()}
                        className="px-4 py-2 rounded-xl bg-gray-900 text-white text-xs font-semibold disabled:opacity-40 hover:bg-gray-800"
                      >
                        Extract
                      </button>
                    </div>
                  </>
                ) : missingFields.length > 0 && currentMissingField ? (
                  <div className="bg-blue-50/60 rounded-2xl border border-blue-200 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-bold text-blue-900">
                        Answering Follow-Up: {currentMissingField.label}
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
                          <Mic className="w-4 h-4" /> 🎙️ Speak Answer
                        </button>

                        <div className="w-full flex-1">
                          <MissingFieldInput onSubmit={(val) => handleApplyAnswer(val, 'text')} />
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
                            <Square className="w-3.5 h-3.5 fill-white inline mr-1" /> Done Speaking
                          </button>
                          <button
                            type="button"
                            onClick={cancelAnswerRecording}
                            className="px-3 py-1.5 rounded-xl border border-gray-300 text-xs text-gray-600"
                          >
                            Cancel
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
                      <span>All 5 core claim fields captured! Proceed to Evidence &amp; Live Camera Screening.</span>
                    </div>

                    <div className="flex items-center gap-2 w-full sm:w-auto">
                      <button
                        type="button"
                        onClick={() => {
                          stopAudio()
                          setHasStartedIntake(false)
                          setTranscript('')
                          setMissingFields([])
                        }}
                        className="px-3 py-2 text-xs font-semibold text-gray-600 hover:text-gray-900 border rounded-xl bg-white"
                      >
                        Reset
                      </button>
                      <button
                        type="button"
                        onClick={handleProceedToEvidenceStep}
                        disabled={isSubmitting}
                        className="flex-1 sm:flex-initial inline-flex items-center justify-center gap-1.5 px-5 py-2.5 rounded-xl bg-brand-600 text-white font-bold text-xs shadow-xs hover:bg-brand-700"
                      >
                        {isSubmitting ? 'Initializing Claim...' : 'Next: Evidence Screening'}
                        <ChevronRight className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* RIGHT COLUMN: LIVE CLAIM HUD / 5 STRUCTURED FIELDS */}
            <div className="lg:col-span-5 bg-white rounded-3xl border border-gray-200 p-6 shadow-xs space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-sm text-gray-900">Extracted Claim Fields (Step 3)</h3>
                  <p className="text-[11px] text-gray-400">Auto-filled from speech/text; click pencil to edit</p>
                </div>
                <div className="flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                  <ShieldCheck className="w-4 h-4" />
                  <span>{capturedCount} of 5 Captured</span>
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
                  return (
                    <FieldRow
                      key={field.name}
                      field={field}
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
                  Continue to Step 2: Upload &amp; Screen Evidence <ChevronRight className="w-4 h-4" />
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
                  onClick={() => setWizardStep(3)}
                  className="inline-flex items-center gap-1.5 px-5 py-2 rounded-xl bg-brand-600 text-white text-xs font-bold hover:bg-brand-700 shadow-xs"
                >
                  Proceed to Step 3: Customer Review <ChevronRight className="w-4 h-4" />
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
                      {captureSession.instructions.map((inst) => (
                        <div key={inst.step} className="text-xs text-gray-700 flex items-center gap-1.5">
                          <span className="w-4 h-4 rounded-full bg-emerald-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0">
                            {inst.step}
                          </span>
                          <span>{inst.prompt}</span>
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
                        key={ev.asset_id}
                        className={`rounded-2xl border p-4 flex gap-4 ${
                          isFlagged
                            ? 'bg-amber-50/60 border-amber-300'
                            : 'bg-white border-gray-200'
                        }`}
                      >
                        {ev.media_type === 'image' ? (
                          <img
                            src={api.getEvidenceFileUrl(ev.asset_id)}
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
                              <p className="text-[11px] text-gray-600">{scr.provenance_summary}</p>
                              <div className="text-[10px] font-mono text-gray-500 space-y-0.5 pt-1">
                                <div className="truncate">
                                  SHA-256: {scr.sha256_hash.slice(0, 24)}...
                                </div>
                                {scr.phash_hex && (
                                  <div>
                                    64-bit DCT pHash: <span className="font-bold">{scr.phash_hex}</span>
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
                                  {scr.matched_claim_id && (
                                    <span className="ml-1 text-red-700">
                                      (Matched {scr.matched_claim_id})
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
