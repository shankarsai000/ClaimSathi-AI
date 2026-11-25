import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Shield, Lock, Scale, ChevronDown, ArrowRight, CheckCircle2, X } from 'lucide-react'
import { LANDING_FAQS } from '../data/landingData'
import { getStoredUser } from '../../api'

interface ComplianceFaqFooterProps {
  pilotModalOpen: boolean
  onOpenPilotModal: () => void
  onClosePilotModal: () => void
}

export default function ComplianceFaqFooter({
  pilotModalOpen,
  onOpenPilotModal,
  onClosePilotModal,
}: ComplianceFaqFooterProps) {
  const [openIdx, setOpenIdx] = useState<number | null>(0)
  const [pilotName, setPilotName] = useState('')
  const [pilotOrg, setPilotOrg] = useState('')
  const [pilotEmail, setPilotEmail] = useState('')
  const [pilotSubmitted, setPilotSubmitted] = useState(false)
  const isLoggedIn = Boolean(getStoredUser())

  const handlePilotSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!pilotName.trim() || !pilotEmail.trim()) return
    setPilotSubmitted(true)
  }

  return (
    <>
      {/* Governance & Compliance Trust Section */}
      <section id="compliance" className="bg-white py-20 border-b border-slate-200/80">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-14">
          <div className="max-w-2xl space-y-3">
            <span className="landing-mono text-xs font-bold uppercase tracking-widest text-brand-600">
              Regulatory &amp; Governance Posture
            </span>
            <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-slate-950">
              Engineered for IRDAI 2026 &amp; DPDP Act 2025 Audit Readiness
            </h2>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            <div className="rounded-3xl border border-slate-200 bg-slate-50/60 p-6 space-y-3">
              <div className="w-10 h-10 rounded-xl bg-blue-50 text-brand-600 flex items-center justify-center">
                <Scale className="w-5 h-5" />
              </div>
              <h3 className="text-base font-extrabold text-slate-950">
                Explainable Human-in-the-Loop
              </h3>
              <p className="text-sm text-slate-600 leading-relaxed">
                ClaimSathi AI never issues binding claim rejections or liability promises. Adjusters
                retain full override authority with tagged reasons tracking false-positive rates.
              </p>
            </div>

            <div className="rounded-3xl border border-slate-200 bg-slate-50/60 p-6 space-y-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
                <Lock className="w-5 h-5" />
              </div>
              <h3 className="text-base font-extrabold text-slate-950">
                Unbundled DPDP Consent &amp; Erasure
              </h3>
              <p className="text-sm text-slate-600 leading-relaxed">
                Purpose-scoped pre-capture consent recorded before voice or camera access, PII
                masking in handoff logs, and one-click media erasure while preserving statutory audit
                hashes.
              </p>
            </div>

            <div className="rounded-3xl border border-slate-200 bg-slate-50/60 p-6 space-y-3">
              <div className="w-10 h-10 rounded-xl bg-blue-50 text-brand-600 flex items-center justify-center">
                <Shield className="w-5 h-5" />
              </div>
              <h3 className="text-base font-extrabold text-slate-950">
                Immutable Cryptographic Provenance
              </h3>
              <p className="text-sm text-slate-600 leading-relaxed">
                Original media bytes are preserved intact with SHA-256 digests, 64-bit DCT pHash
                deduplication, and tamper-evident Canonical JSON + PDF dossiers.
              </p>
            </div>
          </div>

          {/* FAQ Accordion */}
          <div className="max-w-3xl mx-auto pt-4 space-y-6">
            <h3 className="text-2xl font-extrabold text-slate-950 text-center">
              CTO &amp; Claims Head FAQ
            </h3>
            <div className="space-y-3">
              {LANDING_FAQS.map((item, idx) => {
                const isOpen = openIdx === idx
                return (
                  <div
                    key={item.q}
                    className="rounded-2xl border border-slate-200 bg-white overflow-hidden"
                  >
                    <button
                      type="button"
                      onClick={() => setOpenIdx(isOpen ? null : idx)}
                      className="w-full px-5 py-4 text-left flex items-center justify-between gap-4 hover:bg-slate-50 transition-colors"
                    >
                      <span className="text-sm font-bold text-slate-900">{item.q}</span>
                      <ChevronDown
                        className={`w-4 h-4 text-slate-500 shrink-0 transition-transform ${
                          isOpen ? 'rotate-180' : ''
                        }`}
                      />
                    </button>
                    {isOpen && (
                      <div className="px-5 pb-4 text-sm text-slate-600 leading-relaxed border-t border-slate-100 pt-3">
                        {item.a}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </section>

      {/* High-Contrast Closing CTA Banner */}
      <section className="landing-dark-grid text-white py-20">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center space-y-6">
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
            Ready to Pilot Audit-Grade Motor Claims?
          </h2>
          <p className="text-base text-slate-300 max-w-2xl mx-auto">
            Try the complete 3-step voice intake, 5-stage computer vision screening, and 9-section
            insurer dossier live today—or schedule a surveyor copilot pilot for your team.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-4 pt-2">
            <Link
              to={isLoggedIn ? '/claims/new' : '/login'}
              className="inline-flex items-center gap-2 px-6 py-3.5 rounded-2xl bg-brand-600 hover:bg-brand-500 text-white text-sm font-bold shadow-lg transition-all"
            >
              <span>Launch Live ClaimSathi App</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
            <button
              type="button"
              onClick={onOpenPilotModal}
              className="px-6 py-3.5 rounded-2xl bg-white/10 hover:bg-white/15 border border-white/20 text-white text-sm font-bold transition-all"
            >
              Request Insurer / Surveyor Pilot
            </button>
          </div>
        </div>
      </section>

      {/* Clean Startup Footer */}
      <footer className="bg-[#070B14] text-slate-400 border-t border-slate-800/80 py-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-brand-500" />
            <span className="font-bold text-white">ClaimSathi AI</span>
            <span>&middot; Built in India for Motor Claims Automation</span>
          </div>
          <div className="flex items-center gap-6">
            <a href="#playground" className="hover:text-white transition-colors">
              Interactive Demo
            </a>
            <a href="#anti-fraud" className="hover:text-white transition-colors">
              Forensics
            </a>
            <a href="#compliance" className="hover:text-white transition-colors">
              DPDP &amp; IRDAI
            </a>
            <Link to="/login" className="hover:text-white transition-colors">
              Sign In
            </Link>
          </div>
          <div className="text-[11px] text-slate-500">
            &copy; {new Date().getFullYear()} ClaimSathi AI. Preliminary decision-support only.
          </div>
        </div>
      </footer>

      {/* Lightweight Book Pilot Modal */}
      {pilotModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl border border-slate-200 max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-extrabold text-slate-950">
                Request a 20-Case Motor Pilot
              </h3>
              <button
                type="button"
                onClick={() => {
                  setPilotSubmitted(false)
                  onClosePilotModal()
                }}
                className="p-1.5 rounded-lg text-slate-500 hover:bg-slate-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {pilotSubmitted ? (
              <div className="rounded-2xl bg-emerald-50 border border-emerald-200 p-4 space-y-2 text-emerald-950">
                <div className="flex items-center gap-2 font-bold text-sm">
                  <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                  Pilot Request Recorded
                </div>
                <p className="text-xs leading-relaxed">
                  Thanks, <strong>{pilotName}</strong>. You can also jump directly into the live
                  ClaimSathi sandbox right now to test voice intake and 5-stage image verification.
                </p>
                <div className="pt-2 flex gap-2">
                  <Link
                    to="/login"
                    className="px-4 py-2 rounded-xl bg-brand-600 text-white text-xs font-bold"
                  >
                    Open Live App
                  </Link>
                  <button
                    type="button"
                    onClick={() => {
                      setPilotSubmitted(false)
                      onClosePilotModal()
                    }}
                    className="px-4 py-2 rounded-xl border border-slate-200 text-xs font-semibold text-slate-700"
                  >
                    Close
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handlePilotSubmit} className="space-y-3">
                <p className="text-xs text-slate-600">
                  Ideal for IRDAI-licensed motor surveyors, fleet operators, and regional TPAs
                  evaluating 2W/4W triage accuracy.
                </p>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Full Name
                  </label>
                  <input
                    type="text"
                    required
                    value={pilotName}
                    onChange={(e) => setPilotName(e.target.value)}
                    placeholder="e.g. Rajesh Kumar"
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-xs text-slate-900"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Organization / Survey Firm / Workshop
                  </label>
                  <input
                    type="text"
                    value={pilotOrg}
                    onChange={(e) => setPilotOrg(e.target.value)}
                    placeholder="e.g. Apex Motor Surveyors, Bengaluru"
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-xs text-slate-900"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Work Email
                  </label>
                  <input
                    type="email"
                    required
                    value={pilotEmail}
                    onChange={(e) => setPilotEmail(e.target.value)}
                    placeholder="name@company.in"
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-xs text-slate-900"
                  />
                </div>
                <button
                  type="submit"
                  className="w-full py-2.5 rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-xs font-bold transition-colors"
                >
                  Request Pilot Walkthrough
                </button>
              </form>
            )}
          </div>
        </div>
      )}
    </>
  )
}
