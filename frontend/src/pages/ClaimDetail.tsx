import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api'
import { APP_LANGUAGES, useAppSettings, type AppLanguageCode } from '../i18n'
import type {
  ClaimRecord,
  TimelineEvent,
  EvidenceAssetRecord,
  ReportRecord,
  InsurerSubmissionResponse,
  MotorAdjusterPlaceholders,
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
  Building2,
  Fingerprint,
  RefreshCw,
  CheckCircle2,
  Upload,
  Video,
  Send,
  ShieldCheck,
  Save,
} from 'lucide-react'

const SECTION_TITLES: { key: string; num: string; title: string }[] = [
  { key: 'section_01_customer', num: '01', title: 'Customer Identification & Profile' },
  { key: 'section_02_policy', num: '02', title: 'Policy & Coverage Details' },
  { key: 'section_03_incident', num: '03', title: 'Incident Details & Summary' },
  { key: 'section_04_statement', num: '04', title: 'Detailed Chronological Incident Statement' },
  { key: 'section_05_evidence_inventory', num: '05', title: 'Evidence Inventory & Screening Summary' },
  { key: 'section_06_validation_review', num: '06', title: 'Validation & Completeness Review' },
  { key: 'section_07_supporting_documents', num: '07', title: 'Supporting Documents & Cryptographic Hashes' },
  { key: 'section_08_preparation_summary', num: '08', title: 'Claim Preparation Summary & Next Steps' },
  { key: 'section_09_declaration', num: '09', title: 'Customer Confirmation & Regulatory Declaration' },
]

export default function ClaimDetail() {
  const { id } = useParams<{ id: string }>()
  const { preferredReportLanguage, setPreferredReportLanguage, t } = useAppSettings()
  const [claim, setClaim] = useState<ClaimRecord | null>(null)
  const [timeline, setTimeline] = useState<TimelineEvent[]>([])
  const [evidence, setEvidence] = useState<EvidenceAssetRecord[]>([])
  const [reports, setReports] = useState<ReportRecord[]>([])
  const [submissions, setSubmissions] = useState<InsurerSubmissionResponse[]>([])

  const [activeTab, setActiveTab] = useState<'dossier' | 'evidence' | 'gateway' | 'adjuster' | 'timeline'>('dossier')
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState('')
  const [adjusterSavedMsg, setAdjusterSavedMsg] = useState('')
  const [adjusterForm, setAdjusterForm] = useState<MotorAdjusterPlaceholders>({
    insurer_policy_master: { active_addons: [] },
    external_registry_checks: {
      vahan_status: 'pending_integration',
      sarathi_dl_status: 'pending_integration',
      iib_cross_claim_status: 'pending_integration',
      edar_sync_status: 'pending_integration',
    },
    surveyor_assessment: { damage_freshness_classification: 'pending' },
  })
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
      if (data.claim.insurer_adjuster_data) {
        setAdjusterForm(data.claim.insurer_adjuster_data)
      }
      setTimeline(data.timeline || [])
      setEvidence(data.evidence || [])
      setReports(data.reports || [])
      setSubmissions(data.insurer_submissions || [])

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

  const handleSaveAdjusterAssessment = async () => {
    if (!id) return
    setActionLoading(true)
    setError('')
    setAdjusterSavedMsg('')
    try {
      await api.updateAdjusterAssessment(id, adjusterForm)
      await api.generateReport(id)
      await loadClaimFull()
      setAdjusterSavedMsg('Group D insurer/surveyor assessment saved and 9-Section Dossier refreshed.')
    } catch (e: any) {
      setError(e.message || 'Failed to save adjuster assessment.')
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
            <ArrowLeft className="w-3.5 h-3.5" /> {t('claim_detail_back')} ({claim.customer_id})
          </Link>
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-2xl font-extrabold text-gray-900 font-mono">{claim.id}</h1>
            <StatusBadge status={claim.status} />
            <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-purple-50 text-purple-800 border border-purple-200">
              Dossier v{latestReport?.version || '1.0'}
            </span>
            <DemoBadge />
          </div>
          <p className="text-xs text-gray-500 mt-1">
            Policy: <strong className="text-gray-800">{claim.policy_reference}</strong> &bull; Insurer:{' '}
            <strong className="text-gray-800">{claim.insurer_name}</strong> &bull; Vehicle:{' '}
            <strong className="text-gray-800 capitalize">{claim.vehicle_type}</strong>
          </p>
        </div>

        {/* Download & Gateway Action Buttons (Multi-Language + English Insurer PDF) */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex items-center gap-1.5 bg-blue-50 border border-blue-200 rounded-xl px-3 py-2">
            <span className="text-xs font-bold text-blue-900">{t('report_lang_label')}</span>
            <select
              value={preferredReportLanguage}
              onChange={(e) => setPreferredReportLanguage(e.target.value as AppLanguageCode)}
              className="bg-transparent text-xs font-extrabold text-blue-800 focus:outline-none cursor-pointer"
            >
              {APP_LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.native} ({l.label})
                </option>
              ))}
            </select>
          </div>

          <a
            href={api.getReportLocalizedUrl(claim.id, preferredReportLanguage, false)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-emerald-600 text-white text-xs font-bold hover:bg-emerald-700 shadow-xs"
          >
            <Download className="w-4 h-4" />
            {t('download_preferred_lang_btn')} ({APP_LANGUAGES.find((l) => l.code === preferredReportLanguage)?.native})
          </a>

          <a
            href={api.getReportPdfUrl(claim.id)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-brand-600 text-white text-xs font-bold hover:bg-brand-700 shadow-xs"
          >
            <Download className="w-4 h-4" /> {t('download_english_pdf_btn')}
          </a>
          <a
            href={api.getReportJsonUrl(claim.id)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl bg-white border border-gray-300 text-gray-800 text-xs font-semibold hover:bg-gray-50"
          >
            <FileCode className="w-4 h-4 text-blue-600" /> {t('download_json_btn')}
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
            id: 'adjuster',
            label: 'Insurer & Surveyor Portal (Adjuster)',
            icon: ShieldCheck,
          },
          {
            id: 'timeline',
            label: 'Transcript & Activity Timeline',
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
                    key === 'section_05_evidence_inventory' || key === 'section_07_supporting_documents'
                      ? 'md:col-span-2'
                      : ''
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
                    key={ev.evidence_id}
                    className={`rounded-2xl border p-4 flex gap-4 ${
                      isFlagged ? 'bg-amber-50/60 border-amber-300' : 'bg-gray-50/60 border-gray-200'
                    }`}
                  >
                    {ev.media_type === 'image' ? (
                      <img
                        src={api.getEvidenceFileUrl(claim.id, ev.evidence_id)}
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
                          <div className="text-[11px] text-gray-600">
                            {scr.provenance_result} &rarr; <strong>{scr.provenance_system_response}</strong>
                          </div>
                          <div className="text-[10px] font-mono text-gray-500 bg-white p-2 rounded-lg border border-gray-200 space-y-0.5">
                            <div className="truncate">SHA-256: {scr.sha256_hash}</div>
                            {scr.perceptual_hash && <div>64-bit pHash: {scr.perceptual_hash}</div>}
                            <div>
                              Duplicate Status: <strong>{scr.duplicate_status}</strong>
                              {scr.matched_claim_reference && ` (Matched ${scr.matched_claim_reference})`}
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
          TAB 3B: INSURER & SURVEYOR ADJUSTER PORTAL (GROUP D ONLY)
         ===================================================================== */}
      {activeTab === 'adjuster' && (
        <div className="bg-white rounded-3xl border border-gray-200 p-6 shadow-xs space-y-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-gray-100 pb-4">
            <div>
              <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-brand-600" />
                Group D — Insurer Policy Master, External Registry &amp; Surveyor Portal
              </h2>
              <p className="text-xs text-gray-500 mt-0.5">
                Adjuster-managed and insurer-side fields (never requested on Customer Portal). Updates feed directly into Layer 1 Canonical JSON &amp; PDF Dossier.
              </p>
            </div>
            <button
              type="button"
              onClick={handleSaveAdjusterAssessment}
              disabled={actionLoading}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-brand-600 text-white text-xs font-bold hover:bg-brand-700 shadow-xs disabled:opacity-50"
            >
              <Save className="w-4 h-4" />
              {actionLoading ? 'Saving...' : 'Save Assessment & Refresh Dossier'}
            </button>
          </div>

          {adjusterSavedMsg && (
            <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl px-4 py-2.5 text-xs font-semibold">
              {adjusterSavedMsg}
            </div>
          )}

          {/* 1. Insurer Policy Master */}
          <div className="rounded-2xl border border-gray-200 p-4 space-y-3 text-xs">
            <h3 className="text-xs font-bold uppercase tracking-wider text-gray-500">
              1. Insurer Policy Master
            </h3>
            <div className="grid sm:grid-cols-3 gap-3">
              <div>
                <label className="block font-semibold text-gray-600 mb-1">Insurer Claim Ref No</label>
                <input
                  type="text"
                  value={adjusterForm.insurer_policy_master.claim_reference_number || ''}
                  onChange={(e) =>
                    setAdjusterForm((p) => ({
                      ...p,
                      insurer_policy_master: { ...p.insurer_policy_master, claim_reference_number: e.target.value },
                    }))
                  }
                  className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                />
              </div>
              <div>
                <label className="block font-semibold text-gray-600 mb-1">Policy Start Date</label>
                <input
                  type="date"
                  value={adjusterForm.insurer_policy_master.policy_start_date || ''}
                  onChange={(e) =>
                    setAdjusterForm((p) => ({
                      ...p,
                      insurer_policy_master: { ...p.insurer_policy_master, policy_start_date: e.target.value },
                    }))
                  }
                  className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                />
              </div>
              <div>
                <label className="block font-semibold text-gray-600 mb-1">Policy End Date</label>
                <input
                  type="date"
                  value={adjusterForm.insurer_policy_master.policy_end_date || ''}
                  onChange={(e) =>
                    setAdjusterForm((p) => ({
                      ...p,
                      insurer_policy_master: { ...p.insurer_policy_master, policy_end_date: e.target.value },
                    }))
                  }
                  className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                />
              </div>
              <div>
                <label className="block font-semibold text-gray-600 mb-1">IDV (INR)</label>
                <input
                  type="number"
                  value={adjusterForm.insurer_policy_master.idv_inr ?? ''}
                  onChange={(e) =>
                    setAdjusterForm((p) => ({
                      ...p,
                      insurer_policy_master: { ...p.insurer_policy_master, idv_inr: e.target.value ? Number(e.target.value) : null },
                    }))
                  }
                  className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                />
              </div>
              <div>
                <label className="block font-semibold text-gray-600 mb-1">NCB (%)</label>
                <input
                  type="number"
                  value={adjusterForm.insurer_policy_master.ncb_percent ?? ''}
                  onChange={(e) =>
                    setAdjusterForm((p) => ({
                      ...p,
                      insurer_policy_master: { ...p.insurer_policy_master, ncb_percent: e.target.value ? Number(e.target.value) : null },
                    }))
                  }
                  className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                />
              </div>
              <div>
                <label className="block font-semibold text-gray-600 mb-1">Coverage Type</label>
                <input
                  type="text"
                  value={adjusterForm.insurer_policy_master.coverage_type || ''}
                  onChange={(e) =>
                    setAdjusterForm((p) => ({
                      ...p,
                      insurer_policy_master: { ...p.insurer_policy_master, coverage_type: e.target.value },
                    }))
                  }
                  placeholder="Comprehensive / Package"
                  className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                />
              </div>
              <div>
                <label className="block font-semibold text-gray-600 mb-1">Compulsory Excess (INR)</label>
                <input
                  type="number"
                  value={adjusterForm.insurer_policy_master.compulsory_excess_inr ?? ''}
                  onChange={(e) =>
                    setAdjusterForm((p) => ({
                      ...p,
                      insurer_policy_master: { ...p.insurer_policy_master, compulsory_excess_inr: e.target.value ? Number(e.target.value) : null },
                    }))
                  }
                  className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                />
              </div>
              <div>
                <label className="block font-semibold text-gray-600 mb-1">Voluntary Excess (INR)</label>
                <input
                  type="number"
                  value={adjusterForm.insurer_policy_master.voluntary_excess_inr ?? ''}
                  onChange={(e) =>
                    setAdjusterForm((p) => ({
                      ...p,
                      insurer_policy_master: { ...p.insurer_policy_master, voluntary_excess_inr: e.target.value ? Number(e.target.value) : null },
                    }))
                  }
                  className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                />
              </div>
              <div>
                <label className="block font-semibold text-gray-600 mb-1">Hypothecation Financier</label>
                <input
                  type="text"
                  value={adjusterForm.insurer_policy_master.hypothecation_financier || ''}
                  onChange={(e) =>
                    setAdjusterForm((p) => ({
                      ...p,
                      insurer_policy_master: { ...p.insurer_policy_master, hypothecation_financier: e.target.value },
                    }))
                  }
                  className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                />
              </div>
            </div>
            <div>
              <span className="block font-semibold text-gray-600 mb-1.5">Active Policy Add-ons</span>
              <div className="flex flex-wrap gap-2">
                {['Zero-Dep', 'Engine Protect', 'RTI', 'Consumables', 'PA'].map((addon) => {
                  const active = (adjusterForm.insurer_policy_master.active_addons || []).includes(addon)
                  return (
                    <button
                      key={addon}
                      type="button"
                      onClick={() =>
                        setAdjusterForm((p) => ({
                          ...p,
                          insurer_policy_master: {
                            ...p.insurer_policy_master,
                            active_addons: active
                              ? p.insurer_policy_master.active_addons.filter((a) => a !== addon)
                              : [...(p.insurer_policy_master.active_addons || []), addon],
                          },
                        }))
                      }
                      className={`px-3 py-1 rounded-full text-xs font-bold border ${
                        active ? 'bg-brand-600 text-white border-brand-600' : 'bg-gray-50 text-gray-700 border-gray-200'
                      }`}
                    >
                      {addon}
                    </button>
                  )
                })}
              </div>
            </div>
          </div>

          {/* 2. External Registry Checks (Read-Only Pending Integration Placeholders) */}
          <div className="rounded-2xl border border-gray-200 p-4 space-y-3 text-xs">
            <h3 className="text-xs font-bold uppercase tracking-wider text-gray-500">
              2. External Registry Verification Hooks (Read-Only Integration Placeholders)
            </h3>
            <div className="grid sm:grid-cols-2 gap-3">
              <div>
                <label className="block font-semibold text-gray-600 mb-1">Engine Number</label>
                <input
                  type="text"
                  value={adjusterForm.external_registry_checks.engine_number || ''}
                  onChange={(e) =>
                    setAdjusterForm((p) => ({
                      ...p,
                      external_registry_checks: { ...p.external_registry_checks, engine_number: e.target.value },
                    }))
                  }
                  placeholder="Pending VAHAN sync / manual entry"
                  className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs font-mono"
                />
              </div>
              <div>
                <label className="block font-semibold text-gray-600 mb-1">Chassis / VIN Number</label>
                <input
                  type="text"
                  value={adjusterForm.external_registry_checks.chassis_vin_number || ''}
                  onChange={(e) =>
                    setAdjusterForm((p) => ({
                      ...p,
                      external_registry_checks: { ...p.external_registry_checks, chassis_vin_number: e.target.value },
                    }))
                  }
                  placeholder="Pending VAHAN sync / manual entry"
                  className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs font-mono"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              {[
                { label: 'VAHAN RC Status', val: adjusterForm.external_registry_checks.vahan_status },
                { label: 'SARATHI DL Status', val: adjusterForm.external_registry_checks.sarathi_dl_status },
                { label: 'IIB Cross-Claim', val: adjusterForm.external_registry_checks.iib_cross_claim_status },
                { label: 'eDAR Sync', val: adjusterForm.external_registry_checks.edar_sync_status },
              ].map((item) => (
                <div key={item.label} className="bg-slate-50 border border-slate-200 rounded-xl p-2.5">
                  <div className="text-[10px] font-bold text-slate-500 uppercase">{item.label}</div>
                  <div className="mt-1 inline-block px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 font-mono text-[11px] font-bold">
                    {item.val || 'pending_integration'}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 3. Surveyor Assessment */}
          <div className="rounded-2xl border border-gray-200 p-4 space-y-3 text-xs">
            <h3 className="text-xs font-bold uppercase tracking-wider text-gray-500">
              3. Licensed Surveyor Assessment
            </h3>
            <div className="grid sm:grid-cols-4 gap-3">
              <div>
                <label className="block font-semibold text-gray-600 mb-1">Surveyor Name</label>
                <input
                  type="text"
                  value={adjusterForm.surveyor_assessment.surveyor_name || ''}
                  onChange={(e) =>
                    setAdjusterForm((p) => ({
                      ...p,
                      surveyor_assessment: { ...p.surveyor_assessment, surveyor_name: e.target.value },
                    }))
                  }
                  className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                />
              </div>
              <div>
                <label className="block font-semibold text-gray-600 mb-1">IRDAI License No</label>
                <input
                  type="text"
                  value={adjusterForm.surveyor_assessment.surveyor_irdai_license_no || ''}
                  onChange={(e) =>
                    setAdjusterForm((p) => ({
                      ...p,
                      surveyor_assessment: { ...p.surveyor_assessment, surveyor_irdai_license_no: e.target.value },
                    }))
                  }
                  className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs font-mono"
                />
              </div>
              <div>
                <label className="block font-semibold text-gray-600 mb-1">Odometer Reading (km)</label>
                <input
                  type="number"
                  value={adjusterForm.surveyor_assessment.odometer_reading_km ?? ''}
                  onChange={(e) =>
                    setAdjusterForm((p) => ({
                      ...p,
                      surveyor_assessment: { ...p.surveyor_assessment, odometer_reading_km: e.target.value ? Number(e.target.value) : null },
                    }))
                  }
                  className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                />
              </div>
              <div>
                <label className="block font-semibold text-gray-600 mb-1">Damage Freshness</label>
                <select
                  value={adjusterForm.surveyor_assessment.damage_freshness_classification || 'pending'}
                  onChange={(e) =>
                    setAdjusterForm((p) => ({
                      ...p,
                      surveyor_assessment: { ...p.surveyor_assessment, damage_freshness_classification: e.target.value as any },
                    }))
                  }
                  className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs bg-white"
                >
                  <option value="pending">Pending</option>
                  <option value="fresh">Fresh</option>
                  <option value="pre_existing">Pre-existing</option>
                  <option value="mixed">Mixed</option>
                </select>
              </div>
              <div>
                <label className="block font-semibold text-gray-600 mb-1">IMT GR-9 Depreciation (INR)</label>
                <input
                  type="number"
                  value={adjusterForm.surveyor_assessment.imt_gr9_depreciation_inr ?? ''}
                  onChange={(e) =>
                    setAdjusterForm((p) => ({
                      ...p,
                      surveyor_assessment: { ...p.surveyor_assessment, imt_gr9_depreciation_inr: e.target.value ? Number(e.target.value) : null },
                    }))
                  }
                  className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                />
              </div>
              <div>
                <label className="block font-semibold text-gray-600 mb-1">Salvage Value (INR)</label>
                <input
                  type="number"
                  value={adjusterForm.surveyor_assessment.salvage_value_inr ?? ''}
                  onChange={(e) =>
                    setAdjusterForm((p) => ({
                      ...p,
                      surveyor_assessment: { ...p.surveyor_assessment, salvage_value_inr: e.target.value ? Number(e.target.value) : null },
                    }))
                  }
                  className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                />
              </div>
              <div>
                <label className="block font-semibold text-gray-600 mb-1">Net Assessed Payable (INR)</label>
                <input
                  type="number"
                  value={adjusterForm.surveyor_assessment.net_assessed_payable_inr ?? ''}
                  onChange={(e) =>
                    setAdjusterForm((p) => ({
                      ...p,
                      surveyor_assessment: { ...p.surveyor_assessment, net_assessed_payable_inr: e.target.value ? Number(e.target.value) : null },
                    }))
                  }
                  className="w-full rounded-xl border border-gray-300 px-3 py-1.5 text-xs"
                />
              </div>
              <div className="flex items-end pb-1">
                <label className="flex items-center gap-2 font-semibold text-gray-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={Boolean(adjusterForm.surveyor_assessment.constructive_total_loss)}
                    onChange={(e) =>
                      setAdjusterForm((p) => ({
                        ...p,
                        surveyor_assessment: { ...p.surveyor_assessment, constructive_total_loss: e.target.checked },
                      }))
                    }
                    className="rounded text-brand-600"
                  />
                  Constructive Total Loss (CTL)
                </label>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          TAB 4: TRANSCRIPT & ACTIVITY TIMELINE
         ===================================================================== */}
      {activeTab === 'timeline' && (
        <div className="space-y-6">
          {claim.transcript && (
            <div className="bg-white rounded-2xl border border-gray-200 p-5 shadow-xs">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-xs font-bold text-gray-600 uppercase tracking-wider">
                  Recorded Customer Transcript
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
        </div>
      )}
    </div>
  )
}
