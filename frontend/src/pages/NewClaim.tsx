import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import type { ClaimField, VoiceTranscribeResponse, RequestMetadata } from '../types'
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
  RotateCcw,
  Sparkles,
  Info,
  Bot,
  User,
  Radio,
  Clock,
  ShieldCheck,
  Check,
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
}

const INDIAN_LANGUAGES = [
  { code: 'indic-auto', label: '🌐 Auto-Detect All 10+ Languages (Telugu, Hindi, English, etc.)' },
  { code: 'te-IN', label: '🇮🇳 Telugu / Tenglish (te-IN)' },
  { code: 'hi-IN', label: '🇮🇳 Hindi / Hinglish (hi-IN)' },
  { code: 'en-IN', label: '🇮🇳 Indian English (en-IN)' },
  { code: 'kn-IN', label: '🇮🇳 Kannada / Kanglish (kn-IN)' },
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

  // Conversation turns history
  const [messages, setMessages] = useState<MessageTurn[]>([
    {
      id: 'greeting',
      sender: 'assistant',
      text: 'Namaste! Welcome to ClaimSathi AI. I am your claims intake officer. Please tell me what happened to your vehicle — you can speak naturally in Telugu, Hindi, or English. Describe your policy number, vehicle, where it happened, and the damage.',
      audioText: 'Namaste! Welcome to ClaimSathi AI. Please tell me what happened to your vehicle. Mention your policy number, vehicle, location, and damage. You can speak naturally in Telugu, Hindi, or English.',
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

  // Conversation scroll container ref
  const chatScrollRef = useRef<HTMLDivElement | null>(null)

  // Health check on mount
  useEffect(() => {
    api.health()
      .then((h) => {
        if (h.gnani_stt_model) setActiveModel(h.gnani_stt_model)
        setIsDemoMode(!h.gnani_configured)
      })
      .catch(() => {
        setIsDemoMode(true)
      })

    return () => {
      stopAudio()
      if (timerRef.current) clearInterval(timerRef.current)
      if (recorderRef.current) recorderRef.current.cancel()
      if (answerTimerRef.current) clearInterval(answerTimerRef.current)
      if (answerRecorderRef.current) answerRecorderRef.current.cancel()
    }
  }, [])

  // Auto scroll chat to bottom when messages update
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
      // Pick voice & language: te-IN for Telugu, hi-IN for Hindi, en-IN for English
      const targetLang = langCode.startsWith('te') ? 'te-IN' : langCode.startsWith('hi') ? 'hi-IN' : 'en-IN'
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

  // ── Handle Uploaded Audio File ──
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

    // Add temporary processing message turn
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

      // Remove temporary message and append the user's transcript turn
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

      // Assistant dialogue turn
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

      // Auto-speak response if enabled
      if (autoVoiceEnabled && assistantSpeech) {
        setTimeout(() => speakText(assistantSpeech, assistantLang), 350)
      }
    } catch (err: any) {
      setMessages((prev) => prev.filter((m) => m.id !== procTurnId))
      setError(err.message || 'Speech transcription failed.')
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

  // ── Apply Spoken or Typed Answer to Missing Field ──
  const handleApplyAnswer = (value: string, source: 'voice' | 'text') => {
    const targetFieldName = missingFields[activeMissingIndex]
    if (!targetFieldName) return

    // Update field value with High confidence (not marked as edited override)
    setFields((prev) =>
      prev.map((f) =>
        f.name === targetFieldName
          ? { ...f, value, confidence: 'high' as const, is_edited: false }
          : f,
      ),
    )

    // Add user answer turn to conversation
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
      // ALL 5 FIELDS COMPLETE!
      setMissingFields([])
      const completionText =
        'Thank you! All 5 claim details have been recorded successfully. Please review the summary below and click Confirm to create your demo claim ticket.'
      const completionTe =
        'ధన్యవాదాలు! మీ క్లెయిమ్ కి సంబంధించిన వివరాలు విజయవంతంగా నమోదయ్యాయి. దయచేసి వివరాలు సరిచూసుకొని క్లెయిమ్ టికెట్ ని కన్ఫర్మ్ చేయండి.'

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

  // ── Inline Edit for Any Extracted Field ──
  const handleEditField = (name: string, value: string) => {
    setFields((prev) =>
      prev.map((f) => (f.name === name ? { ...f, value, is_edited: true } : f)),
    )
  }

  // ── Submit & Create Claim Ticket ──
  const handleConfirmAndSubmit = async () => {
    setIsSubmitting(true)
    setError('')
    const fieldMap = Object.fromEntries(fields.map((f) => [f.name, f.value || '']))

    try {
      const result = await api.createClaim({
        policy_reference: fieldMap.policy_reference,
        incident_location: fieldMap.incident_location,
        incident_date: fieldMap.incident_date,
        vehicle_type: fieldMap.vehicle_type,
        damage_description: fieldMap.damage_description,
        transcript,
      })
      navigate(`/claims/${result.id}`)
    } catch (err: any) {
      setIsSubmitting(false)
      setError(err.message || 'Failed to create demo claim ticket.')
    }
  }

  // Computed state
  const capturedCount = fields.filter((f) => f.confidence !== 'missing' && f.value).length
  const isAllCaptured = capturedCount === 5
  const currentMissingFieldName = missingFields.length > 0 ? missingFields[activeMissingIndex] : null
  const currentMissingField = fields.find((f) => f.name === currentMissingFieldName)

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* ── HEADER & LIVE PROVIDER BADGES ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white border border-gray-200 rounded-3xl p-5 shadow-sm">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-bold text-gray-900">Conversational Claim Intake</h1>
            <ProviderBadge isMock={isDemoMode} model={activeModel} />
          </div>
          <p className="text-xs text-gray-500 mt-1">
            Voice-first insurance intake powered by Gnani Prisma ASR &amp; Timbre TTS
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Dialect / Language Dropdown */}
          <select
            value={selectedLanguage}
            onChange={(e) => setSelectedLanguage(e.target.value)}
            className="bg-gray-50 border border-gray-200 rounded-xl px-3 py-1.5 text-xs font-semibold text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 shadow-sm"
          >
            {INDIAN_LANGUAGES.map((l) => (
              <option key={l.code} value={l.code}>
                {l.label}
              </option>
            ))}
          </select>

          {/* Voice Auto-play Toggle */}
          <button
            type="button"
            onClick={() => setAutoVoiceEnabled(!autoVoiceEnabled)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border transition-colors ${
              autoVoiceEnabled
                ? 'bg-blue-50 border-blue-200 text-blue-700'
                : 'bg-gray-50 border-gray-200 text-gray-400'
            }`}
            title="Automatically speak assistant responses out loud"
          >
            <Volume2 className="w-3.5 h-3.5" />
            <span>Voice: {autoVoiceEnabled ? 'ON' : 'OFF'}</span>
          </button>

          {/* Demo Mode Toggle */}
          <div className="flex items-center bg-gray-100 rounded-xl p-1 text-xs">
            <button
              type="button"
              onClick={() => {
                setIsDemoMode(false)
                setError('')
              }}
              className={`px-2.5 py-1 rounded-lg font-medium transition-all ${
                !isDemoMode ? 'bg-blue-600 text-white shadow-sm' : 'text-gray-600 hover:text-gray-900'
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
                isDemoMode ? 'bg-amber-600 text-white shadow-sm' : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Simulated Demo
            </button>
          </div>
        </div>
      </div>

      {/* ── ERROR BANNER ── */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-2xl p-4 shadow-sm flex items-start gap-3">
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

      {/* ── MAIN CONVERSATIONAL VIEWPORT & LIVE HUD ── */}
      <div className="grid lg:grid-cols-12 gap-6 items-start">
        {/* LEFT COLUMN: ACTIVE CONVERSATION THREAD (8 cols) */}
        <div className="lg:col-span-7 bg-white rounded-3xl border border-gray-200 p-6 shadow-sm flex flex-col h-[600px]">
          {/* Conversational Stream */}
          <div
            ref={chatScrollRef}
            className="flex-1 overflow-y-auto space-y-4 pr-1 scrollbar-thin scrollbar-thumb-gray-200"
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
                    <div className="w-9 h-9 rounded-2xl bg-blue-600 flex items-center justify-center text-white shrink-0 shadow">
                      <Bot className="w-5 h-5" />
                    </div>
                  )}

                  <div
                    className={`max-w-[85%] rounded-2xl p-4 text-xs leading-relaxed shadow-sm ${
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
                        {isAssistant ? 'ClaimSathi Voice Assistant' : 'You (Spoken)'}
                      </span>

                      {isAssistant && turn.audioText && (
                        <button
                          type="button"
                          onClick={() => speakText(turn.audioText!, turn.language)}
                          disabled={isSynthesizing}
                          className="inline-flex items-center gap-1 text-[11px] font-semibold text-blue-700 hover:text-blue-950 transition-colors"
                        >
                          {isTurnSpeaking ? (
                            <>
                              <VolumeX className="w-3.5 h-3.5 text-red-600 animate-pulse" /> Stop Voice
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

                    {/* Metadata pill */}
                    {(turn.latencyMs || turn.audioDuration || turn.language) && (
                      <div className="flex items-center gap-2 mt-2 pt-2 border-t border-black/10 text-[10px] text-gray-500">
                        {turn.language && <span>Lang: {turn.language}</span>}
                        {turn.audioDuration && <span>&bull; Audio: {turn.audioDuration}s</span>}
                        {turn.latencyMs && <span>&bull; Latency: {turn.latencyMs}ms</span>}
                      </div>
                    )}
                  </div>

                  {!isAssistant && (
                    <div className="w-9 h-9 rounded-2xl bg-gray-800 flex items-center justify-center text-white shrink-0 shadow">
                      <User className="w-5 h-5" />
                    </div>
                  )}
                </div>
              )
            })}

            {/* Live recording indicator in chat */}
            {isRecording && (
              <div className="flex items-center gap-3 justify-end animate-pulse">
                <div className="bg-red-50 border border-red-300 rounded-2xl p-3 text-xs text-red-700 flex items-center gap-2">
                  <Radio className="w-4 h-4 text-red-600 animate-ping" />
                  <span>Listening to your claim in Telugu / Hinglish... (00:{recordingSeconds < 10 ? `0${recordingSeconds}` : recordingSeconds})</span>
                </div>
              </div>
            )}

            {isAnswerRecording && (
              <div className="flex items-center gap-3 justify-end animate-pulse">
                <div className="bg-red-50 border border-red-300 rounded-2xl p-3 text-xs text-red-700 flex items-center gap-2">
                  <Radio className="w-4 h-4 text-red-600 animate-ping" />
                  <span>Listening to your answer... (00:{answerRecordingSeconds < 10 ? `0${answerRecordingSeconds}` : answerRecordingSeconds})</span>
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

          {/* ── BOTTOM INTERACTIVE VOICE CONTROLS ── */}
          <div className="mt-4 pt-4 border-t border-gray-200">
            {/* STAGE 1: INITIAL VOICE INTAKE */}
            {!hasStartedIntake ? (
              <div className="text-center">
                {!isRecording ? (
                  <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
                    <button
                      type="button"
                      onClick={startRecording}
                      className="w-full sm:w-auto inline-flex items-center justify-center gap-2.5 px-8 py-3.5 rounded-2xl bg-blue-600 text-white font-bold text-sm shadow hover:bg-blue-700 transition-all"
                    >
                      <Mic className="w-5 h-5" /> Speak Your Claim (Press to Talk)
                    </button>

                    <label className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-3.5 rounded-2xl border border-gray-300 text-gray-700 font-medium hover:bg-gray-50 transition-colors cursor-pointer text-xs">
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
                  /* While Recording Main Intake */
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
                        className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl bg-red-600 text-white font-semibold text-xs shadow hover:bg-red-700"
                      >
                        <Square className="w-4 h-4 fill-white" /> Finish &amp; Transcribe
                      </button>
                      <button
                        type="button"
                        onClick={cancelRecording}
                        className="px-4 py-2.5 rounded-xl border border-gray-300 text-xs font-medium text-gray-600 hover:bg-gray-50"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : missingFields.length > 0 && currentMissingField ? (
              /* STAGE 2: ANSWERING MISSING FIELD (VOICE PRIMARY, TEXT OPTIONAL) */
              <div className="bg-blue-50/60 rounded-2xl border border-blue-200 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-blue-900">
                    Answering: {currentMissingField.label}
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
                      className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-2.5 rounded-xl bg-emerald-600 text-white font-bold text-xs shadow hover:bg-emerald-700 transition-all shrink-0"
                    >
                      <Mic className="w-4 h-4" /> 🎙️ Speak Answer (e.g. "Ninna evening 5:30 PM")
                    </button>

                    <div className="w-full flex-1">
                      <MissingFieldInput
                        onSubmit={(val) => handleApplyAnswer(val, 'text')}
                      />
                    </div>
                  </div>
                ) : isAnswerRecording ? (
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-red-600 flex items-center gap-1.5">
                      <Radio className="w-4 h-4 animate-ping" /> Listening to your answer (00:
                      {answerRecordingSeconds < 10 ? `0${answerRecordingSeconds}` : answerRecordingSeconds})
                    </span>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={stopAnswerRecording}
                        className="px-4 py-1.5 rounded-xl bg-red-600 text-white text-xs font-bold shadow hover:bg-red-700"
                      >
                        <Square className="w-3.5 h-3.5 fill-white inline mr-1" /> Done Speaking
                      </button>
                      <button
                        type="button"
                        onClick={cancelAnswerRecording}
                        className="px-3 py-1.5 rounded-xl border border-gray-300 text-xs text-gray-600 hover:bg-gray-50"
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
              /* STAGE 3: ALL FIELDS COMPLETE -> CONFIRMATION READY */
              <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-emerald-50 border border-emerald-200 rounded-2xl p-4">
                <div className="flex items-center gap-2 text-emerald-800 text-xs font-bold">
                  <CheckCircle className="w-5 h-5 text-emerald-600 shrink-0" />
                  <span>All 5 claim details recorded via voice! Ready to submit.</span>
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
                    className="px-3 py-2 text-xs font-semibold text-gray-600 hover:text-gray-900 border rounded-xl"
                  >
                    Start New Voice
                  </button>
                  <button
                    type="button"
                    onClick={handleConfirmAndSubmit}
                    disabled={isSubmitting}
                    className="flex-1 sm:flex-initial inline-flex items-center justify-center gap-2 px-6 py-2.5 rounded-xl bg-emerald-600 text-white font-bold text-xs shadow hover:bg-emerald-700 transition-colors disabled:opacity-50"
                  >
                    {isSubmitting ? (
                      <>
                        <Spinner size="sm" /> Creating Ticket...
                      </>
                    ) : (
                      <>
                        <Check className="w-4 h-4" /> Confirm &amp; Create Demo Ticket
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* RIGHT COLUMN: LIVE CLAIM HUD / 5 STRUCTURED FIELDS (5 cols) */}
        <div className="lg:col-span-5 bg-white rounded-3xl border border-gray-200 p-6 shadow-sm space-y-5">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-bold text-sm text-gray-900">Extracted Claim Fields</h3>
              <p className="text-[11px] text-gray-400">Auto-filled in real-time from your speech</p>
            </div>
            <div className="flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
              <ShieldCheck className="w-4 h-4" />
              <span>{capturedCount} of 5 Captured</span>
            </div>
          </div>

          {/* Progress bar */}
          <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden border border-gray-200">
            <div
              className={`h-full transition-all duration-500 ${
                isAllCaptured ? 'bg-emerald-500' : 'bg-blue-600'
              }`}
              style={{ width: `${(capturedCount / 5) * 100}%` }}
            />
          </div>

          {/* 5 Field Rows with Inline Editing */}
          <div className="space-y-3">
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

          {/* Disclaimer */}
          <div className="bg-amber-50/80 border border-amber-200 rounded-2xl p-3.5 text-[11px] text-amber-800 leading-snug">
            <strong>Demonstration Claim Intake:</strong> Generates a local <code>DEMO-XXXXXXXX</code> ticket for demonstration purposes. No real claim is submitted.
          </div>
        </div>
      </div>
    </div>
  )
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

/* ── Optional Text Input Subcomponent ── */

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
        className="flex-1 rounded-xl border border-gray-300 bg-white px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500 shadow-sm"
        placeholder="Or type answer here..."
        value={val}
        onChange={(e) => setVal(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleSend()}
      />
      <button
        type="button"
        onClick={handleSend}
        disabled={!val.trim()}
        className="px-3.5 py-2 rounded-xl bg-blue-600 text-white text-xs font-semibold disabled:opacity-40 hover:bg-blue-700 transition-colors shadow-sm"
      >
        <Send className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}
