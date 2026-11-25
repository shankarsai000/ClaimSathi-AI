import {
  Mic,
  Camera,
  FileCheck2,
  ShieldAlert,
  Smartphone,
  Sliders,
  CheckCircle2,
  Car,
} from 'lucide-react'

const STEPS = [
  {
    num: '01',
    icon: Mic,
    title: 'Speak Naturally in Your Language',
    desc: 'Policyholders describe the incident hands-free in Hindi, Hinglish, Kannada, Telugu, Tamil, or English. Adaptive VAD & Layer 0 silence gating block roadside honking so zero scripted hallucinations occur.',
  },
  {
    num: '02',
    icon: Camera,
    title: 'WhatsApp → Tokenized Live Camera Lock',
    desc: 'Instead of accepting compressed WhatsApp photos that strip EXIF, ClaimSathi sends a single-use 48-bit browser link enforcing Live Camera capture of License Plate (ANPR), Odometer/VIN, Damage, and RC/DL.',
  },
  {
    num: '03',
    icon: FileCheck2,
    title: 'Explainable 9-Section Dossier & Adjuster Sign-Off',
    desc: 'Insurers & surveyors receive a Canonical JSON + PDF Dossier with YOLOv8 bounding boxes, 64-bit pHash deduplication, Make/Model INR repair cost bands, and IRDAI audit-ready override controls.',
  },
]

export default function WorkflowAndBento() {
  return (
    <>
      {/* 3-Step Workflow Section */}
      <section id="how-it-works" className="bg-white py-20 border-b border-slate-200/80">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-12">
          <div className="max-w-2xl space-y-3">
            <span className="landing-mono text-xs font-bold uppercase tracking-widest text-brand-600">
              End-to-End Motor Claims Flow
            </span>
            <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-slate-950">
              From Roadside Voice Note to Adjuster Sign-Off in 3 Steps
            </h2>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            {STEPS.map(({ num, icon: Icon, title, desc }) => (
              <div
                key={num}
                className="rounded-3xl bg-slate-50/80 border border-slate-200 p-6 space-y-4 hover:border-blue-300 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div className="w-11 h-11 rounded-2xl bg-brand-600 text-white flex items-center justify-center shadow-xs">
                    <Icon className="w-5 h-5" />
                  </div>
                  <span className="landing-mono text-2xl font-extrabold text-slate-300">{num}</span>
                </div>
                <h3 className="text-lg font-extrabold text-slate-950">{title}</h3>
                <p className="text-sm text-slate-600 leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Bento Grid: Anti-Fraud & Systems Engineering */}
      <section id="anti-fraud" className="bg-slate-50/60 py-20 border-b border-slate-200/80">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-12">
          <div className="max-w-2xl space-y-3">
            <span className="landing-mono text-xs font-bold uppercase tracking-widest text-brand-600">
              Built for Real Fraud Defense
            </span>
            <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-slate-950">
              Why ClaimSathi Stops Fraud That Naive Wrappers Miss
            </h2>
          </div>

          <div className="grid md:grid-cols-6 gap-5">
            {/* Wide Card 1 */}
            <div className="md:col-span-3 rounded-3xl bg-white border border-slate-200 p-6 shadow-xs space-y-3">
              <div className="w-10 h-10 rounded-xl bg-blue-50 text-brand-600 flex items-center justify-center">
                <Smartphone className="w-5 h-5" />
              </div>
              <h3 className="text-lg font-extrabold text-slate-950">
                WhatsApp-to-Live-Camera Handoff (Zero EXIF Loss)
              </h3>
              <p className="text-sm text-slate-600 leading-relaxed">
                Sending damage photos inside WhatsApp strips EXIF &amp; C2PA on arrival. ClaimSathi
                dispatches a 15-minute cryptographic browser link (`CAP-2026-...`) where device
                gallery uploads are strictly blocked by server validation (`HTTP 400`).
              </p>
            </div>

            {/* Wide Card 2 */}
            <div className="md:col-span-3 rounded-3xl bg-white border border-slate-200 p-6 shadow-xs space-y-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
                <Car className="w-5 h-5" />
              </div>
              <h3 className="text-lg font-extrabold text-slate-950">
                Symmetric Car-vs-Bike Guard + Pixel ANPR Binding
              </h3>
              <p className="text-sm text-slate-600 leading-relaxed">
                Blocks uploading a car photo under a two-wheeler policy—even on close-up bumper
                shots—and extracts the physical license plate via pixel OCR to catch swapped-vehicle
                fraud within the same category.
              </p>
            </div>

            {/* 3 Narrow Cards */}
            <div className="md:col-span-2 rounded-3xl bg-white border border-slate-200 p-6 shadow-xs space-y-3">
              <div className="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center">
                <ShieldAlert className="w-5 h-5" />
              </div>
              <h3 className="text-base font-extrabold text-slate-950">
                Honest Forensics Framing
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Treats C2PA/SynthID strictly as advisory signals—never falsely calling an image
                &ldquo;authentic&rdquo; when watermarks are absent. Primary defense rests on Live Capture + 64-bit
                DCT perceptual hashing.
              </p>
            </div>

            <div className="md:col-span-2 rounded-3xl bg-white border border-slate-200 p-6 shadow-xs space-y-3">
              <div className="w-10 h-10 rounded-xl bg-blue-50 text-brand-600 flex items-center justify-center">
                <Sliders className="w-5 h-5" />
              </div>
              <h3 className="text-base font-extrabold text-slate-950">
                Adjuster False-Positive Governance
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Every human override captures a structured reason tag (`FALSE_POSITIVE_GENUINE_DAMAGE`,
                etc.), feeding real-time IRDAI 2026 false-positive vs. false-negative dashboards.
              </p>
            </div>

            <div className="md:col-span-2 rounded-3xl bg-white border border-slate-200 p-6 shadow-xs space-y-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
                <FileCheck2 className="w-5 h-5" />
              </div>
              <h3 className="text-base font-extrabold text-slate-950">
                9-Section Dossier &amp; Canonical JSON
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Generates a downloadable PDF dossier, cryptographic SHA-256/pHash inventory, and
                Layer-1 Canonical JSON ready for core insurer gateway ingestion.
              </p>
            </div>
          </div>

          {/* Dual Persona Value Split */}
          <div className="grid md:grid-cols-2 gap-6 pt-4">
            <div className="rounded-3xl bg-white border border-slate-200 p-7 space-y-4">
              <span className="landing-mono text-[11px] font-bold uppercase text-brand-600">
                For Policyholders
              </span>
              <h3 className="text-xl font-extrabold text-slate-950">
                Zero Paperwork Confusion During Roadside Stress
              </h3>
              <ul className="space-y-2.5 text-sm text-slate-600">
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                  <span>Speaks your language with empathetic pacing—asks safety first on severe crashes.</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                  <span>Hands-free auto-pause microphone with instant spoken verification feedback.</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                  <span>One-tap consent withdrawal &amp; media erasure under DPDP Rules 2025.</span>
                </li>
              </ul>
            </div>

            <div className="rounded-3xl bg-[#0B1220] text-white border border-slate-800 p-7 space-y-4">
              <span className="landing-mono text-[11px] font-bold uppercase text-blue-300">
                For Insurers, TPAs &amp; Motor Surveyors
              </span>
              <h3 className="text-xl font-extrabold">
                Sub-₹50,000 Two-Wheeler &amp; Motor Triage at Scale
              </h3>
              <ul className="space-y-2.5 text-sm text-slate-300">
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                  <span>Cuts manual report compilation &amp; photo chasing from 45 minutes down to ~4 minutes.</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                  <span>Stops cross-claim image reuse, swapped plates, and car-under-bike mismatches early.</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                  <span>Explainable bounding boxes, cost bands, and immutable audit logs aligned with IRDAI 2026.</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </section>
    </>
  )
}
