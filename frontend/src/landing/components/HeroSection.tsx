import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Mic,
  ShieldCheck,
  Camera,
  CheckCircle2,
  Play,
  Sparkles,
  Volume2,
  Square,
  Loader2,
} from 'lucide-react'
import { getStoredUser } from '../../api'
import { VOICE_PLAYGROUND_SCENARIOS } from '../data/landingData'
import { speakLandingText, stopLandingSpeech } from '../utils/landingSpeech'

interface HeroSectionProps {
  onOpenPilotModal: () => void
}

const WAVE_HEIGHTS = [16, 28, 20, 34, 24, 38, 18, 30, 22, 36, 20, 26]

export default function HeroSection({ onOpenPilotModal }: HeroSectionProps) {
  const isLoggedIn = Boolean(getStoredUser())
  const [heroAudioState, setHeroAudioState] = useState<'idle' | 'loading' | 'playing'>('idle')
  const heroSample = VOICE_PLAYGROUND_SCENARIOS[0]

  useEffect(() => {
    return () => stopLandingSpeech()
  }, [])

  const handleToggleHeroVoice = async () => {
    if (heroAudioState !== 'idle') {
      stopLandingSpeech()
      setHeroAudioState('idle')
      return
    }
    setHeroAudioState('loading')
    try {
      setHeroAudioState('playing')
      await speakLandingText(
        heroSample.speechTaggedReply,
        heroSample.assistantReply,
        heroSample.ttsLang,
        1.0,
      )
    } finally {
      setHeroAudioState('idle')
    }
  }

  return (
    <section id="top" className="relative overflow-hidden bg-white landing-grid-bg pt-14 pb-20 lg:pt-20 lg:pb-28">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid lg:grid-cols-12 gap-12 lg:gap-10 items-center">
          {/* Left Column: Value-First Outcome Copy + Dual Paths */}
          <div className="lg:col-span-6 space-y-6">
            <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-blue-50 border border-blue-200/80 text-brand-800 text-xs font-bold shadow-xs">
              <Sparkles className="w-3.5 h-3.5 text-brand-600" />
              <span>Built for Indian Motor Claims (2W &amp; 4W) &middot; IRDAI &amp; DPDP 2025 Ready</span>
            </div>

            <h1 className="text-4xl sm:text-5xl lg:text-[54px] font-extrabold tracking-tight text-slate-950 leading-[1.08]">
              Turn 45-Minute Motor Claims Into{' '}
              <span className="text-brand-600">4-Minute Audit-Ready Dossiers.</span>
            </h1>

            <p className="text-base sm:text-lg text-slate-600 leading-relaxed max-w-xl">
              Multilingual Indian voice intake in Hindi, Kannada, Telugu, Tamil &amp; Hinglish,
              paired with tokenized Live Camera forensics, pixel ANPR plate binding, and
              Make/Model INR repair cost bands—built for insurers, TPAs, and motor surveyors.
            </p>

            {/* Dual Conversion Path */}
            <div className="flex flex-wrap items-center gap-3.5 pt-1">
              <Link
                to={isLoggedIn ? '/claims/new' : '/login'}
                className="inline-flex items-center gap-2 px-6 py-3.5 rounded-2xl bg-brand-600 hover:bg-brand-700 text-white text-sm font-bold shadow-sm transition-all"
              >
                <span>Launch Live Intake Demo</span>
                <ArrowRight className="w-4 h-4" />
              </Link>
              <a
                href="#playground"
                className="inline-flex items-center gap-2 px-5 py-3.5 rounded-2xl bg-white hover:bg-slate-50 text-slate-800 border border-slate-200 text-sm font-bold shadow-xs transition-all"
              >
                <Play className="w-4 h-4 text-brand-600" />
                <span>Try Interactive Sandbox</span>
              </a>
              <button
                type="button"
                onClick={onOpenPilotModal}
                className="text-sm font-semibold text-slate-600 hover:text-brand-700 underline underline-offset-4 px-1"
              >
                Book Insurer / Surveyor Pilot
              </button>
            </div>

            {/* Concrete Proof Metrics */}
            <div className="pt-4 grid grid-cols-3 gap-4 border-t border-slate-200/80 max-w-lg">
              <div>
                <div className="text-xl sm:text-2xl font-extrabold text-slate-950">10+</div>
                <div className="text-xs font-medium text-slate-500">Indic &amp; Code-Mixed Voices</div>
              </div>
              <div>
                <div className="text-xl sm:text-2xl font-extrabold text-slate-950">5-Stage</div>
                <div className="text-xs font-medium text-slate-500">Live Anti-Fraud Screening</div>
              </div>
              <div>
                <div className="text-xl sm:text-2xl font-extrabold text-slate-950">Top 50</div>
                <div className="text-xs font-medium text-slate-500">Indian 2W/4W Cost Tiers</div>
              </div>
            </div>
          </div>

          {/* Right Column: Live Interactive Product Telemetry Card (Deep Midnight Contrast) */}
          <div className="lg:col-span-6">
            <div className="rounded-3xl bg-[#0B1220] border border-slate-800 shadow-2xl p-5 sm:p-6 text-white space-y-4">
              {/* Top Window Header */}
              <div className="flex items-center justify-between border-b border-slate-800 pb-3.5">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="landing-mono text-xs text-slate-300 font-semibold">
                    LIVE PIPELINE &middot; CS-2026-000142
                  </span>
                </div>
                <span className="landing-mono text-[11px] px-2.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-semibold">
                  PASS &middot; AUDIT READY
                </span>
              </div>

              {/* 1. Spoken Indic Voice -> Structured Slots */}
              <div className="rounded-2xl bg-slate-900/90 border border-slate-800 p-4 space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-xs font-bold text-blue-300">
                    <Mic className="w-4 h-4 text-brand-400" />
                    <span>Gnani Prisma STT + Timbre v3.0</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1 h-5">
                      {WAVE_HEIGHTS.map((h, i) => (
                        <span
                          key={i}
                          className={`w-1 rounded-full cs-wave-bar ${
                            heroAudioState === 'playing' ? 'bg-emerald-400' : 'bg-brand-400'
                          }`}
                          style={{
                            height: `${h}%`,
                            animationDelay: `${i * 0.09}s`,
                            animationDuration: heroAudioState === 'playing' ? '0.65s' : '1.35s',
                          }}
                        />
                      ))}
                    </div>
                    <button
                      type="button"
                      onClick={handleToggleHeroVoice}
                      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-bold transition-all ${
                        heroAudioState === 'idle'
                          ? 'bg-brand-600 hover:bg-brand-500 text-white'
                          : 'bg-rose-600 hover:bg-rose-500 text-white'
                      }`}
                    >
                      {heroAudioState === 'loading' ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : heroAudioState === 'playing' ? (
                        <Square className="w-3 h-3" />
                      ) : (
                        <Volume2 className="w-3 h-3" />
                      )}
                      <span>
                        {heroAudioState === 'loading'
                          ? 'Loading'
                          : heroAudioState === 'playing'
                          ? 'Stop'
                          : 'Listen Live'}
                      </span>
                    </button>
                  </div>
                </div>

                <p className="text-xs text-slate-300 italic leading-relaxed">
                  &ldquo;Meri Activa KA 01 MJ 4412 kal shaam Indiranagar signal par skid ho gayi, front mudguard aur headlamp toot gaya.&rdquo;
                </p>

                <div className="flex flex-wrap gap-1.5">
                  <span className="landing-mono text-[10px] px-2 py-0.5 rounded-md bg-blue-500/15 text-blue-300 border border-blue-500/25">
                    reg: KA-01-MJ-4412
                  </span>
                  <span className="landing-mono text-[10px] px-2 py-0.5 rounded-md bg-blue-500/15 text-blue-300 border border-blue-500/25">
                    type: Two-Wheeler
                  </span>
                  <span className="landing-mono text-[10px] px-2 py-0.5 rounded-md bg-blue-500/15 text-blue-300 border border-blue-500/25">
                    loc: Indiranagar
                  </span>
                  <span className="landing-mono text-[10px] px-2 py-0.5 rounded-md bg-emerald-500/15 text-emerald-300 border border-emerald-500/25">
                    tags: &lt;slow&gt; &lt;pauses&gt;
                  </span>
                </div>
              </div>

              {/* 2. Dual Grid: Stage 5 Live Capture Vision + Cost Band */}
              <div className="grid sm:grid-cols-2 gap-3">
                {/* Vision Box Mockup */}
                <div className="rounded-2xl bg-slate-900/90 border border-slate-800 p-3.5 space-y-2.5">
                  <div className="flex items-center justify-between text-[11px] font-bold text-emerald-300">
                    <span className="flex items-center gap-1.5">
                      <Camera className="w-3.5 h-3.5" /> Stage 5 Live Frame
                    </span>
                    <span className="landing-mono text-[10px] text-slate-400">CAP-48BIT</span>
                  </div>

                  {/* Stylized Detection Frame */}
                  <div className="relative h-24 rounded-xl bg-gradient-to-br from-slate-800 to-slate-950 border border-slate-700/80 overflow-hidden p-2">
                    <div className="absolute top-2.5 left-3 w-20 h-12 border-2 border-blue-400 rounded-sm bg-blue-500/10">
                      <span className="landing-mono absolute -top-4 left-0 bg-blue-600 text-[9px] px-1 rounded-xs text-white font-semibold">
                        2W 94%
                      </span>
                    </div>
                    <div className="absolute bottom-2.5 right-3 w-24 h-11 border-2 border-rose-400 rounded-sm bg-rose-500/15">
                      <span className="landing-mono absolute -top-4 right-0 bg-rose-600 text-[9px] px-1 rounded-xs text-white font-semibold">
                        headlamp 89%
                      </span>
                    </div>
                    <div className="absolute bottom-1.5 left-2 landing-mono text-[9px] text-emerald-300 bg-emerald-950/80 px-1.5 py-0.5 rounded-xs border border-emerald-700/50">
                      ANPR: KA-01-MJ-4412 MATCH
                    </div>
                  </div>
                </div>

                {/* Preliminary INR Cost Band + Compliance */}
                <div className="rounded-2xl bg-slate-900/90 border border-slate-800 p-3.5 flex flex-col justify-between space-y-2">
                  <div className="flex items-center justify-between text-[11px] font-bold text-slate-200">
                    <span>Preliminary Cost Band</span>
                    <span className="text-[10px] text-blue-300 font-semibold">Honda Activa 6G</span>
                  </div>
                  <div>
                    <div className="text-xl font-extrabold text-white tracking-tight">
                      ₹4,120 – ₹5,820
                    </div>
                    <div className="text-[10px] text-slate-400 mt-0.5">
                      For Surveyor / Adjuster Review Only
                    </div>
                  </div>
                  <div className="pt-2 border-t border-slate-800 space-y-1 text-[10px] text-emerald-300">
                    <div className="flex items-center gap-1.5">
                      <CheckCircle2 className="w-3 h-3 shrink-0" />
                      <span>64-bit DCT pHash: Unique</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <ShieldCheck className="w-3 h-3 shrink-0" />
                      <span>DPDP Consent &amp; IRDAI Audit Logged</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
