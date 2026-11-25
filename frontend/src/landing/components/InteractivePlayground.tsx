import { useState, useRef, useEffect } from 'react'
import {
  Mic,
  Square,
  Volume2,
  ShieldAlert,
  IndianRupee,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  BrainCircuit,
  Loader2,
  Radio,
} from 'lucide-react'
import {
  VOICE_PLAYGROUND_SCENARIOS,
  FORENSICS_PLAYGROUND_SCENARIOS,
  VEHICLE_COST_TIERS,
} from '../data/landingData'
import { api } from '../../api'
import type { VoiceTranscribeResponse } from '../../types'
import { WavRecorder, type VadState } from '../../utils/wavRecorder'
import { speakLandingText, stopLandingSpeech } from '../utils/landingSpeech'

type PlaygroundTab = 'voice' | 'forensics' | 'pricing'
type VoiceMode = string // scenario id or 'live-mic'

const LIVE_MIC_LANGUAGES = [
  { code: 'indic-auto', label: 'Auto-Detect (Indic + English)' },
  { code: 'hi-IN', label: 'Hindi / Hinglish (hi-IN)' },
  { code: 'kn-IN', label: 'Kannada / Kanglish (kn-IN)' },
  { code: 'te-IN', label: 'Telugu / Tenglish (te-IN)' },
  { code: 'ta-IN', label: 'Tamil / Tanglish (ta-IN)' },
  { code: 'en-IN', label: 'Indian English (en-IN)' },
]

function formatInr(val: number) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(val)
}

export default function InteractivePlayground() {
  const [activeTab, setActiveTab] = useState<PlaygroundTab>('voice')
  const [voiceMode, setVoiceMode] = useState<VoiceMode>(VOICE_PLAYGROUND_SCENARIOS[0].id)
  const [forensicsId, setForensicsId] = useState(FORENSICS_PLAYGROUND_SCENARIOS[0].id)
  const [vehicleId, setVehicleId] = useState(VEHICLE_COST_TIERS[1].id)

  // Audio playback state
  const [speakingKey, setSpeakingKey] = useState<string | null>(null)

  // Live Zero-Login Mic Sandbox state
  const [liveLang, setLiveLang] = useState<string>('indic-auto')
  const [autoSpeakReply, setAutoSpeakReply] = useState<boolean>(true)
  const [isRecording, setIsRecording] = useState<boolean>(false)
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false)
  const [vadState, setVadState] = useState<VadState>('calibrating')
  const [audioVolume, setAudioVolume] = useState<number>(0)
  const [liveError, setLiveError] = useState<string>('')
  const [liveResult, setLiveResult] = useState<VoiceTranscribeResponse | null>(null)
  const recorderRef = useRef<WavRecorder | null>(null)
  const isRecordingRef = useRef<boolean>(false)
  const autoSpeakRef = useRef<boolean>(true)
  const liveLangRef = useRef<string>('indic-auto')

  useEffect(() => {
    autoSpeakRef.current = autoSpeakReply
  }, [autoSpeakReply])

  useEffect(() => {
    liveLangRef.current = liveLang
  }, [liveLang])

  useEffect(() => {
    return () => {
      stopLandingSpeech()
      if (recorderRef.current) {
        recorderRef.current.cancel()
        recorderRef.current = null
      }
    }
  }, [])

  const activeVoice =
    VOICE_PLAYGROUND_SCENARIOS.find((s) => s.id === voiceMode) || VOICE_PLAYGROUND_SCENARIOS[0]
  const activeForensic =
    FORENSICS_PLAYGROUND_SCENARIOS.find((s) => s.id === forensicsId) || FORENSICS_PLAYGROUND_SCENARIOS[0]
  const activeVehicle =
    VEHICLE_COST_TIERS.find((v) => v.id === vehicleId) || VEHICLE_COST_TIERS[0]

  const handleTogglePlay = async (
    key: string,
    speechText: string,
    cleanText: string,
    lang: string,
  ) => {
    if (speakingKey === key) {
      stopLandingSpeech()
      setSpeakingKey(null)
      return
    }
    setSpeakingKey(key)
    try {
      await speakLandingText(speechText, cleanText, lang, 1.0)
    } finally {
      setSpeakingKey((prev) => (prev === key ? null : prev))
    }
  }

  const handleStopAndAnalyzeLiveMic = async () => {
    if (!recorderRef.current || !isRecordingRef.current) return
    isRecordingRef.current = false
    setIsRecording(false)
    setAudioVolume(0)
    setIsAnalyzing(true)
    setLiveError('')

    try {
      const wavBlob = await recorderRef.current.stop()
      recorderRef.current = null
      const res = await api.transcribeVoice(
        wavBlob,
        'landing_sandbox.wav',
        false,
        liveLangRef.current,
      )
      setLiveResult(res)

      if (
        autoSpeakRef.current &&
        !res.no_speech_detected &&
        res.assistant_dialogue
      ) {
        const key = 'live-reply'
        setSpeakingKey(key)
        try {
          await speakLandingText(
            res.assistant_speech_text || res.assistant_dialogue,
            res.assistant_dialogue,
            res.assistant_language || res.detected_language || 'hi-IN',
            res.reasoning_trace?.speech_rate || 1.0,
          )
        } finally {
          setSpeakingKey((prev) => (prev === key ? null : prev))
        }
      }
    } catch (err: any) {
      setLiveError(err?.message || 'Microphone analysis failed. Please try speaking again.')
    } finally {
      setIsAnalyzing(false)
    }
  }

  const handleStartLiveMic = async () => {
    stopLandingSpeech()
    setSpeakingKey(null)
    setLiveError('')
    setVoiceMode('live-mic')

    try {
      const rec = new WavRecorder(
        16000,
        (vol) => setAudioVolume(vol),
        {
          autoStopOnSilence: true,
          silenceDurationMs: 1400,
          minSpeechMs: 250,
          onVadStateChange: (s) => setVadState(s),
          onAutoSilenceStop: () => {
            void handleStopAndAnalyzeLiveMic()
          },
          onInitialSilenceTimeout: () => {
            void handleStopAndAnalyzeLiveMic()
          },
        },
      )
      recorderRef.current = rec
      isRecordingRef.current = true
      setIsRecording(true)
      await rec.start()
    } catch (err: any) {
      isRecordingRef.current = false
      setIsRecording(false)
      setLiveError(
        err?.message ||
          'Microphone permission denied or unavailable in this browser.',
      )
    }
  }

  const computedLineItems = activeVehicle.sampleDamages.map((d) => {
    const part = Math.round(d.basePart * activeVehicle.multiplier)
    const labor = Math.round(d.labor * activeVehicle.multiplier)
    const subtotal = Math.round(part * d.severityMultiplier + labor)
    return { ...d, part, labor, subtotal }
  })
  const totalInr = computedLineItems.reduce((acc, item) => acc + item.subtotal, 0)
  const bandMin = Math.round(totalInr * 0.85)
  const bandMax = Math.round(totalInr * 1.2)

  // Live slot entries helper
  const liveSlotEntries: Array<[string, string | null]> = liveResult
    ? (liveResult.fields || []).map((f) => [f.name, f.value])
    : [
        ['policy_reference', null],
        ['vehicle_type', null],
        ['incident_location', null],
        ['incident_date', null],
        ['damage_description', null],
      ]

  return (
    <section id="playground" className="landing-dark-grid text-white py-20 lg:py-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-10">
        {/* Header */}
        <div className="max-w-3xl mx-auto text-center space-y-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/15 border border-blue-400/30 text-blue-300 text-xs font-bold">
            <BrainCircuit className="w-3.5 h-3.5" />
            <span>Interactive Voice &amp; Architecture Sandbox</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
            Hear &amp; Test ClaimSathi Live Before You Sign Up
          </h2>
          <p className="text-sm sm:text-base text-slate-300">
            Play real Gnani Timbre v3.0 voices across Indian languages, test your own microphone
            zero-login, or inspect our 5-stage anti-fraud &amp; Make/Model pricing engine.
          </p>
        </div>

        {/* 3-Tab Switcher */}
        <div className="flex flex-wrap justify-center gap-2.5">
          <button
            type="button"
            onClick={() => setActiveTab('voice')}
            className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-2xl text-xs sm:text-sm font-bold transition-all ${
              activeTab === 'voice'
                ? 'bg-brand-600 text-white shadow-md'
                : 'bg-slate-900 text-slate-300 border border-slate-800 hover:bg-slate-800'
            }`}
          >
            <Mic className="w-4 h-4" />
            <span>1. Live Indic Voice &amp; Mic Sandbox</span>
          </button>
          <button
            type="button"
            onClick={() => {
              stopLandingSpeech()
              setSpeakingKey(null)
              setActiveTab('forensics')
            }}
            className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-2xl text-xs sm:text-sm font-bold transition-all ${
              activeTab === 'forensics'
                ? 'bg-brand-600 text-white shadow-md'
                : 'bg-slate-900 text-slate-300 border border-slate-800 hover:bg-slate-800'
            }`}
          >
            <ShieldAlert className="w-4 h-4" />
            <span>2. 5-Stage Fraud &amp; ANPR Guard</span>
          </button>
          <button
            type="button"
            onClick={() => {
              stopLandingSpeech()
              setSpeakingKey(null)
              setActiveTab('pricing')
            }}
            className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-2xl text-xs sm:text-sm font-bold transition-all ${
              activeTab === 'pricing'
                ? 'bg-brand-600 text-white shadow-md'
                : 'bg-slate-900 text-slate-300 border border-slate-800 hover:bg-slate-800'
            }`}
          >
            <IndianRupee className="w-4 h-4" />
            <span>3. Make/Model Cost Band</span>
          </button>
        </div>

        {/* Tab 1: Voice AI & Live Mic Sandbox */}
        {activeTab === 'voice' && (
          <div className="rounded-3xl bg-slate-900/80 border border-slate-800 p-5 sm:p-7 space-y-6">
            {/* Mode / Scenario Pills */}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap gap-2">
                {VOICE_PLAYGROUND_SCENARIOS.map((sc) => (
                  <button
                    key={sc.id}
                    type="button"
                    onClick={() => {
                      stopLandingSpeech()
                      setSpeakingKey(null)
                      setVoiceMode(sc.id)
                    }}
                    className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all ${
                      voiceMode === sc.id
                        ? 'bg-blue-500/20 text-blue-300 border border-blue-400/50'
                        : 'bg-slate-950/70 text-slate-400 border border-slate-800 hover:text-white'
                    }`}
                  >
                    {sc.label}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => {
                    stopLandingSpeech()
                    setSpeakingKey(null)
                    setVoiceMode('live-mic')
                  }}
                  className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold transition-all ${
                    voiceMode === 'live-mic'
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-400/60 shadow-xs'
                      : 'bg-slate-950/70 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/10'
                  }`}
                >
                  <Radio className="w-3.5 h-3.5" />
                  <span>Try Live Mic (No Login)</span>
                </button>
              </div>
            </div>

            {voiceMode !== 'live-mic' ? (
              <div className="grid lg:grid-cols-12 gap-6 items-start">
                {/* Left: Preset Transcript, Tags & Live Audio Playback */}
                <div className="lg:col-span-7 space-y-4">
                  <div className="rounded-2xl bg-slate-950/80 border border-slate-800 p-4 space-y-2">
                    <div className="flex items-center justify-between text-[11px] text-slate-400">
                      <span className="font-bold text-blue-300">CUSTOMER SPOKEN INPUT</span>
                      <span className="landing-mono">{activeVoice.languageCode}</span>
                    </div>
                    <p className="text-sm text-white font-medium leading-relaxed">
                      &ldquo;{activeVoice.transcript}&rdquo;
                    </p>
                  </div>

                  <div className="rounded-2xl bg-slate-950/80 border border-slate-800 p-4 space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="landing-mono text-[10px] px-2 py-0.5 rounded-md bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                          intent: {activeVoice.intent}
                        </span>
                        <span className="landing-mono text-[10px] px-2 py-0.5 rounded-md bg-blue-500/15 text-blue-300 border border-blue-500/30">
                          emotion: {activeVoice.emotionBadge}
                        </span>
                        {activeVoice.gnaniTags.map((tag) => (
                          <span
                            key={tag}
                            className="landing-mono text-[10px] px-2 py-0.5 rounded-md bg-slate-800 text-slate-200 border border-slate-700"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>

                      <button
                        type="button"
                        onClick={() =>
                          void handleTogglePlay(
                            `preset-${activeVoice.id}`,
                            activeVoice.speechTaggedReply,
                            activeVoice.assistantReply,
                            activeVoice.ttsLang,
                          )
                        }
                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
                          speakingKey === `preset-${activeVoice.id}`
                            ? 'bg-rose-600 hover:bg-rose-500 text-white'
                            : 'bg-brand-600 hover:bg-brand-500 text-white'
                        }`}
                      >
                        {speakingKey === `preset-${activeVoice.id}` ? (
                          <>
                            <Square className="w-3.5 h-3.5" /> Stop Audio
                          </>
                        ) : (
                          <>
                            <Volume2 className="w-3.5 h-3.5" /> Listen (Gnani Timbre)
                          </>
                        )}
                      </button>
                    </div>

                    <p className="text-xs text-slate-400">
                      <strong className="text-slate-200">Reasoning Trace:</strong>{' '}
                      {activeVoice.thoughtProcess}
                    </p>
                    <div className="pt-2 border-t border-slate-800 text-sm text-blue-100 leading-relaxed">
                      <span className="text-[11px] font-bold uppercase text-brand-400 block mb-1">
                        ClaimSathi Expressive Reply ({activeVoice.ttsLang}):
                      </span>
                      &ldquo;{activeVoice.assistantReply}&rdquo;
                    </div>
                  </div>
                </div>

                {/* Right: Normalized English Insurer JSON */}
                <div className="lg:col-span-5 rounded-2xl bg-slate-950 border border-slate-800 p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
                    <span className="text-xs font-bold text-slate-200">
                      Normalized English Insurer Slots
                    </span>
                    <span className="landing-mono text-[10px] text-emerald-400">JSON_SCHEMA_OK</span>
                  </div>
                  <div className="space-y-2.5">
                    {Object.entries(activeVoice.extractedSlots).map(([k, v]) => (
                      <div
                        key={k}
                        className="flex items-center justify-between gap-3 rounded-xl bg-slate-900/90 border border-slate-800/80 px-3 py-2"
                      >
                        <span className="landing-mono text-[11px] text-slate-400">{k}</span>
                        <span
                          className={`text-xs font-semibold text-right ${
                            v ? 'text-emerald-300' : 'text-slate-500 italic'
                          }`}
                        >
                          {v || 'null (not assumed)'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              /* Zero-Login Live Mic Sandbox */
              <div className="grid lg:grid-cols-12 gap-6 items-start">
                <div className="lg:col-span-7 space-y-4">
                  {/* Mic Controls Card */}
                  <div className="rounded-2xl bg-slate-950/90 border border-slate-800 p-4 space-y-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="text-xs font-bold text-emerald-300 uppercase tracking-wide">
                          Zero-Login Live Voice Test (Prisma STT + Gemini + Timbre TTS)
                        </div>
                        <p className="text-[11px] text-slate-400 mt-0.5">
                          Speak a motor incident, say &ldquo;Hello&rdquo;, or stay silent to test Layer 0 noise gating.
                        </p>
                      </div>
                      <label className="inline-flex items-center gap-1.5 text-[11px] text-slate-300 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={autoSpeakReply}
                          onChange={(e) => setAutoSpeakReply(e.target.checked)}
                          className="rounded text-brand-600"
                        />
                        Auto-Speak Reply
                      </label>
                    </div>

                    <div className="flex flex-wrap items-center gap-3">
                      <select
                        value={liveLang}
                        disabled={isRecording || isAnalyzing}
                        onChange={(e) => setLiveLang(e.target.value)}
                        className="rounded-xl bg-slate-900 border border-slate-700 px-3 py-2 text-xs font-semibold text-white"
                      >
                        {LIVE_MIC_LANGUAGES.map((l) => (
                          <option key={l.code} value={l.code}>
                            {l.label}
                          </option>
                        ))}
                      </select>

                      {!isRecording ? (
                        <button
                          type="button"
                          disabled={isAnalyzing}
                          onClick={handleStartLiveMic}
                          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold shadow-xs disabled:opacity-60 transition-all"
                        >
                          {isAnalyzing ? (
                            <>
                              <Loader2 className="w-4 h-4 animate-spin" />
                              <span>Analyzing Audio...</span>
                            </>
                          ) : (
                            <>
                              <Mic className="w-4 h-4" />
                              <span>Tap Mic &amp; Speak (Auto-Pause)</span>
                            </>
                          )}
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={handleStopAndAnalyzeLiveMic}
                          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold animate-pulse"
                        >
                          <Square className="w-3.5 h-3.5" />
                          <span>Stop &amp; Analyze</span>
                        </button>
                      )}
                    </div>

                    {isRecording && (
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between text-[11px]">
                          <span className="landing-mono text-emerald-300">
                            VAD STATE: {vadState.toUpperCase()}
                          </span>
                          <span className="text-slate-400">Auto-submits after 1.4s pause</span>
                        </div>
                        <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
                          <div
                            className="h-full bg-emerald-400 transition-all duration-75"
                            style={{ width: `${Math.min(100, Math.round(audioVolume * 140))}%` }}
                          />
                        </div>
                      </div>
                    )}

                    {liveError && (
                      <div className="rounded-xl bg-rose-950/60 border border-rose-500/40 px-3 py-2 text-xs text-rose-200">
                        {liveError}
                      </div>
                    )}
                  </div>

                  {/* Live AI Response / Layer 0 Result */}
                  {liveResult && (
                    <div className="rounded-2xl bg-slate-950/90 border border-slate-800 p-4 space-y-3">
                      {liveResult.no_speech_detected ? (
                        <div className="rounded-xl bg-amber-950/50 border border-amber-500/40 p-3 text-xs text-amber-200">
                          <strong>Layer 0 Silence Gate Active:</strong> No speech detected in your
                          audio clip — zero hallucinated scripts triggered.
                        </div>
                      ) : (
                        <>
                          <div className="flex items-center justify-between text-[11px] text-slate-400">
                            <span className="font-bold text-blue-300">LIVE TRANSCRIPT</span>
                            <span className="landing-mono">
                              lang: {liveResult.detected_language || 'auto'} &middot;{' '}
                              {liveResult.reasoning_trace?.llm_provider || 'gemini'}
                            </span>
                          </div>
                          <p className="text-sm text-white font-medium">
                            &ldquo;{liveResult.transcript}&rdquo;
                          </p>

                          {liveResult.reasoning_trace && (
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="landing-mono text-[10px] px-2 py-0.5 rounded-md bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                                intent: {liveResult.reasoning_trace.detected_intent}
                              </span>
                              <span className="landing-mono text-[10px] px-2 py-0.5 rounded-md bg-blue-500/15 text-blue-300 border border-blue-500/30">
                                emotion: {liveResult.reasoning_trace.detected_emotion}
                              </span>
                              {(liveResult.reasoning_trace.applied_gnani_tags || []).map((t) => (
                                <span
                                  key={t}
                                  className="landing-mono text-[10px] px-2 py-0.5 rounded-md bg-slate-800 text-slate-200 border border-slate-700"
                                >
                                  {t}
                                </span>
                              ))}
                            </div>
                          )}

                          {liveResult.assistant_dialogue && (
                            <div className="pt-2 border-t border-slate-800 flex items-start justify-between gap-3">
                              <div className="text-sm text-blue-100 leading-relaxed">
                                &ldquo;{liveResult.assistant_dialogue}&rdquo;
                              </div>
                              <button
                                type="button"
                                onClick={() =>
                                  void handleTogglePlay(
                                    'live-reply',
                                    liveResult.assistant_speech_text || liveResult.assistant_dialogue || '',
                                    liveResult.assistant_dialogue || '',
                                    liveResult.assistant_language || 'hi-IN',
                                  )
                                }
                                className="shrink-0 inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-500 text-white text-[11px] font-bold"
                              >
                                {speakingKey === 'live-reply' ? (
                                  <Square className="w-3 h-3" />
                                ) : (
                                  <Volume2 className="w-3 h-3" />
                                )}
                                <span>{speakingKey === 'live-reply' ? 'Stop' : 'Replay'}</span>
                              </button>
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>

                {/* Right: Live Extracted English Slots */}
                <div className="lg:col-span-5 rounded-2xl bg-slate-950 border border-slate-800 p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
                    <span className="text-xs font-bold text-slate-200">
                      Live Extracted Insurer Slots
                    </span>
                    <span className="landing-mono text-[10px] text-emerald-400">
                      {liveResult ? 'LIVE_STT_OUTPUT' : 'WAITING_FOR_VOICE'}
                    </span>
                  </div>
                  <div className="space-y-2.5">
                    {liveSlotEntries.map(([k, v]) => (
                      <div
                        key={k}
                        className="flex items-center justify-between gap-3 rounded-xl bg-slate-900/90 border border-slate-800/80 px-3 py-2"
                      >
                        <span className="landing-mono text-[11px] text-slate-400">{k}</span>
                        <span
                          className={`text-xs font-semibold text-right ${
                            v ? 'text-emerald-300' : 'text-slate-500 italic'
                          }`}
                        >
                          {v || 'null'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: 5-Stage Forensics Playground */}
        {activeTab === 'forensics' && (
          <div className="rounded-3xl bg-slate-900/80 border border-slate-800 p-5 sm:p-7 space-y-6">
            <div className="flex flex-wrap gap-2">
              {FORENSICS_PLAYGROUND_SCENARIOS.map((sc) => (
                <button
                  key={sc.id}
                  type="button"
                  onClick={() => setForensicsId(sc.id)}
                  className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all ${
                    forensicsId === sc.id
                      ? 'bg-blue-500/20 text-blue-300 border border-blue-400/50'
                      : 'bg-slate-950/70 text-slate-400 border border-slate-800 hover:text-white'
                  }`}
                >
                  {sc.label}
                </button>
              ))}
            </div>

            <div className="grid lg:grid-cols-12 gap-6 items-start">
              {/* Visual Detection Overlay Preview */}
              <div className="lg:col-span-5 rounded-2xl bg-slate-950 border border-slate-800 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-200">
                    YOLOv8 + ANPR Inspection View
                  </span>
                  <span
                    className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-extrabold ${
                      activeForensic.decision === 'PASS'
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                        : activeForensic.decision === 'REJECT'
                        ? 'bg-red-500/20 text-red-300 border border-red-500/40'
                        : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                    }`}
                  >
                    {activeForensic.decision === 'PASS' && <CheckCircle2 className="w-3 h-3" />}
                    {activeForensic.decision === 'REJECT' && <XCircle className="w-3 h-3" />}
                    {activeForensic.decision === 'REVIEW' && <AlertTriangle className="w-3 h-3" />}
                    {activeForensic.decision}
                  </span>
                </div>

                <div className="relative h-52 rounded-xl bg-gradient-to-br from-slate-800 via-slate-900 to-slate-950 border border-slate-700/80 overflow-hidden">
                  {activeForensic.yoloBoxes.map((b, i) => (
                    <div
                      key={i}
                      style={{ top: b.top, left: b.left, width: b.width, height: b.height }}
                      className={`absolute border-2 rounded-sm ${
                        b.kind === 'vehicle'
                          ? 'border-blue-400 bg-blue-500/10'
                          : 'border-rose-400 bg-rose-500/15'
                      }`}
                    >
                      <span
                        className={`landing-mono absolute -top-4 left-0 text-[9px] px-1.5 py-0.2 rounded-xs font-bold text-white whitespace-nowrap ${
                          b.kind === 'vehicle' ? 'bg-blue-600' : 'bg-rose-600'
                        }`}
                      >
                        {b.label}
                      </span>
                    </div>
                  ))}
                  <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between text-[10px] landing-mono bg-slate-950/90 border border-slate-800 px-2.5 py-1.5 rounded-lg">
                    <span className="text-slate-300">Claimed: {activeForensic.claimedCategory}</span>
                    <span className="text-blue-300">Detected: {activeForensic.detectedCategory}</span>
                  </div>
                </div>
              </div>

              {/* 5-Stage Telemetry Output */}
              <div className="lg:col-span-7 rounded-2xl bg-slate-950 border border-slate-800 p-4 space-y-3">
                <div className="grid sm:grid-cols-2 gap-3">
                  <div className="rounded-xl bg-slate-900/90 border border-slate-800 p-3">
                    <div className="text-[10px] text-slate-400 uppercase font-bold">
                      Pixel ANPR Plate Binding
                    </div>
                    <div className="text-xs font-bold text-white mt-1">
                      {activeForensic.anprStatus}
                    </div>
                    <div className="landing-mono text-[11px] text-slate-400 mt-0.5">
                      Claimed: {activeForensic.claimedPlate} &middot; Read:{' '}
                      {activeForensic.anprDetectedPlate || 'N/A'}
                    </div>
                  </div>

                  <div className="rounded-xl bg-slate-900/90 border border-slate-800 p-3">
                    <div className="text-[10px] text-slate-400 uppercase font-bold">
                      64-Bit pHash &amp; Duplicate Check
                    </div>
                    <div className="text-xs font-bold text-white mt-1">
                      {activeForensic.phashStatus}
                    </div>
                    <div className="text-[11px] text-slate-400 mt-0.5">
                      {activeForensic.provenanceNote}
                    </div>
                  </div>
                </div>

                <div className="rounded-xl bg-slate-900/90 border border-slate-800 p-3">
                  <div className="text-[10px] text-slate-400 uppercase font-bold mb-1.5">
                    Stage 5 Audit Decision Codes
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {activeForensic.decisionCodes.map((code) => (
                      <span
                        key={code}
                        className="landing-mono text-[11px] px-2 py-0.5 rounded-md bg-slate-800 text-slate-200 border border-slate-700"
                      >
                        {code}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="rounded-xl bg-blue-950/40 border border-blue-800/40 p-3 flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-blue-200">
                    Outcome &amp; Repair Estimate Status:
                  </span>
                  <span className="text-xs sm:text-sm font-extrabold text-white">
                    {activeForensic.preliminaryBand}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: Make/Model Cost Band Calculator */}
        {activeTab === 'pricing' && (
          <div className="rounded-3xl bg-slate-900/80 border border-slate-800 p-5 sm:p-7 space-y-6">
            <div className="flex flex-wrap gap-2">
              {VEHICLE_COST_TIERS.map((v) => (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => setVehicleId(v.id)}
                  className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all ${
                    vehicleId === v.id
                      ? 'bg-blue-500/20 text-blue-300 border border-blue-400/50'
                      : 'bg-slate-950/70 text-slate-400 border border-slate-800 hover:text-white'
                  }`}
                >
                  {v.name} ({v.multiplier}x)
                </button>
              ))}
            </div>

            <div className="grid lg:grid-cols-12 gap-6 items-start">
              <div className="lg:col-span-7 overflow-x-auto rounded-2xl border border-slate-800 bg-slate-950">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400">
                      <th className="py-3 px-4">Detected Damage Component</th>
                      <th className="py-3 px-3">OEM Base + Labor</th>
                      <th className="py-3 px-3">Severity Mult</th>
                      <th className="py-3 px-4 text-right">Line Estimate</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/80">
                    {computedLineItems.map((item) => (
                      <tr key={item.part}>
                        <td className="py-3 px-4 font-semibold text-white">{item.part}</td>
                        <td className="py-3 px-3 text-slate-300">
                          {formatInr(item.part)} + {formatInr(item.labor)}
                        </td>
                        <td className="py-3 px-3 landing-mono text-blue-300">
                          {item.severityMultiplier}x
                        </td>
                        <td className="py-3 px-4 text-right font-bold text-white">
                          {formatInr(item.subtotal)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="lg:col-span-5 rounded-2xl bg-slate-950 border border-slate-800 p-5 space-y-3">
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span>{activeVehicle.category}</span>
                  <span className="landing-mono text-blue-300">
                    {activeVehicle.tierLabel} ({activeVehicle.multiplier}x)
                  </span>
                </div>
                <div>
                  <div className="text-xs font-semibold text-slate-400">
                    Preliminary AI Repair Cost Band (0.85x – 1.20x)
                  </div>
                  <div className="text-2xl sm:text-3xl font-extrabold text-emerald-300 mt-1">
                    {formatInr(bandMin)} – {formatInr(bandMax)}
                  </div>
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed border-t border-slate-800 pt-3">
                  Preliminary AI Repair Cost Band for Surveyor/Adjuster Review Only. Final coverage
                  liability and settlement rest solely with the licensed insurer/TPA under IRDAI
                  guidelines.
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
