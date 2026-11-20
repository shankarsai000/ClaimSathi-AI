import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  Bike,
  Car,
  CheckCircle2,
  FileCheck,
  FileSearch,
  History,
  Image as ImageIcon,
  IndianRupee,
  Printer,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Upload,
  XCircle,
} from 'lucide-react'
import { api } from '../api'
import Spinner from '../components/Spinner'
import type { EvidenceVerificationReport, YoloDetectionBox } from '../types'

function DecisionBadge({ decision }: { decision: 'PASS' | 'REVIEW' | 'REJECT' }) {
  if (decision === 'PASS') {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
        <CheckCircle2 className="w-4 h-4 text-emerald-600" />
        PASS
      </span>
    )
  }
  if (decision === 'REVIEW') {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200">
        <AlertTriangle className="w-4 h-4 text-amber-600" />
        REVIEW
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-red-100 text-red-800 border border-red-200">
      <XCircle className="w-4 h-4 text-red-600" />
      REJECT
    </span>
  )
}

function formatCategoryLabel(cat?: string) {
  if (!cat) return 'Unknown'
  if (cat === 'two_wheeler') return 'Two-Wheeler (Bike)'
  if (cat === 'four_wheeler') return 'Four-Wheeler (Car)'
  return cat
}

function formatInr(amount: number) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount)
}

export default function EvidenceVerify() {
  const [claimedVehicleType, setClaimedVehicleType] = useState<'four_wheeler' | 'two_wheeler'>('four_wheeler')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [report, setReport] = useState<EvidenceVerificationReport | null>(null)
  const [history, setHistory] = useState<EvidenceVerificationReport[]>([])
  const [loadingHistory, setLoadingHistory] = useState(true)

  // Sprint 1.7: Reviewer Override & Official Claim Creation State
  const [reviewerNote, setReviewerNote] = useState('Verified physical vehicle image; approving provisional estimate.')
  const [overriding, setOverriding] = useState(false)
  const [vehicleRegistration, setVehicleRegistration] = useState('')
  const [policyNumber, setPolicyNumber] = useState('')
  const [creatingClaim, setCreatingClaim] = useState(false)
  const [claimActionMessage, setClaimActionMessage] = useState('')

  const loadHistory = async () => {
    setLoadingHistory(true)
    try {
      const res = await api.getEvidenceHistoryV1(25)
      setHistory(res.verifications || [])
    } catch (e: any) {
      console.error('Failed to fetch verification history:', e)
    } finally {
      setLoadingHistory(false)
    }
  }

  useEffect(() => {
    loadHistory()
  }, [])

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    }
  }, [previewUrl])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null
    setError('')
    setClaimActionMessage('')
    setSelectedFile(file)
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
    }
    if (file) {
      setPreviewUrl(URL.createObjectURL(file))
    }
  }

  const handleVerifyAndEstimate = async () => {
    if (!selectedFile) {
      setError('Please select a vehicle image file first.')
      return
    }
    setSubmitting(true)
    setError('')
    setClaimActionMessage('')
    try {
      const res = await api.verifyEvidenceV1(selectedFile, claimedVehicleType)
      setReport(res)
      await loadHistory()
    } catch (e: any) {
      setError(e.message || 'Verification failed.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleSelectHistoryItem = async (id: string) => {
    try {
      setError('')
      setClaimActionMessage('')
      const detail = await api.getEvidenceVerificationByIdV1(id)
      setReport(detail)
      setSelectedFile(null)
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl)
        setPreviewUrl(null)
      }
    } catch (e: any) {
      setError(e.message || 'Could not load verification details.')
    }
  }

  const handleOverride = async (newDecision: 'PASS' | 'REJECT') => {
    if (!report) return
    setOverriding(true)
    setError('')
    setClaimActionMessage('')
    try {
      const res = await api.overrideEvidenceDecision(report.id, newDecision, reviewerNote)
      setReport(res)
      await loadHistory()
    } catch (e: any) {
      setError(e.message || 'Failed to update decision override.')
    } finally {
      setOverriding(false)
    }
  }

  const handleCreateClaim = async () => {
    if (!report) return
    setCreatingClaim(true)
    setError('')
    setClaimActionMessage('')
    try {
      const res = await api.createClaimFromEvidence(report.id, {
        vehicle_registration: vehicleRegistration,
        policy_number: policyNumber,
        incident_description: `Automated AI damage assessment submission for ${report.filename}.`,
      })
      setReport(res)
      setClaimActionMessage('Official claim generated and registered in Customer Claims Vault!')
      await loadHistory()
    } catch (e: any) {
      setError(e.message || 'Failed to create official claim.')
    } finally {
      setCreatingClaim(false)
    }
  }

  const s1 = report?.stage_results?.stage1_integrity
  const s2 = report?.stage_results?.stage2_metadata
  const s3a = report?.stage_results?.stage3a_vehicle
  const s3b = report?.stage_results?.stage3b_damage
  const cost = report?.cost_estimate || report?.stage_results?.cost_estimate

  const claimedCat = report?.claimed_vehicle_type || report?.stage_results?.claimed_vehicle_type || claimedVehicleType
  const detectedCat =
    report?.detected_vehicle_category ||
    report?.stage_results?.detected_vehicle_category ||
    'unknown'
  const isMismatch =
    Boolean(report?.vehicle_category_mismatch) ||
    Boolean(report?.stage_results?.vehicle_category_mismatch) ||
    Boolean(report?.reasons?.some((r) => r.includes('VEHICLE_CATEGORY_MISMATCH')))

  const linkedClaim = report?.linked_claim || report?.stage_results?.linked_claim
  const imgWidth = s1?.width || 0
  const imgHeight = s1?.height || 0
  const vehicleBoxes: YoloDetectionBox[] = s3a?.detections || []
  const damageBoxes: YoloDetectionBox[] = s3b?.detections || []

  return (
    <div className="space-y-6">
      {/* Executive Printable Assessment Report Banner (visible only during window.print()) */}
      {report && (
        <div className="hidden print-only mb-6 pb-4 border-b-2 border-gray-800">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-black text-gray-900 tracking-tight">ClaimSathi AI</h1>
              <p className="text-xs text-gray-600 font-semibold">
                Motor Insurance Claim Intake &amp; Evidence Intelligence Assessment Report
              </p>
            </div>
            <div className="text-right text-xs">
              <div className="font-bold text-gray-900">VERIFICATION DOSSIER</div>
              <div className="text-gray-500 font-mono text-[10px]">ID: {report.id}</div>
              <div className="text-gray-500 text-[10px]">{new Date(report.created_at).toLocaleString()}</div>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="no-print flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <ShieldCheck className="w-6 h-6 text-brand-600" />
            Evidence &amp; Instant Estimate
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Local 5-Stage Fraud-Risk Screening (Four-Wheeler CarDD &amp; Two-Wheeler Bike YOLOv8s + EfficientNetV2-S) &amp; INR Repair Estimator
          </p>
        </div>
        <button
          type="button"
          onClick={loadHistory}
          className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-white border border-gray-200 text-gray-700 text-xs font-semibold hover:bg-gray-50 transition-colors self-start"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh History
        </button>
      </div>

      {error && (
        <div className="no-print flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 text-sm">
          <ShieldAlert className="w-5 h-5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {claimActionMessage && (
        <div className="no-print flex items-center gap-2 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl p-4 text-sm font-semibold">
          <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
          <span>{claimActionMessage}</span>
        </div>
      )}

      {/* Top Grid: Upload & Preview + 5-Stage Verdict */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* Card 1: Image Upload & Preview */}
        <div className="no-print bg-white rounded-2xl border border-gray-200 p-5 shadow-xs space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
              <Upload className="w-4 h-4 text-brand-600" />
              1. Select Vehicle Type &amp; Upload Evidence
            </h2>
            <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-gray-100 text-gray-600">
              JPEG / PNG / WEBP
            </span>
          </div>

          {/* Claimed Vehicle Type Toggle */}
          <div className="space-y-1.5">
            <label className="block text-xs font-bold text-gray-700">
              Claimed Policy Vehicle Category
            </label>
            <div className="grid grid-cols-2 gap-2.5">
              <button
                type="button"
                onClick={() => setClaimedVehicleType('four_wheeler')}
                className={`flex items-center justify-center gap-2 px-3.5 py-2.5 rounded-xl border text-xs font-bold transition-all ${
                  claimedVehicleType === 'four_wheeler'
                    ? 'bg-brand-50 border-brand-600 text-brand-800 shadow-xs'
                    : 'bg-gray-50 border-gray-200 text-gray-600 hover:bg-gray-100'
                }`}
              >
                <Car className="w-4 h-4" />
                Four-Wheeler (Car)
              </button>
              <button
                type="button"
                onClick={() => setClaimedVehicleType('two_wheeler')}
                className={`flex items-center justify-center gap-2 px-3.5 py-2.5 rounded-xl border text-xs font-bold transition-all ${
                  claimedVehicleType === 'two_wheeler'
                    ? 'bg-brand-50 border-brand-600 text-brand-800 shadow-xs'
                    : 'bg-gray-50 border-gray-200 text-gray-600 hover:bg-gray-100'
                }`}
              >
                <Bike className="w-4 h-4" />
                Two-Wheeler (Bike)
              </button>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center">
            <label className="flex-1 cursor-pointer">
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
                onChange={handleFileChange}
                className="block w-full text-xs text-gray-600 file:mr-3 file:py-2 file:px-3 file:rounded-xl file:border-0 file:text-xs file:font-bold file:bg-brand-50 file:text-brand-700 hover:file:bg-brand-100 cursor-pointer border border-gray-200 rounded-xl p-1"
              />
            </label>
            <button
              type="button"
              disabled={!selectedFile || submitting}
              onClick={handleVerifyAndEstimate}
              className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-brand-600 text-white text-xs font-bold hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-xs shrink-0"
            >
              {submitting ? (
                <>
                  <Spinner size="sm" /> Screening...
                </>
              ) : (
                <>
                  <FileSearch className="w-4 h-4" /> Verify &amp; Estimate
                </>
              )}
            </button>
          </div>

          {/* Image Preview + Bounding-Box Overlays */}
          <div className="bg-gray-50 border border-dashed border-gray-300 rounded-xl min-h-[240px] flex items-center justify-center overflow-hidden p-2">
            {previewUrl ? (
              <div className="relative inline-block max-w-full">
                <img
                  src={previewUrl}
                  alt={selectedFile?.name || 'Uploaded evidence preview'}
                  className="max-h-72 w-auto rounded-lg object-contain block"
                />
                {report &&
                  report.filename === selectedFile?.name &&
                  imgWidth > 0 &&
                  imgHeight > 0 && (
                    <>
                      {vehicleBoxes.map((b, idx) => {
                        const [x1, y1, x2, y2] = b.bbox
                        return (
                          <div
                            key={`veh-${idx}`}
                            style={{
                              left: `${(x1 / imgWidth) * 100}%`,
                              top: `${(y1 / imgHeight) * 100}%`,
                              width: `${((x2 - x1) / imgWidth) * 100}%`,
                              height: `${((y2 - y1) / imgHeight) * 100}%`,
                            }}
                            className="absolute border-2 border-blue-500 bg-blue-500/10 pointer-events-none rounded-xs"
                          >
                            <span className="absolute -top-5 left-0 bg-blue-600 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-xs whitespace-nowrap">
                              {b.class_name} {(b.confidence * 100).toFixed(0)}%
                            </span>
                          </div>
                        )
                      })}
                      {damageBoxes.map((b, idx) => {
                        const [x1, y1, x2, y2] = b.bbox
                        return (
                          <div
                            key={`dmg-${idx}`}
                            style={{
                              left: `${(x1 / imgWidth) * 100}%`,
                              top: `${(y1 / imgHeight) * 100}%`,
                              width: `${((x2 - x1) / imgWidth) * 100}%`,
                              height: `${((y2 - y1) / imgHeight) * 100}%`,
                            }}
                            className="absolute border-2 border-red-500 bg-red-500/15 pointer-events-none rounded-xs"
                          >
                            <span className="absolute -top-5 left-0 bg-red-600 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-xs whitespace-nowrap">
                              {b.class_name} {(b.confidence * 100).toFixed(0)}%
                            </span>
                          </div>
                        )
                      })}
                    </>
                  )}
              </div>
            ) : (
              <div className="text-center text-gray-400 space-y-2 py-8">
                <ImageIcon className="w-10 h-10 mx-auto text-gray-300" />
                <p className="text-xs">
                  Select a local image to preview bounding boxes and damage detections.
                </p>
              </div>
            )}
          </div>

          {/* Detected Damage Tags */}
          {report && (
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <span className="text-xs font-semibold text-gray-600">Detected Tags:</span>
              {s3a?.detected_classes?.map((cls) => (
                <span
                  key={`cls-${cls}`}
                  className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200"
                >
                  {cls === 'motorcycle' || cls === 'bicycle' ? (
                    <Bike className="w-3 h-3" />
                  ) : (
                    <Car className="w-3 h-3" />
                  )}{' '}
                  {cls}
                </span>
              ))}
              {damageBoxes.length > 0 ? (
                damageBoxes.map((d, i) => (
                  <span
                    key={`dtag-${i}`}
                    className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-50 text-red-700 border border-red-200"
                  >
                    {d.class_name} ({(d.confidence * 100).toFixed(0)}%)
                  </span>
                ))
              ) : (
                <span className="text-xs text-gray-400">No active damage boxes detected</span>
              )}
            </div>
          )}
        </div>

        {/* Card 2: 5-Stage Verification Verdict */}
        <div className="bg-white rounded-2xl border border-gray-200 p-5 shadow-xs space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-brand-600" />
              2. 5-Stage Verification Verdict
            </h2>
            <div className="flex items-center gap-2">
              {report && (
                <button
                  type="button"
                  onClick={() => window.print()}
                  className="no-print inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-gray-200 bg-gray-50 hover:bg-gray-100 text-gray-700 text-xs font-semibold transition-colors"
                  title="Print or Save PDF Assessment Report"
                >
                  <Printer className="w-3.5 h-3.5 text-gray-600" />
                  Print / Save PDF
                </button>
              )}
              {report && <DecisionBadge decision={report.decision} />}
            </div>
          </div>

          {!report ? (
            <div className="py-16 text-center text-xs text-gray-400">
              Run &ldquo;Verify &amp; Estimate&rdquo; or choose a record from History to inspect Stage 1–5 risk signals.
            </div>
          ) : (
            <div className="space-y-4">
              {/* Feature A: Human-in-the-Loop Reviewer Override Bar */}
              {report.decision === 'REVIEW' && (
                <div className="no-print rounded-xl bg-amber-50/80 border border-amber-300 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs font-bold text-amber-900">
                      <AlertTriangle className="w-4 h-4 text-amber-600" />
                      Human Adjuster Review Required
                    </div>
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-amber-200 text-amber-900">
                      Manual Override
                    </span>
                  </div>
                  <p className="text-xs text-amber-800">
                    This upload triggered secondary fraud-risk screening checks. A certified claims reviewer may inspect the visual evidence and confirm or reject the estimate.
                  </p>
                  <div className="space-y-1.5">
                    <label className="block text-[11px] font-bold text-amber-900">
                      Reviewer Note
                    </label>
                    <input
                      type="text"
                      value={reviewerNote}
                      onChange={(e) => setReviewerNote(e.target.value)}
                      placeholder="Verified physical vehicle image; approving provisional estimate."
                      className="w-full text-xs px-3 py-2 rounded-lg border border-amber-300 bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-amber-500"
                    />
                  </div>
                  <div className="flex items-center gap-2.5 pt-1 flex-wrap">
                    <button
                      type="button"
                      disabled={overriding}
                      onClick={() => handleOverride('PASS')}
                      className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold disabled:opacity-50 transition-colors shadow-xs"
                    >
                      {overriding ? <Spinner size="sm" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                      Approve Override (Mark PASS)
                    </button>
                    <button
                      type="button"
                      disabled={overriding}
                      onClick={() => handleOverride('REJECT')}
                      className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-bold disabled:opacity-50 transition-colors shadow-xs"
                    >
                      {overriding ? <Spinner size="sm" /> : <XCircle className="w-3.5 h-3.5" />}
                      Reject Override (Mark REJECT)
                    </button>
                  </div>
                </div>
              )}

              {/* Vehicle Category Mismatch Red Alert Banner */}
              {isMismatch && (
                <div className="flex items-start gap-2.5 bg-red-50 border border-red-300 text-red-800 rounded-xl p-3.5 text-xs">
                  <XCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
                  <div className="space-y-0.5">
                    <div className="font-extrabold text-red-900">
                      Vehicle Category Mismatch — Upload Rejected
                    </div>
                    <p>
                      You selected <strong>{formatCategoryLabel(claimedCat)}</strong>, but the AI vision pipeline detected a{' '}
                      <strong>{formatCategoryLabel(detectedCat)}</strong> in the uploaded photo. Claim estimate has been blocked (₹0).
                    </p>
                  </div>
                </div>
              )}

              {/* Claimed vs Detected Vehicle Category Row */}
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-xl bg-blue-50/60 border border-blue-200">
                  <div className="text-[11px] font-semibold text-blue-700">Claimed Vehicle Type</div>
                  <div className="text-sm font-bold text-blue-950 mt-0.5">
                    {formatCategoryLabel(claimedCat)}
                  </div>
                </div>
                <div
                  className={`p-3 rounded-xl border ${
                    isMismatch
                      ? 'bg-red-50 border-red-300 text-red-900'
                      : 'bg-emerald-50/60 border-emerald-200 text-emerald-950'
                  }`}
                >
                  <div
                    className={`text-[11px] font-semibold ${
                      isMismatch ? 'text-red-700' : 'text-emerald-700'
                    }`}
                  >
                    Detected Vehicle Type
                  </div>
                  <div className="text-sm font-bold mt-0.5">
                    {formatCategoryLabel(detectedCat)}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <div className="p-3 rounded-xl bg-gray-50 border border-gray-200">
                  <div className="text-[11px] font-semibold text-gray-500">Spoof Risk</div>
                  <div className="text-lg font-bold text-gray-900 mt-0.5">
                    {(report.spoof_risk * 100).toFixed(2)}%
                  </div>
                </div>
                <div className="p-3 rounded-xl bg-gray-50 border border-gray-200">
                  <div className="text-[11px] font-semibold text-gray-500">Predicted Class</div>
                  <div className="text-sm font-bold text-gray-900 mt-1 break-all">
                    {report.predicted_spoof_class}
                  </div>
                </div>
                <div className="p-3 rounded-xl bg-gray-50 border border-gray-200">
                  <div className="text-[11px] font-semibold text-gray-500">Vehicle Detected</div>
                  <div className="text-lg font-bold text-gray-900 mt-0.5">
                    {report.vehicle_detected ? 'Yes' : 'No'}
                  </div>
                </div>
                <div className="p-3 rounded-xl bg-gray-50 border border-gray-200">
                  <div className="text-[11px] font-semibold text-gray-500">Damages Found</div>
                  <div className="text-lg font-bold text-gray-900 mt-0.5">{report.damage_count}</div>
                </div>
                <div className="p-3 rounded-xl bg-gray-50 border border-gray-200">
                  <div className="text-[11px] font-semibold text-gray-500">EXIF / Metadata</div>
                  <div className="text-xs font-bold text-gray-900 mt-1">
                    {s2
                      ? s2.editing_software_detected
                        ? `Editor: ${s2.software_tag}`
                        : s2.has_exif
                          ? s2.camera_make_model || 'EXIF Present'
                          : 'No EXIF (Mild 0.15)'
                      : 'N/A (Stage 1 Rejected)'}
                  </div>
                </div>
                <div className="p-3 rounded-xl bg-gray-50 border border-gray-200">
                  <div className="text-[11px] font-semibold text-gray-500">Inference Time</div>
                  <div className="text-lg font-bold text-gray-900 mt-0.5">
                    {report.processing_time_ms.toFixed(0)} ms
                  </div>
                </div>
              </div>

              <div className="rounded-xl bg-gray-50 border border-gray-200 p-3.5 space-y-1.5">
                <div className="text-xs font-bold text-gray-700">Verdict &amp; Risk Reasons</div>
                <ul className="list-disc list-inside text-xs text-gray-700 space-y-1">
                  {report.reasons.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
                <div className="pt-1 text-[11px] text-gray-400 font-mono truncate">
                  SHA-256: {report.sha256}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Card 3: Itemized Repair Estimate Card (Track A) */}
      <div className="bg-white rounded-2xl border border-gray-200 p-5 shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
            <IndianRupee className="w-4 h-4 text-brand-600" />
            3. Itemized Repair Cost Estimate (INR)
          </h2>
          {cost && (
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`px-2.5 py-1 rounded-full text-xs font-bold border ${
                  cost.estimate_status === 'APPROVED_AUTO_ESTIMATE'
                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                    : cost.estimate_status === 'PROVISIONAL_PENDING_REVIEW'
                      ? 'bg-amber-50 text-amber-700 border-amber-200'
                      : 'bg-red-50 text-red-700 border-red-200'
                }`}
              >
                {cost.estimate_status}
              </span>
              <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-gray-100 text-gray-700 border border-gray-200">
                Overall Severity: {cost.overall_severity}
              </span>
            </div>
          )}
        </div>

        {!cost ? (
          <p className="text-xs text-gray-400 py-4">No estimate generated yet.</p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-gray-200 text-gray-500">
                    <th className="py-2 pr-3 font-semibold">Damage Type</th>
                    <th className="py-2 pr-3 font-semibold">Confidence</th>
                    <th className="py-2 pr-3 font-semibold">Area %</th>
                    <th className="py-2 pr-3 font-semibold">Severity</th>
                    <th className="py-2 pr-3 font-semibold">Base Part</th>
                    <th className="py-2 pr-3 font-semibold">Multiplier</th>
                    <th className="py-2 pr-3 font-semibold">Labor</th>
                    <th className="py-2 font-semibold text-right">Subtotal (INR)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {cost.line_items.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-4 text-center text-gray-400">
                        {report?.decision === 'REJECT'
                          ? isMismatch
                            ? 'Rejected due to Vehicle Category Mismatch — ₹0 claim estimate issued.'
                            : 'File rejected at Stage 1 — ₹0 claim estimate issued.'
                          : 'No damage instances detected for the claimed vehicle type.'}
                      </td>
                    </tr>
                  ) : (
                    cost.line_items.map((item, idx) => (
                      <tr key={idx} className="hover:bg-gray-50/70">
                        <td className="py-2.5 pr-3 font-semibold capitalize text-gray-900">
                          {item.damage_type.replace('_', ' ')}
                        </td>
                        <td className="py-2.5 pr-3 text-gray-600">
                          {(item.confidence * 100).toFixed(1)}%
                        </td>
                        <td className="py-2.5 pr-3 text-gray-600">
                          {(item.area_ratio * 100).toFixed(2)}%
                        </td>
                        <td className="py-2.5 pr-3">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${
                              item.severity === 'Severe'
                                ? 'bg-red-100 text-red-700'
                                : item.severity === 'Moderate'
                                  ? 'bg-amber-100 text-amber-700'
                                  : 'bg-blue-100 text-blue-700'
                            }`}
                          >
                            {item.severity}
                          </span>
                        </td>
                        <td className="py-2.5 pr-3 text-gray-700">{formatInr(item.base_part_inr)}</td>
                        <td className="py-2.5 pr-3 text-gray-700">
                          {item.Diagnostic_multiplier ?? item.multiplier}x
                        </td>
                        <td className="py-2.5 pr-3 text-gray-700">{formatInr(item.labor_inr)}</td>
                        <td className="py-2.5 font-bold text-gray-900 text-right">
                          {formatInr(item.subtotal_inr)}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-gray-200">
              <span className="text-sm font-bold text-gray-700">Total Estimated Claim Amount</span>
              <span className="text-2xl font-extrabold text-brand-700">
                {formatInr(cost.total_estimated_inr)}
              </span>
            </div>
          </>
        )}
      </div>

      {/* Feature B: One-Click Official Claim Creation or Linked Claim Confirmation */}
      {report && (report.decision === 'PASS' || report.decision === 'REVIEW') && (
        <>
          {linkedClaim ? (
            <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-5 shadow-xs space-y-3">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                  <h3 className="text-sm font-bold text-emerald-950">
                    Official Claim Created: <span className="font-mono text-brand-700">{linkedClaim.claim_id}</span>
                  </h3>
                </div>
                <Link
                  to="/dashboard"
                  className="no-print inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand-600 text-white text-xs font-bold hover:bg-brand-700 transition-colors shadow-xs"
                >
                  View in Customer Claims Vault &rarr;
                </Link>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1 text-xs">
                <div className="bg-white/90 p-2.5 rounded-lg border border-emerald-100">
                  <div className="text-gray-500 text-[11px]">Vehicle Registration</div>
                  <div className="font-bold text-gray-900 mt-0.5">{linkedClaim.vehicle_registration}</div>
                </div>
                <div className="bg-white/90 p-2.5 rounded-lg border border-emerald-100">
                  <div className="text-gray-500 text-[11px]">Policy Reference</div>
                  <div className="font-bold text-gray-900 mt-0.5">{linkedClaim.policy_number}</div>
                </div>
                <div className="bg-white/90 p-2.5 rounded-lg border border-emerald-100">
                  <div className="text-gray-500 text-[11px]">Claim Status</div>
                  <div className="font-bold text-emerald-700 mt-0.5">{linkedClaim.claim_status}</div>
                </div>
                <div className="bg-white/90 p-2.5 rounded-lg border border-emerald-100">
                  <div className="text-gray-500 text-[11px]">Total Estimate</div>
                  <div className="font-bold text-brand-700 mt-0.5">{formatInr(linkedClaim.total_estimated_inr)}</div>
                </div>
              </div>
            </div>
          ) : (
            <div className="no-print bg-white rounded-2xl border border-gray-200 p-5 shadow-xs space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-gray-900 flex items-center gap-2">
                  <FileCheck className="w-4 h-4 text-brand-600" />
                  Submit Official Insurance Claim from Verified Estimate
                </h3>
                <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full">
                  Ready for Submission
                </span>
              </div>
              <p className="text-xs text-gray-500">
                Bind this verified AI assessment and {formatInr(cost?.total_estimated_inr || 0)} estimate to an official claim case in your Customer Claims Vault.
              </p>
              <div className="grid sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-gray-700 mb-1">Vehicle Registration Number</label>
                  <input
                    type="text"
                    value={vehicleRegistration}
                    onChange={(e) => setVehicleRegistration(e.target.value)}
                    placeholder="KA-17-AB-4021"
                    className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 bg-gray-50 text-gray-900 focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-gray-700 mb-1">Insurance Policy Number</label>
                  <input
                    type="text"
                    value={policyNumber}
                    onChange={(e) => setPolicyNumber(e.target.value)}
                    placeholder="POL-CS-99201"
                    className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 bg-gray-50 text-gray-900 focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                </div>
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  disabled={creatingClaim}
                  onClick={handleCreateClaim}
                  className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-xs font-bold disabled:opacity-50 transition-colors shadow-xs"
                >
                  {creatingClaim ? <Spinner size="sm" /> : <FileCheck className="w-4 h-4" />}
                  Submit Official Claim from Estimate
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Card 4: Recent Verifications History */}
      <div className="no-print bg-white rounded-2xl border border-gray-200 p-5 shadow-xs space-y-4">
        <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
          <History className="w-4 h-4 text-brand-600" />
          4. Recent Verification Runs (SQLite Log)
        </h2>

        {loadingHistory ? (
          <div className="flex justify-center py-6">
            <Spinner size="md" />
          </div>
        ) : history.length === 0 ? (
          <p className="text-xs text-gray-400">No verification runs recorded yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-gray-200 text-gray-500">
                  <th className="py-2 pr-3 font-semibold">Filename</th>
                  <th className="py-2 pr-3 font-semibold">Claimed / Detected</th>
                  <th className="py-2 pr-3 font-semibold">Decision</th>
                  <th className="py-2 pr-3 font-semibold">Spoof Risk</th>
                  <th className="py-2 pr-3 font-semibold">Damages</th>
                  <th className="py-2 pr-3 font-semibold">Estimate (INR)</th>
                  <th className="py-2 font-semibold text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {history.map((item) => {
                  const estTotal = item.cost_estimate?.total_estimated_inr ?? 0
                  const cType = item.claimed_vehicle_type === 'two_wheeler' ? '2W Bike' : '4W Car'
                  const dType =
                    item.detected_vehicle_category === 'two_wheeler'
                      ? '2W Bike'
                      : item.detected_vehicle_category === 'four_wheeler'
                        ? '4W Car'
                        : 'Unknown'
                  return (
                    <tr key={item.id} className="hover:bg-gray-50">
                      <td className="py-2 pr-3 font-medium text-gray-900">{item.filename}</td>
                      <td className="py-2 pr-3 text-gray-700">
                        {cType} &rarr; {dType}
                      </td>
                      <td className="py-2 pr-3">
                        <DecisionBadge decision={item.decision} />
                      </td>
                      <td className="py-2 pr-3 text-gray-700">
                        {(item.spoof_risk * 100).toFixed(2)}%
                      </td>
                      <td className="py-2 pr-3 text-gray-700">{item.damage_count}</td>
                      <td className="py-2 pr-3 font-bold text-gray-900">{formatInr(estTotal)}</td>
                      <td className="py-2 text-right">
                        <button
                          type="button"
                          onClick={() => handleSelectHistoryItem(item.id)}
                          className="text-brand-600 hover:underline font-semibold"
                        >
                          Inspect
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
