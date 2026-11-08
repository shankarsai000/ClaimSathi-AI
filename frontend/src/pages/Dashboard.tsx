import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, getStoredUser, clearStoredAuth } from '../api'
import type { VaultSummaryResponse, UserConsentInput } from '../types'
import Spinner from '../components/Spinner'
import StatusBadge from '../components/StatusBadge'
import DemoBadge from '../components/DemoBadge'
import {
  PlusCircle,
  FileText,
  AlertCircle,
  UserCheck,
  ShieldCheck,
  KeyRound,
  UserPlus,
  Download,
  FileCode,
  History,
  CheckCircle2,
  LogOut,
  RefreshCw,
} from 'lucide-react'

export default function Dashboard() {
  const [vault, setVault] = useState<VaultSummaryResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [authTab, setAuthTab] = useState<'none' | 'login' | 'register'>('none')

  // Login form state
  const [loginIdentifier, setLoginIdentifier] = useState('rahul@example.com')
  const [loginPassword, setLoginPassword] = useState('Rahul@2026')
  const [loginOtp, setLoginOtp] = useState('123456')
  const [useOtp, setUseOtp] = useState(false)
  const [authLoading, setAuthLoading] = useState(false)

  // Register form state
  const [regName, setRegName] = useState('')
  const [regEmail, setRegEmail] = useState('')
  const [regPhone, setRegPhone] = useState('')
  const [regPassword, setRegPassword] = useState('')
  const [regLang, setRegLang] = useState('kn-IN')

  const loadVault = async () => {
    setLoading(true)
    setError('')
    try {
      const current = getStoredUser()
      const data = await api.getVault(current?.customer_id)
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

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setAuthLoading(true)
    setError('')
    try {
      await api.login({
        identifier: loginIdentifier,
        password: useOtp ? undefined : loginPassword,
        otp: useOtp ? loginOtp : undefined,
      })
      setAuthTab('none')
      await loadVault()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setAuthLoading(false)
    }
  }

  const handleQuickRahulLogin = async () => {
    setAuthLoading(true)
    setError('')
    try {
      await api.login({ identifier: 'USR-100001', demo_quick_login: true })
      setAuthTab('none')
      await loadVault()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setAuthLoading(false)
    }
  }

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    setAuthLoading(true)
    setError('')
    try {
      await api.register({
        name: regName,
        email: regEmail,
        phone: regPhone,
        password: regPassword || 'ClaimSathi@2026',
        preferred_language: regLang,
        consents: {
          ai_assistance_accepted: true,
          media_storage_accepted: true,
          fraud_screening_accepted: true,
          privacy_policy_accepted: true,
        },
      })
      setAuthTab('none')
      setRegName('')
      setRegEmail('')
      setRegPhone('')
      setRegPassword('')
      await loadVault()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setAuthLoading(false)
    }
  }

  const handleToggleConsent = async (key: keyof UserConsentInput) => {
    if (!vault?.user) return
    const updated: UserConsentInput = {
      ...vault.user.consents,
      [key]: !vault.user.consents[key],
    }
    try {
      await api.updateConsent(updated)
      setVault({
        ...vault,
        user: { ...vault.user, consents: updated },
      })
    } catch (err: any) {
      setError(err.message)
    }
  }

  return (
    <div className="space-y-6">
      {/* ── TOP HEADER ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-gray-900">Customer Claims Vault</h1>
            <DemoBadge />
          </div>
          <p className="text-sm text-gray-500 mt-0.5">
            Step 1 &amp; Step 9: Persistent customer account, consent management, archived claim dossiers &amp; audit trail
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={() => setAuthTab(authTab === 'login' ? 'none' : 'login')}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-gray-300 bg-white text-gray-700 text-xs font-semibold hover:bg-gray-50 transition-colors"
          >
            <KeyRound className="w-3.5 h-3.5 text-blue-600" />
            Switch / Login Account
          </button>
          <button
            type="button"
            onClick={() => setAuthTab(authTab === 'register' ? 'none' : 'register')}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-gray-300 bg-white text-gray-700 text-xs font-semibold hover:bg-gray-50 transition-colors"
          >
            <UserPlus className="w-3.5 h-3.5 text-emerald-600" />
            Register New Customer
          </button>
          <Link
            to="/claims/new"
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-brand-600 text-white text-xs font-bold hover:bg-brand-700 transition-colors shadow-xs"
          >
            <PlusCircle className="w-4 h-4" /> Start New Claim Wizard
          </Link>
        </div>
      </div>

      {/* ── LOGIN / REGISTER DRAWER (PHASE 1) ── */}
      {authTab === 'login' && (
        <div className="bg-white rounded-2xl border border-blue-200 p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-base font-bold text-gray-900">Customer Account Login (Phase 1)</h2>
              <p className="text-xs text-gray-500">
                Sign in with Email, Phone, or Customer ID (e.g. <code>USR-100001</code> / <code>rahul@example.com</code>)
              </p>
            </div>
            <button
              type="button"
              onClick={handleQuickRahulLogin}
              disabled={authLoading}
              className="px-3.5 py-1.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-bold hover:bg-emerald-100"
            >
              ⚡ 1-Click Login as Rahul (USR-100001)
            </button>
          </div>

          <form onSubmit={handleLogin} className="grid sm:grid-cols-3 gap-4 items-end">
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">
                Email / Phone / Customer ID
              </label>
              <input
                type="text"
                required
                value={loginIdentifier}
                onChange={(e) => setLoginIdentifier(e.target.value)}
                className="w-full rounded-xl border border-gray-300 px-3 py-2 text-xs focus:ring-2 focus:ring-blue-500 focus:outline-none"
                placeholder="rahul@example.com or USR-100001"
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-semibold text-gray-600">
                  {useOtp ? 'Demo OTP (use 123456)' : 'Password'}
                </label>
                <button
                  type="button"
                  onClick={() => setUseOtp(!useOtp)}
                  className="text-[11px] text-blue-600 font-semibold hover:underline"
                >
                  {useOtp ? 'Use Password instead' : 'Use OTP (123456)'}
                </button>
              </div>
              {useOtp ? (
                <input
                  type="text"
                  required
                  value={loginOtp}
                  onChange={(e) => setLoginOtp(e.target.value)}
                  className="w-full rounded-xl border border-gray-300 px-3 py-2 text-xs focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  placeholder="123456"
                />
              ) : (
                <input
                  type="password"
                  required
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  className="w-full rounded-xl border border-gray-300 px-3 py-2 text-xs focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  placeholder="Rahul@2026"
                />
              )}
            </div>

            <div className="flex items-center gap-2">
              <button
                type="submit"
                disabled={authLoading}
                className="px-5 py-2 rounded-xl bg-blue-600 text-white text-xs font-bold hover:bg-blue-700 disabled:opacity-50"
              >
                {authLoading ? 'Signing in...' : 'Sign In'}
              </button>
              <button
                type="button"
                onClick={() => setAuthTab('none')}
                className="px-3 py-2 rounded-xl border border-gray-200 text-xs text-gray-600 hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {authTab === 'register' && (
        <div className="bg-white rounded-2xl border border-emerald-200 p-6 shadow-sm">
          <h2 className="text-base font-bold text-gray-900 mb-1">
            Register New Customer Account (Generates Unique USR-XXXXXX ID)
          </h2>
          <p className="text-xs text-gray-500 mb-4">
            Creates a new customer profile in SQLite with full consent records and an isolated Claims Vault.
          </p>

          <form onSubmit={handleRegister} className="grid sm:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">Full Name</label>
              <input
                type="text"
                required
                value={regName}
                onChange={(e) => setRegName(e.target.value)}
                placeholder="Priya Nair"
                className="w-full rounded-xl border border-gray-300 px-3 py-2 text-xs"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">Email</label>
              <input
                type="email"
                required
                value={regEmail}
                onChange={(e) => setRegEmail(e.target.value)}
                placeholder="priya@example.com"
                className="w-full rounded-xl border border-gray-300 px-3 py-2 text-xs"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">Phone Number</label>
              <input
                type="text"
                required
                value={regPhone}
                onChange={(e) => setRegPhone(e.target.value)}
                placeholder="+91-9845012345"
                className="w-full rounded-xl border border-gray-300 px-3 py-2 text-xs"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">Preferred Language</label>
              <select
                value={regLang}
                onChange={(e) => setRegLang(e.target.value)}
                className="w-full rounded-xl border border-gray-300 px-3 py-2 text-xs bg-white"
              >
                <option value="kn-IN">Kannada (kn-IN)</option>
                <option value="te-IN">Telugu (te-IN)</option>
                <option value="hi-IN">Hindi (hi-IN)</option>
                <option value="ta-IN">Tamil (ta-IN)</option>
                <option value="en-IN">English (en-IN)</option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="submit"
                disabled={authLoading}
                className="px-4 py-2 rounded-xl bg-emerald-600 text-white text-xs font-bold hover:bg-emerald-700"
              >
                {authLoading ? 'Creating...' : 'Create Account'}
              </button>
              <button
                type="button"
                onClick={() => setAuthTab('none')}
                className="px-3 py-2 rounded-xl border border-gray-200 text-xs text-gray-600"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

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
                        {vault.user.email} &bull; {vault.user.phone} &bull; Preferred Language:{' '}
                        <strong className="text-gray-700">{vault.user.preferred_language}</strong>
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      clearStoredAuth()
                      setAuthTab('login')
                    }}
                    className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-red-600 font-medium"
                  >
                    <LogOut className="w-3.5 h-3.5" /> Switch User
                  </button>
                </div>

                {/* Consent & Privacy Checkboxes */}
                <div className="mt-5 pt-4 border-t border-gray-100">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-gray-700 uppercase tracking-wider flex items-center gap-1.5">
                      <ShieldCheck className="w-4 h-4 text-emerald-600" />
                      Recorded Customer Consents &amp; Privacy Preferences
                    </span>
                    <span className="text-[11px] text-gray-400">Click any badge to update consent</span>
                  </div>
                  <div className="grid sm:grid-cols-2 md:grid-cols-4 gap-2">
                    {[
                      { key: 'ai_assistance_accepted', label: 'AI Voice & Text Intake' },
                      { key: 'media_storage_accepted', label: 'Evidence Media Vault' },
                      { key: 'fraud_screening_accepted', label: 'C2PA / pHash Screening' },
                      { key: 'privacy_policy_accepted', label: 'Privacy & Audit Policy' },
                    ].map(({ key, label }) => {
                      const active = vault.user.consents[key as keyof UserConsentInput]
                      return (
                        <button
                          key={key}
                          type="button"
                          onClick={() => handleToggleConsent(key as keyof UserConsentInput)}
                          className={`flex items-center gap-1.5 px-3 py-2 rounded-xl border text-left text-xs font-medium transition-all ${
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
                        </button>
                      )
                    })}
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
                      <p className="text-2xl font-bold text-brand-700 mt-0.5">{vault.total_claims}</p>
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
                        <th className="text-left px-4 py-3">Report Version</th>
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
                          <td className="px-4 py-3.5 text-gray-700 capitalize">
                            {c.vehicle_type}
                            {c.vehicle_registration && c.vehicle_registration !== 'Pending verification' && (
                              <span className="ml-1.5 text-xs text-gray-400 font-mono">
                                ({c.vehicle_registration})
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3.5 text-gray-700 text-xs">
                            <div className="font-medium text-gray-900">{c.incident_location}</div>
                            <div className="text-gray-400">{c.incident_date}</div>
                          </td>
                          <td className="px-4 py-3.5">
                            <StatusBadge status={c.status} />
                          </td>
                          <td className="px-4 py-3.5 text-xs text-gray-600 font-semibold">
                            v{c.report_version || '1.0'}
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
            {vault.recent_audit_logs && vault.recent_audit_logs.length > 0 && (
              <div className="bg-white rounded-2xl border border-gray-200 p-5 shadow-xs">
                <h3 className="font-bold text-gray-900 text-sm flex items-center gap-2 mb-3">
                  <History className="w-4 h-4 text-blue-600" />
                  Customer Vault Audit Trail (Real-Time Security &amp; Provenance Log)
                </h3>
                <div className="space-y-2 max-h-56 overflow-y-auto pr-2">
                  {vault.recent_audit_logs.map((log) => (
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
