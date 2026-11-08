import { Link } from 'react-router-dom'
import {
  Shield,
  Mic,
  Camera,
  Fingerprint,
  FileCheck,
  Building2,
  ArrowRight,
  Lock,
} from 'lucide-react'
import DemoBadge from '../components/DemoBadge'

const features = [
  {
    icon: Lock,
    step: 'Step 1',
    title: 'Customer Account & Claims Vault',
    desc: 'Unique Customer ID (USR-100001) with consent tracking, encrypted claims vault, and full audit trail.',
  },
  {
    icon: Mic,
    step: 'Steps 2–4',
    title: '10+ Indian Languages Voice Intake',
    desc: 'Speak naturally in Telugu, Hindi, Kannada, Tamil, or English. AI extracts structured fields & asks targeted follow-ups.',
  },
  {
    icon: Camera,
    step: 'Step 5',
    title: 'Guided Live Camera & Evidence Capture',
    desc: 'Upload photos/videos or launch server-bound Live Camera Capture sessions with randomized vehicle angle prompts.',
  },
  {
    icon: Fingerprint,
    step: 'Step 6',
    title: 'Evidence Integrity & Provenance Engine',
    desc: 'C2PA Content Credentials & SynthID inspection, magic-byte validation, SHA-256 exact hash & 64-bit DCT pHash duplicate screening.',
  },
  {
    icon: FileCheck,
    step: 'Steps 7–8',
    title: '9-Section Professional Claim Dossier',
    desc: 'Customer review & declaration followed by a structured 9-section dossier, Layer 1 Canonical JSON, and downloadable binary PDF.',
  },
  {
    icon: Building2,
    step: 'Step 9',
    title: 'Layer 2 Insurer Adapter & Mock Gateway',
    desc: 'Maps canonical claim payloads into insurer-specific schemas and simulates end-to-end submission & acknowledgement.',
  },
]

export default function Landing() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Hero */}
      <section className="flex-1 flex items-center justify-center bg-gradient-to-br from-brand-50 via-white to-blue-50 px-4">
        <div className="max-w-4xl text-center py-16">
          <div className="flex items-center justify-center gap-2.5 mb-5">
            <Shield className="w-11 h-11 text-brand-600" />
            <h1 className="text-4xl sm:text-5xl font-extrabold text-brand-900 tracking-tight">
              ClaimSathi <span className="text-brand-500">AI</span>
            </h1>
          </div>
          <p className="text-lg sm:text-xl text-gray-700 font-medium mb-3 max-w-2xl mx-auto">
            Multilingual Insurance Claim Preparation, Evidence Integrity Screening &amp; Standardized Dossier Platform
          </p>
          <p className="text-sm text-gray-500 mb-6 max-w-2xl mx-auto">
            Helping customers explain incidents in their own language, verify photo/video evidence integrity with C2PA, SynthID, SHA-256 &amp; 64-bit pHash, and generate insurer-ready 9-section claim dossiers.
          </p>
          <DemoBadge className="mb-8" />
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mt-4">
            <Link
              to="/claims/new"
              className="inline-flex items-center gap-2 px-7 py-3.5 rounded-xl bg-brand-600 text-white font-semibold shadow-lg hover:bg-brand-700 transition-colors"
            >
              Start End-to-End Claim Wizard <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              to="/dashboard"
              className="inline-flex items-center gap-2 px-7 py-3.5 rounded-xl bg-white border border-gray-300 text-gray-700 font-semibold hover:bg-gray-50 transition-colors"
            >
              Open Customer Claims Vault (USR-100001)
            </Link>
          </div>
        </div>
      </section>

      {/* 9-Step Product Architecture */}
      <section className="bg-white border-t py-14 px-4">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-2xl font-bold text-center text-gray-900 mb-2">
            Complete 9-Step ClaimSathi AI Workflow
          </h2>
          <p className="text-sm text-gray-500 text-center mb-10">
            Built end-to-end with real cryptographic provenance inspection, perceptual hashing, and standardized insurer adapters
          </p>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map(({ icon: Icon, step, title, desc }, i) => (
              <div
                key={i}
                className="bg-gray-50/70 rounded-2xl border border-gray-200 p-5 hover:border-brand-300 transition-all"
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="w-11 h-11 rounded-xl bg-brand-50 border border-brand-100 flex items-center justify-center">
                    <Icon className="w-5 h-5 text-brand-600" />
                  </div>
                  <span className="text-[11px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                    {step}
                  </span>
                </div>
                <h3 className="font-bold text-gray-900 text-sm mb-1.5">{title}</h3>
                <p className="text-xs text-gray-600 leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-gray-50 border-t py-5 text-center text-xs text-gray-500">
        ClaimSathi AI – Complete Phases 1–7 Platform. Final claim approval remains with the licensed insurer.
      </footer>
    </div>
  )
}
