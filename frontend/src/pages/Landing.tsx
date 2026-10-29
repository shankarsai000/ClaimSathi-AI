import { Link } from 'react-router-dom'
import { Shield, Mic, FileText, CheckCircle, ArrowRight } from 'lucide-react'
import DemoBadge from '../components/DemoBadge'

const steps = [
  { icon: Mic, title: 'Speak naturally', desc: 'Describe your claim in Hinglish or any Indian language mix.' },
  { icon: FileText, title: 'AI extracts details', desc: 'Policy, location, date, vehicle, and damage – auto-filled.' },
  { icon: CheckCircle, title: 'Review & confirm', desc: 'Verify the details, answer follow-ups, and submit.' },
]

export default function Landing() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Hero */}
      <section className="flex-1 flex items-center justify-center bg-gradient-to-br from-brand-50 via-white to-brand-50 px-4">
        <div className="max-w-3xl text-center py-20">
          <div className="flex items-center justify-center gap-2 mb-6">
            <Shield className="w-10 h-10 text-brand-600" />
            <h1 className="text-4xl sm:text-5xl font-extrabold text-brand-900 tracking-tight">
              ClaimSathi <span className="text-brand-500">AI</span>
            </h1>
          </div>
          <p className="text-lg sm:text-xl text-gray-600 mb-3 max-w-2xl mx-auto">
            Voice-first motor insurance claim intake – speak in Hinglish, let AI do the paperwork.
          </p>
          <DemoBadge className="mb-8" />
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mt-6">
            <Link
              to="/claims/new"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-brand-600 text-white font-semibold shadow-lg hover:bg-brand-700 transition-colors"
            >
              Start Demo Claim <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              to="/dashboard"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-white border border-gray-300 text-gray-700 font-semibold hover:bg-gray-50 transition-colors"
            >
              View Dashboard
            </Link>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="bg-white border-t py-16 px-4">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-2xl font-bold text-center text-gray-900 mb-10">How it works</h2>
          <div className="grid sm:grid-cols-3 gap-8">
            {steps.map(({ icon: Icon, title, desc }, i) => (
              <div key={i} className="text-center">
                <div className="mx-auto w-14 h-14 rounded-2xl bg-brand-50 flex items-center justify-center mb-4">
                  <Icon className="w-7 h-7 text-brand-600" />
                </div>
                <h3 className="font-semibold text-gray-900 mb-1">{title}</h3>
                <p className="text-sm text-gray-500">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-gray-50 border-t py-6 text-center text-xs text-gray-400">
        ClaimSathi AI – Phase 1 Demo. No real insurance claims are processed.
      </footer>
    </div>
  )
}
