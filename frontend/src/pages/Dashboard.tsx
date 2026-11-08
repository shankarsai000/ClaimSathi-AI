import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, getStoredUser, clearStoredAuth } from '../api'
import { useAppSettings } from '../i18n'
import type { VaultSummaryResponse } from '../types'
import Spinner from '../components/Spinner'
import StatusBadge from '../components/StatusBadge'
import DemoBadge from '../components/DemoBadge'
import {
  PlusCircle,
  FileText,
  AlertCircle,
  ShieldCheck,
  Download,
  FileCode,
  History,
  CheckCircle2,
  LogOut,
  RefreshCw,
} from 'lucide-react'

export default function Dashboard() {
  const navigate = useNavigate()
  const { t, setIsSettingsOpen } = useAppSettings()
  const [vault, setVault] = useState<VaultSummaryResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadVault = async () => {
    setLoading(true)
    setError('')
    try {
      const current = getStoredUser()
      if (!current) {
        navigate('/login', { replace: true })
        return
      }
      const data = await api.getVault(current.customer_id)
      setVault(data)
    } catch (e: any) {
      setError(e.message || 'Failed to load Customer Claims Vault.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadVault()
    const onAuthChange = () => loadVault()
    window.addEventListener('claimsathi-auth-change', onAuthChange)
    return () => window.removeEventListener('claimsathi-auth-change', onAuthChange)
  }, [])

  return (
    <div className="space-y-6">
      {/* ── TOP HEADER ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-gray-900">{t('vault_title')}</h1>
            <DemoBadge />
          </div>
          <p className="text-sm text-gray-500 mt-0.5">
            {t('vault_subtitle')}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={() => setIsSettingsOpen(true)}
            className="inline-flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl bg-white border border-gray-200 text-gray-700 text-xs font-bold hover:bg-gray-50 transition-colors"
          >
            ⚙️ {t('nav_settings')}
          </button>
          <Link
            to="/claims/new"
            className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-brand-600 text-white text-xs font-bold hover:bg-brand-700 transition-colors shadow-xs"
          >
            <PlusCircle className="w-4 h-4" /> {t('start_new_claim')}
          </Link>
        </div>
      </div>

      {/* ── ERROR ALERT ── */}
      {error && (
        <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 text-sm">
          <AlertCircle className="w-5 h-5 shrink-0" /> {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-20">
          <Spinner size="lg" />
        </div>
      ) : (
        vault && (
          <>
            {/* ── CUSTOMER PROFILE & CONSENT SUMMARY CARD (STEP 1) ── */}
            <div className="grid lg:grid-cols-3 gap-5">
              {/* Customer Identity Card */}
              <div className="lg:col-span-2 bg-white rounded-2xl border border-gray-200 p-5 shadow-xs flex flex-col justify-between">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-center gap-3.5">
                    <div className="w-12 h-12 rounded-2xl bg-brand-50 border border-brand-200 flex items-center justify-center text-brand-700 font-bold text-lg">
                      {vault.user.name.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h2 className="text-lg font-bold text-gray-900">{vault.user.name}</h2>
                        <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          {vault.user.customer_id}
                        </span>
                      </div>
                      <p className="text-xs text-gray-500 mt-0.5">
                        {vault.user.email} &bull; {vault.user.phone} &bull; Declared Insurer:{' '}
                        <strong className="text-gray-700">{vault.user.declared_insurer}</strong>
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      clearStoredAuth()
                      navigate('/login', { replace: true })
                    }}
                    className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-red-600 font-medium"
                  >
                    <LogOut className="w-3.5 h-3.5" /> Switch Account
                  </button>
                </div>

                {/* Consent & Privacy Badges */}
                <div className="mt-5 pt-4 border-t border-gray-100">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-gray-700 uppercase tracking-wider flex items-center gap-1.5">
                      <ShieldCheck className="w-4 h-4 text-emerald-600" />
                      Recorded Customer Consents &amp; Privacy Preferences
                    </span>
                  </div>
                  <div className="grid sm:grid-cols-3 gap-2">
                    {[
                      {
                        key: 'data_processing_consent',
                        label: 'AI Voice & Text Processing',
                        active: vault.user.consents?.data_processing_consent ?? true,
                      },
                      {
                        key: 'evidence_screening_consent',
                        label: 'C2PA / SynthID / pHash Screening',
                        active: vault.user.consents?.evidence_screening_consent ?? true,
                      },
                      {
                        key: 'retention_policy_acknowledged',
                        label: 'Vault Retention & Audit Policy',
                        active: vault.user.consents?.retention_policy_acknowledged ?? true,
                      },
                    ].map(({ key, label, active }) => (
                      <div
                        key={key}
                        className={`flex items-center gap-1.5 px-3 py-2 rounded-xl border text-left text-xs font-medium ${
                          active
                            ? 'bg-emerald-50/70 border-emerald-200 text-emerald-900'
                            : 'bg-gray-50 border-gray-200 text-gray-400'
                        }`}
                      >
                        <CheckCircle2
                          className={`w-3.5 h-3.5 shrink-0 ${
                            active ? 'text-emerald-600' : 'text-gray-300'
                          }`}
                        />
                        <span className="truncate">{label}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Vault Stats */}
              <div className="bg-white rounded-2xl border border-gray-200 p-5 shadow-xs flex flex-col justify-between">
                <div>
                  <span className="text-xs font-bold uppercase tracking-wider text-gray-400">
                    Customer Vault Metrics
                  </span>
                  <div className="grid grid-cols-2 gap-3 mt-3">
                    <div className="bg-gray-50 rounded-xl p-3 border border-gray-100">
                      <p className="text-[11px] text-gray-500">Total Claims in Vault</p>
                      <p className="text-2xl font-bold text-brand-700 mt-0.5">{vault.total_cases}</p>
                    </div>
                    <div className="bg-gray-50 rounded-xl p-3 border border-gray-100">
                      <p className="text-[11px] text-gray-500">Customer ID</p>
                      <p className="text-sm font-bold text-emerald-700 mt-1.5">{vault.user.customer_id}</p>
                    </div>
                  </div>
                </div>
                <div className="mt-4 pt-3 border-t border-gray-100 flex items-center justify-between text-xs text-gray-500">
                  <span>Cross-Claim pHash Index: Active</span>
                  <button
                    type="button"
                    onClick={loadVault}
                    className="inline-flex items-center gap-1 text-blue-600 font-semibold hover:underline"
                  >
                    <RefreshCw className="w-3 h-3" /> Refresh
                  </button>
                </div>
              </div>
            </div>

            {/* ── STORED CLAIMS TABLE (STEP 9 VAULT) ── */}
            <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden shadow-xs">
              <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-gray-900 text-sm">
                    Stored Claims &amp; Dossiers for {vault.user.name} ({vault.user.customer_id})
                  </h3>
                  <p className="text-xs text-gray-500">
                    Click any Claim ID to view the 9-Section Professional Dossier, Screened Evidence Inventory, or submit to the Mock Insurer Gateway
                  </p>
                </div>
              </div>

              {vault.claims.length === 0 ? (
                <div className="text-center py-14">
                  <FileText className="w-10 h-10 text-gray-300 mx-auto mb-2" />
                  <p className="text-sm text-gray-500 mb-4">No claims recorded in this customer vault yet.</p>
                  <Link
                    to="/claims/new"
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-brand-600 text-white text-xs font-bold hover:bg-brand-700"
                  >
                    <PlusCircle className="w-4 h-4" /> Start Your First Claim
                  </Link>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                      <tr>
                        <th className="text-left px-5 py-3">Claim ID</th>
                        <th className="text-left px-4 py-3">Policy Number</th>
                        <th className="text-left px-4 py-3">Vehicle</th>
                        <th className="text-left px-4 py-3">Incident Location &amp; Date</th>
                        <th className="text-left px-4 py-3">Status</th>
                        <th className="text-left px-4 py-3">Insurer</th>
                        <th className="text-right px-5 py-3">Dossier &amp; Exports</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {vault.claims.map((c) => (
                        <tr key={c.id} className="hover:bg-gray-50/80 transition-colors">
                          <td className="px-5 py-3.5">
                            <Link
                              to={`/claims/${c.id}`}
                              className="text-brand-600 font-bold hover:underline"
                            >
                              {c.id}
                            </Link>
                          </td>
                          <td className="px-4 py-3.5 font-mono text-xs text-gray-700">
                            {c.policy_reference}
                          </td>
                          <td className="px-4 py-3.5 text-gray-700 capitalize">{c.vehicle_type}</td>
                          <td className="px-4 py-3.5 text-gray-700 text-xs">
                            <div className="font-medium text-gray-900">{c.incident_location}</div>
                            <div className="text-gray-400">{c.incident_date}</div>
                          </td>
                          <td className="px-4 py-3.5">
                            <StatusBadge status={c.status} />
                          </td>
                          <td className="px-4 py-3.5 text-xs text-gray-600 font-medium">
                            {c.insurer_name}
                          </td>
                          <td className="px-5 py-3.5 text-right">
                            <div className="inline-flex items-center gap-2">
                              <Link
                                to={`/claims/${c.id}`}
                                className="px-2.5 py-1 rounded-lg bg-brand-50 text-brand-700 border border-brand-200 text-xs font-semibold hover:bg-brand-100"
                              >
                                Open Dossier
                              </Link>
                              <a
                                href={api.getReportPdfUrl(c.id)}
                                target="_blank"
                                rel="noreferrer"
                                title="Download Binary PDF Report"
                                className="p-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-100"
                              >
                                <Download className="w-3.5 h-3.5" />
                              </a>
                              <a
                                href={api.getReportJsonUrl(c.id)}
                                target="_blank"
                                rel="noreferrer"
                                title="Download Layer 1 Canonical Schema JSON"
                                className="p-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-100"
                              >
                                <FileCode className="w-3.5 h-3.5" />
                              </a>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* ── AUDIT TRAIL LOGS (PHASE 1 & 6) ── */}
            {vault.audit_logs && vault.audit_logs.length > 0 && (
              <div className="bg-white rounded-2xl border border-gray-200 p-5 shadow-xs">
                <h3 className="font-bold text-gray-900 text-sm flex items-center gap-2 mb-3">
                  <History className="w-4 h-4 text-blue-600" />
                  Customer Vault Audit Trail (Real-Time Security &amp; Provenance Log)
                </h3>
                <div className="space-y-2 max-h-56 overflow-y-auto pr-2">
                  {vault.audit_logs.map((log) => (
                    <div
                      key={log.log_id}
                      className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-xs bg-gray-50 rounded-xl px-3.5 py-2 border border-gray-100"
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-[11px] px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                          {log.action}
                        </span>
                        {log.claim_id && (
                          <Link
                            to={`/claims/${log.claim_id}`}
                            className="font-bold text-brand-600 hover:underline"
                          >
                            {log.claim_id}
                          </Link>
                        )}
                        <span className="text-gray-700">{log.details}</span>
                      </div>
                      <span className="text-[11px] text-gray-400 shrink-0">
                        {new Date(log.timestamp).toLocaleString()}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )
      )}
    </div>
  )
}
