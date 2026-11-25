import { ShieldCheck, Lock, ScanLine, Fingerprint, FileCheck2, Scale } from 'lucide-react'

const TRUST_ITEMS = [
  {
    icon: ScanLine,
    title: 'Layer 0 Silence Gate',
    sub: 'PCM RMS gating defeats honking & wind noise',
  },
  {
    icon: Lock,
    title: 'Live-Camera Lock',
    sub: 'Gallery upload blocked on WhatsApp handoff links',
  },
  {
    icon: ShieldCheck,
    title: 'Pixel ANPR Binding',
    sub: 'Extracts physical plate to catch swapped vehicles',
  },
  {
    icon: Fingerprint,
    title: '64-Bit DCT pHash',
    sub: 'Detects cropped & resized duplicate reuse',
  },
  {
    icon: Scale,
    title: 'IRDAI 2026 Governance',
    sub: 'Tracks false-positive adjuster override rates',
  },
  {
    icon: FileCheck2,
    title: 'DPDP Act 2025 Ready',
    sub: 'Unbundled pre-capture consent & media erasure',
  },
]

export default function TrustBar() {
  return (
    <section className="border-y border-slate-200 bg-slate-50/90 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-5">
          <span className="landing-mono text-[11px] font-semibold uppercase tracking-widest text-slate-500">
            Production-Hardened Architecture for Indian Insurers, TPAs &amp; Independent Surveyors
          </span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3.5">
          {TRUST_ITEMS.map(({ icon: Icon, title, sub }) => (
            <div
              key={title}
              className="rounded-2xl bg-white border border-slate-200/90 p-3.5 shadow-xs flex flex-col gap-1.5"
            >
              <div className="w-7 h-7 rounded-lg bg-blue-50 text-brand-600 flex items-center justify-center">
                <Icon className="w-4 h-4" />
              </div>
              <div className="text-xs font-bold text-slate-900">{title}</div>
              <div className="text-[11px] text-slate-500 leading-snug">{sub}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
