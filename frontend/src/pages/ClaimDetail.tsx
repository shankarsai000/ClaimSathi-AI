import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api'
import type {
  ClaimRecord,
  TimelineEvent,
  EvidenceAssetRecord,
  ReportRecord,
  InsurerSubmissionResponse,
  AuditLogEntry,
} from '../types'
import Spinner from '../components/Spinner'
import StatusBadge from '../components/StatusBadge'
import DemoBadge from '../components/DemoBadge'
import { playAudioBlob, stopAudio } from '../utils/audioPlayer'
import {
  ArrowLeft,
  FileText,
  AlertCircle,
  Clock,
  Volume2,
  VolumeX,
  Download,
  FileCode,
  ShieldCheck,
  Building2,
  Fingerprint,
  RefreshCw,
  CheckCircle2,
  Upload,
  Video,
  Send,
} from 'lucide-react'

const SECTION_TITLES: { key: string; num: string; title: string }[] = [
  { key: 'section_1_claim_header', num: '01', title: 'Claim Header' },
  { key: 'section_2_policyholder_profile', num: '02', title: 'Policyholder Profile' },
  { key: 'section_3_policy_and_asset_details', num: '03', title: 'Policy and Asset Details' },
  { key: 'section_4_incident_summary', num: '04', title: 'Incident Summary' },
  { key: 'section_5_structured_damage_report', num: '05', title: 'Structured Damage Report' },
  { key: 'section_6_evidence_inventory_and_screening', num: '06', title: 'Evidence Inventory & Screening Summary' },
  { key: 'section_7_completeness_and_validation_checklist', num: '07', title: 'Completeness & Validation Checklist' },
  { key: 'section_8_customer_declaration_and_confirmation', num: '08', title: 'Customer Declaration & Confirmation' },
  { key: 'section_9_audit_and_system_metadata', num: '09', title: 'Audit & System Metadata' },
]

export default function ClaimDetail() {
  const { id } = useParams<{ id: string }>()
  const [claim, setClaim] = useState<ClaimRecord | null>(null)
  const [timeline, setTimeline] = useState<TimelineEvent[]>([])
  const [evidence, setEvidence] = useState<EvidenceAssetRecord[]>([])
  const [reports, setReports] = useState<ReportRecord[]>([])
  const [submissions, setSubmissions] = useState<InsurerSubmissionResponse[]>([])
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([])

  const [activeTab, setActiveTab] = useState<'dossier' | 'evidence' | 'gateway' | 'timeline'>('dossier')
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedRecipient, setSelectedRecipient] = useState('DEMO_INSURER_A')
  const [showCanonicalJson, setShowCanonicalJson] = useState(false)

  const [isPlayingAudio, setIsPlayingAudio] = useState(false)
  const [isSynthesizing, setIsSynthesizing] = useState(false)

  const loadClaimFull = async () => {
    if (!id) return
    setLoading(true)
    setError('')
    try {
      const data = await api.getClaim(id)
      setClaim(data.claim)
      setTimeline(data.timeline || [])
      setEvidence(data.evidence || [])
      setReports(data.reports || [])
      setSubmissions(data.insurer_submissions || [])
      setAuditLogs(data.audit_logs || [])

      // Auto-generate v1.0 dossier if none exists yet
      if (!data.reports || data.reports.length === 0) {
        const rep = await api.generateReport(id)
        setReports([rep])
      }
    } catch (e: any) {
      setError(e.message || 'Failed to load claim dossier.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadClaimFull()
    return () => {
      stopAudio()
    }
  }, [id])

  const handleRegenerateReport = async () => {
    if (!id) return
    setActionLoading(true)
    setError('')
    try {
      await api.generateReport(id)
      await loadClaimFull()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setActionLoading(false)
    }
  }

  const handleSubmitToInsurer = async () => {
    if (!id) return
    setActionLoading(true)
    setError('')
    try {
      await api.submitToInsurer(id, selectedRecipient)
      await loadClaimFull()
      setActiveTab('gateway')
    } catch (e: any) {
      setError(e.message)
    } finally {
      setActionLoading(false)
    }
  }

  const handleUploadMoreEvidence = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!id || !e.target.files?.length) return
    setActionLoading(true)
    setError('')
    try {
      for (let i = 0; i < e.target.files.length; i++) {
        const file = e.target.files[i]
        const isVideo = file.type.startsWith('video/')
        await api.uploadEvidence(id, file, file.name, isVideo ? 'upload_video' : 'upload_photo')
      }
      await api.generateReport(id)
      await loadClaimFull()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  const handlePlayTranscript = async () => {
    if (isPlayingAudio) {
      stopAudio()
      setIsPlayingAudio(false)
      return
    }
    if (!claim?.transcript) return
    setIsSynthesizing(true)
    try {
      const audioBlob = await api.synthesizeSpeech(claim.transcript, {
        language: 'hi-IN',
        voice: 'Nalini',
      })
      setIsSynthesizing(false)
      setIsPlayingAudio(true)
      await playAudioBlob(audioBlob)
      setIsPlayingAudio(false)
    } catch (err: any) {
      setIsSynthesizing(false)
      setIsPlayingAudio(false)
      setError(`TTS synthesis error: ${err.message}`)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Spinner size="lg" />
      </div>
    )
  }

  if (error && !claim) {
    return (
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 rounded-xl p-4">
          <AlertCircle className="w-5 h-5 shrink-0" /> {error || 'Claim not found.'}
        </div>
        <Link
          to="/dashboard"
          className="inline-flex items-center gap-1 text-sm text-blue-600 mt-4 hover:underline"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Customer Claims Vault
        </Link>
      </div>
    )
  }

  if (!claim) return null
  const latestReport = reports[0] || null

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* ── TOP BREADCRUMB & HEADER ── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white rounded-3xl border border-gray-200 p-6 shadow-xs">
        <div>
          <Link
            to="/dashboard"
            className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 mb-2 hover:underline"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Back to Customer Claims Vault ({claim.customer_id})
          </Link>
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-2xl font-extrabold text-gray-900 font-mono">{claim.id}</h1>
            <StatusBadge status={claim.status} />
            <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-purple-50 text-purple-800 border border-purple-200">
              Dossier v{latestReport?.version || claim.report_version || '1.0'}
            </span>
            <DemoBadge />
          </div>
          <p className="text-xs text-gray-500 mt-1">
            Policy: <strong className="text-gray-800">{claim.policy_reference}</strong> &bull; Customer:{' '}
            <strong className="text-gray-800">{claim.policy_holder_name} ({claim.customer_id})</strong> &bull; Vehicle:{' '}
            <strong className="text-gray-800 capitalize">{claim.vehicle_type}</strong>
          </p>
        </div>

        {/* Download & Gateway Action Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          <a
            href={api.getReportPdfUrl(claim.id)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-brand-600 text-white text-xs font-bold hover:bg-brand-700 shadow-xs"
          >
            <Download className="w-4 h-4" /> Download Binary PDF Dossier
          </a>
          <a
            href={api.getReportJsonUrl(claim.id)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl bg-white border border-gray-300 text-gray-800 text-xs font-semibold hover:bg-gray-50"
          >
            <FileCode className="w-4 h-4 text-blue-600" /> Layer 1 Canonical JSON
          </a>
          <button
            type="button"
            onClick={handleRegenerateReport}
            disabled={actionLoading}
            className="inline-flex items-center gap-1.5 px-3 py-2.5 rounded-xl bg-white border border-gray-200 text-gray-600 text-xs font-semibold hover:bg-gray-50"
            title="Regenerate a new versioned dossier report"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${actionLoading ? 'animate-spin' : ''}`} />
            New Version
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 rounded-2xl p-4 text-xs">
          <AlertCircle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}

      {/* ── NAVIGATION TABS ── */}
      <div className="flex flex-wrap items-center gap-2 border-b border-gray-200 pb-2">
        {[
          {
            id: 'dossier',
            label: '9-Section Professional Claim Dossier',
            icon: FileText,
          },
          {
            id: 'evidence',
            label: `Screened Evidence Inventory (${evidence.length})`,
            icon: Fingerprint,
          },
          {
            id: 'gateway',
            label: `Mock Insurer Integration Gateway (${submissions.length})`,
            icon: Building2,
          },
          {
            id: 'timeline',
            label: 'Transcript, Timeline & Audit Trail',
            icon: Clock,
          },
        ].map(({ id: tabId, label, icon: Icon }) => (
          <button
            key={tabId}
            type="button"
            onClick={() => setActiveTab(tabId as any)}
            className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-2xl text-xs font-bold transition-all ${
              activeTab === tabId
                ? 'bg-brand-600 text-white shadow-xs'
                : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      {/* =====================================================================
          TAB 1: 9-SECTION PROFESSIONAL CLAIM DOSSIER (STEP 8 OF PDF)
         ===================================================================== */}
      {activeTab === 'dossier' && latestReport && (
        <div className="space-y-5">
          {/* Layer 1 Canonical Schema Toggle */}
          <div className="bg-slate-900 text-slate-100 rounded-2xl p-4 flex flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <FileCode className="w-5 h-5 text-blue-400" />
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-blue-300">
                    Layer 1 — ClaimSathi Canonical Claim Schema ({latestReport.report_id} &bull; v{latestReport.version})
                  </h3>
                  <p className="text-[11px] text-slate-400">
                    Standardized internal format ready for Layer 2 Insurer Adapter mapping
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowCanonicalJson(!showCanonicalJson)}
                className="px-3 py-1.5 rounded-xl bg-slate-800 border border-slate-700 text-xs font-semibold text-blue-300 hover:bg-slate-700"
              >
                {showCanonicalJson ? 'Hide Canonical JSON' : 'Inspect Canonical JSON Schema'}
              </button>
            </div>
            {showCanonicalJson && (
              <pre className="text-[11px] font-mono bg-black/50 p-4 rounded-xl overflow-x-auto text-emerald-300 max-h-80">
                {JSON.stringify(latestReport.canonical_schema, null, 2)}
              </pre>
            )}
          </div>

          {/* 9 Sections Grid */}
          <div className="grid md:grid-cols-2 gap-5">
            {SECTION_TITLES.map(({ key, num, title }) => {
              const secData = (latestReport.dossier as any)[key] || {}
              return (
                <div
                  key={key}
                  className={`bg-white rounded-2xl border border-gray-200 p-5 shadow-xs ${
                    key === 'section_6_evidence_inventory_and_screening' ? 'md:col-span-2' : ''
                  }`}
                >
                  <div className="flex items-center gap-2.5 border-b border-gray-100 pb-3 mb-3">
                    <span className="w-7 h-7 rounded-xl bg-brand-50 border border-brand-200 text-brand-700 font-bold text-xs flex items-center justify-center">
                      {num}
                    </span>
                    <h3 className="font-bold text-gray-900 text-sm">
                      Section {num} — {title}
                    </h3>
                  </div>

                  <dl className="grid sm:grid-cols-2 gap-3 text-xs">
                    {Object.entries(secData).map(([k, v]) => (
                      <div
                        key={k}
                        className={`bg-gray-50/80 rounded-xl p-3 border border-gray-100 ${
                          Array.isArray(v) || typeof v === 'object' ? 'sm:col-span-2' : ''
                        }`}
                      >
                        <dt className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-1">
                          {k.replace(/_/g, ' ')}
                        </dt>
                        <dd className="text-gray-800 font-medium break-words">
                          {Array.isArray(v) ? (
                            v.length === 0 ? (
                              <span className="text-gray-400 italic">None</span>
                            ) : (
                              <ul className="list-disc list-inside space-y-1">
                                {v.map((item, idx) => (
                                  <li key={idx} className="text-xs">
                                    {typeof item === 'object' ? JSON.stringify(item) : String(item)}
                                  </li>
                                ))}
                              </ul>
                            )
                          ) : typeof v === 'object' && v !== null ? (
                            <pre className="text-[11px] font-mono bg-white p-2 rounded border overflow-x-auto">
                              {JSON.stringify(v, null, 2)}
                            </pre>
                          ) : (
                            String(v ?? 'N/A')
                          )}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* =====================================================================
          TAB 2: SCREENED EVIDENCE INVENTORY (STEP 5 & 6 OF PDF)
         ===================================================================== */}
      {activeTab === 'evidence' && (
        <div className="bg-white rounded-3xl border border-gray-200 p-6 shadow-xs space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-lg font-bold text-gray-900">
                Evidence Integrity &amp; Provenance Inventory ({evidence.length} files)
              </h2>
              <p className="text-xs text-gray-500">
                Cryptographic SHA-256, 64-bit DCT perceptual hash (pHash), magic-byte verification, and C2PA/SynthID provenance results
              </p>
            </div>
            <label className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-600 text-white text-xs font-bold cursor-pointer hover:bg-blue-700">
              <Upload className="w-4 h-4" /> Upload Additional Evidence
              <input
                type="file"
                multiple
                accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm"
                className="hidden"
                onChange={handleUploadMoreEvidence}
              />
            </label>
          </div>

          {evidence.length === 0 ? (
            <div className="text-center py-12 bg-gray-50 rounded-2xl border border-gray-200 text-xs text-gray-500">
              No evidence files attached to this claim yet. Click "Upload Additional Evidence" above to screen photos or videos.
            </div>
          ) : (
            <div className="grid md:grid-cols-2 gap-4">
              {evidence.map((ev) => {
                const scr = ev.screening
                const isFlagged = scr?.requires_human_review
                return (
                  <div
                    key={ev.asset_id}
                    className={`rounded-2xl border p-4 flex gap-4 ${
                      isFlagged ? 'bg-amber-50/60 border-amber-300' : 'bg-gray-50/60 border-gray-200'
                    }`}
                  >
                    {ev.media_type === 'image' ? (
                      <img
                        src={api.getEvidenceFileUrl(ev.asset_id)}
                        alt={ev.label}
                        className="w-28 h-28 rounded-xl object-cover border border-gray-200 shrink-0 bg-white"
                      />
                    ) : (
                      <div className="w-28 h-28 rounded-xl bg-slate-900 text-white flex flex-col items-center justify-center text-xs font-bold shrink-0">
                        <Video className="w-6 h-6 mb-1 text-blue-400" />
                        {ev.label}
                      </div>
                    )}

                    <div className="flex-1 min-w-0 space-y-1 text-xs">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-bold text-gray-900">
                          {ev.label} &bull; {ev.original_filename}
                        </span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                            isFlagged ? 'bg-red-100 text-red-800' : 'bg-emerald-100 text-emerald-800'
                          }`}
                        >
                          {isFlagged ? '⚠️ Human Review' : '✓ Passed'}
                        </span>
                      </div>

                      <div className="text-[11px] text-gray-500">
                        Method: <strong>{ev.capture_method}</strong>
                        {ev.capture_session_id && (
                          <span className="ml-2 font-mono text-emerald-700 font-bold">
                            [{ev.capture_session_id}]
                          </span>
                        )}
                      </div>

                      {scr && (
                        <div className="pt-1 space-y-1">
                          <div className="font-semibold text-gray-800">
                            {scr.screening_outcome_label}
                          </div>
                          <div className="text-[11px] text-gray-600">{scr.provenance_summary}</div>
                          <div className="text-[10px] font-mono text-gray-500 bg-white p-2 rounded-lg border border-gray-200 space-y-0.5">
                            <div className="truncate">SHA-256: {scr.sha256_hash}</div>
                            {scr.phash_hex && <div>64-bit pHash: {scr.phash_hex}</div>}
                            <div>
                              Duplicate Status: <strong>{scr.duplicate_status}</strong>
                              {scr.matched_claim_id && ` (Matched ${scr.matched_claim_id})`}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* =====================================================================
          TAB 3: MOCK INSURER INTEGRATION GATEWAY (PHASE 7 / PAGES 10–11 OF PDF)
         ===================================================================== */}
      {activeTab === 'gateway' && (
        <div className="bg-white rounded-3xl border border-gray-200 p-6 shadow-xs space-y-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-gray-100 pb-4">
            <div>
              <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                <Building2 className="w-5 h-5 text-brand-600" />
                Layer 2 — Insurer Adapter Layer &amp; Mock Insurer Integration Gateway
              </h2>
              <p className="text-xs text-gray-500 mt-0.5">
                Maps the Layer 1 ClaimSathi Canonical Schema into insurer-specific formats and simulates end-to-end submission &amp; acknowledgement.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <select
                value={selectedRecipient}
                onChange={(e) => setSelectedRecipient(e.target.value)}
                className="rounded-xl border border-gray-300 px-3 py-2 text-xs font-semibold bg-white"
              >
                <option value="DEMO_INSURER_A">DEMO_INSURER_A (Official Insurer REST API)</option>
                <option value="DEMO_INSURER_B">DEMO_INSURER_B (Regional Portal Form Adapter)</option>
                <option value="DEMO_INSURER_C">DEMO_INSURER_C (TPA Email Package Adapter)</option>
              </select>

              <button
                type="button"
                onClick={handleSubmitToInsurer}
                disabled={actionLoading}
                className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-emerald-600 text-white text-xs font-bold hover:bg-emerald-700 shadow-xs disabled:opacity-50"
              >
                <Send className="w-3.5 h-3.5" />
                {actionLoading ? 'Transmitting...' : 'Submit to Mock Insurer Gateway'}
              </button>
            </div>
          </div>

          {submissions.length === 0 ? (
            <div className="text-center py-12 bg-gray-50 rounded-2xl border border-gray-200">
              <Building2 className="w-10 h-10 text-gray-300 mx-auto mb-2" />
              <p className="text-sm font-semibold text-gray-700">No insurer gateway submissions yet</p>
              <p className="text-xs text-gray-500 mt-1 mb-4">
                Select an insurer adapter above and click "Submit to Mock Insurer Gateway" to simulate transmission.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {submissions.map((sub) => (
                <div
                  key={sub.submission_id}
                  className="rounded-2xl border border-emerald-200 bg-emerald-50/40 p-5 space-y-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-sm text-emerald-950">
                          {sub.submission_id}
                        </span>
                        <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">
                          {sub.delivery_status}
                        </span>
                        <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-blue-100 text-blue-800">
                          Insurer Ref: {sub.insurer_claim_reference}
                        </span>
                      </div>
                      <p className="text-xs text-gray-600 mt-1">
                        Recipient: <strong>{sub.recipient_display_name}</strong> ({sub.recipient}) &bull; Processing Status:{' '}
                        <strong className="uppercase text-emerald-800">{sub.processing_status}</strong>
                      </p>
                    </div>
                    <span className="text-xs font-semibold text-amber-800 bg-amber-100 px-3 py-1 rounded-full">
                      {sub.disclaimer}
                    </span>
                  </div>

                  {/* 5-Step Pipeline Visualization */}
                  <div className="grid sm:grid-cols-5 gap-2">
                    {sub.pipeline_steps.map((st, idx) => (
                      <div
                        key={idx}
                        className="bg-white rounded-xl border border-emerald-200 p-3 text-xs"
                      >
                        <div className="flex items-center gap-1.5 font-bold text-emerald-800 mb-1">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                          <span className="truncate">{st.step}</span>
                        </div>
                        <p className="text-[11px] text-gray-600 leading-snug">{st.detail}</p>
                      </div>
                    ))}
                  </div>

                  {/* Mapped Adapter Payload */}
                  <details className="bg-white rounded-xl border border-gray-200 p-3 text-xs">
                    <summary className="font-bold text-gray-800 cursor-pointer">
                      Inspect Layer 2 Adapter Mapped Payload ({sub.recipient})
                    </summary>
                    <pre className="mt-2 text-[11px] font-mono bg-slate-900 text-emerald-300 p-3 rounded-lg overflow-x-auto">
                      {JSON.stringify(sub.mapped_payload_preview, null, 2)}
                    </pre>
                  </details>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* =====================================================================
          TAB 4: TRANSCRIPT, TIMELINE & AUDIT TRAIL
         ===================================================================== */}
      {activeTab === 'timeline' && (
        <div className="space-y-6">
          {claim.transcript && (
            <div className="bg-white rounded-2xl border border-gray-200 p-5 shadow-xs">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-xs font-bold text-gray-600 uppercase tracking-wider">
                  Recorded Customer Transcript ({claim.language})
                </h2>
                <button
                  type="button"
                  onClick={handlePlayTranscript}
                  disabled={isSynthesizing}
                  className="inline-flex items-center gap-1.5 px-3 py-1 bg-gray-50 border border-gray-300 rounded-lg text-xs font-medium text-gray-700 hover:bg-gray-100"
                >
                  {isSynthesizing ? (
                    <>
                      <Spinner size="sm" /> Synthesizing...
                    </>
                  ) : isPlayingAudio ? (
                    <>
                      <VolumeX className="w-3.5 h-3.5 text-red-600" /> Stop
                    </>
                  ) : (
                    <>
                      <Volume2 className="w-3.5 h-3.5 text-blue-600" /> Listen (Timbre TTS)
                    </>
                  )}
                </button>
              </div>
              <p className="text-sm text-gray-800 italic bg-gray-50 p-4 rounded-xl border border-gray-100">
                "{claim.transcript}"
              </p>
            </div>
          )}

          <div className="grid md:grid-cols-2 gap-6">
            {/* Activity Timeline */}
            <div className="bg-white rounded-2xl border border-gray-200 p-6 shadow-xs">
              <h2 className="font-bold text-gray-900 text-sm mb-4 flex items-center gap-2">
                <Clock className="w-4 h-4 text-blue-600" /> Claim Lifecycle Timeline
              </h2>
              <ol className="relative border-l-2 border-gray-200 ml-3 space-y-5">
                {timeline.map((evt, i) => (
                  <li key={i} className="ml-5">
                    <span className="absolute -left-[9px] w-4 h-4 rounded-full bg-blue-600 border-2 border-white" />
                    <time className="text-[11px] text-gray-400">
                      {new Date(evt.timestamp).toLocaleString()}
                    </time>
                    <h3 className="text-xs font-bold text-gray-900">{evt.title}</h3>
                    <p className="text-xs text-gray-600">{evt.description}</p>
                  </li>
                ))}
              </ol>
            </div>

            {/* Security & Provenance Audit Trail */}
            <div className="bg-white rounded-2xl border border-gray-200 p-6 shadow-xs">
              <h2 className="font-bold text-gray-900 text-sm mb-4 flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-600" /> Security &amp; Audit Logs
              </h2>
              <div className="space-y-2.5">
                {auditLogs.map((log) => (
                  <div
                    key={log.log_id}
                    className="bg-gray-50 rounded-xl p-3 border border-gray-100 text-xs"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-mono font-bold text-[10px] px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                        {log.action}
                      </span>
                      <span className="text-[10px] text-gray-400">
                        {new Date(log.timestamp).toLocaleString()}
                      </span>
                    </div>
                    <p className="text-gray-700">{log.details}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
