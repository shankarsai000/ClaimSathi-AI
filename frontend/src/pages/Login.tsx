import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, getStoredUser } from '../api'
import { useAppSettings } from '../i18n'
import {
  Shield,
  Lock,
  KeyRound,
  UserPlus,
  AlertCircle,
  CheckCircle2,
  ArrowRight,
  Smartphone,
  Sparkles,
} from 'lucide-react'

// Demo accounts seeded into PostgreSQL / SQLite database (zero hardcoding, real DB users)
const DEMO_ACCOUNTS = [
  {
    name: 'Rahul Sharma',
    city: 'Bengaluru (Bike / Car)',
    id: 'rahul.sharma@claimsathi.in',
    pwd: 'Rahul@2026',
    policy: 'MOT-2026-KA-44210',
    color: 'border-blue-200 bg-blue-50/70 text-blue-900 hover:bg-blue-100',
  },
  {
    name: 'Sai Shankar Reddy',
    city: 'Hyderabad (Car)',
    id: 'saishankar.reddy@claimsathi.in',
    pwd: 'Shankar@2026',
    policy: 'MOT-2024-TS-98765',
    color: 'border-emerald-200 bg-emerald-50/70 text-emerald-900 hover:bg-emerald-100',
  },
  {
    name: 'Ananya Lakshmi Iyer',
    city: 'Chennai (Two-Wheeler)',
    id: 'ananya.iyer@claimsathi.in',
    pwd: 'Ananya@2026',
    policy: 'MOT-2026-TN-55120',
    color: 'border-amber-200 bg-amber-50/70 text-amber-900 hover:bg-amber-100',
  },
  {
    name: 'Vikramaditya Deshmukh',
    city: 'Pune (Car / SUV)',
    id: 'vikram.deshmukh@claimsathi.in',
    pwd: 'Vikram@2026',
    policy: 'MOT-2026-MH-33901',
    color: 'border-purple-200 bg-purple-50/70 text-purple-900 hover:bg-purple-100',
  },
]

export default function Login() {
  const navigate = useNavigate()
  const { t } = useAppSettings()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [authMethod, setAuthMethod] = useState<'password' | 'otp'>('password')

  // Login form state (zero hardcoded accounts)
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [otpCode, setOtpCode] = useState('')
  const [otpRequestedMessage, setOtpRequestedMessage] = useState('')

  // Registration form state
  const [regName, setRegName] = useState('')
  const [regEmail, setRegEmail] = useState('')
  const [regPhone, setRegPhone] = useState('')
  const [regPassword, setRegPassword] = useState('')
  const [regInsurer, setRegInsurer] = useState('Bharat General Insurance')
  const [consentData, setConsentData] = useState(true)
  const [consentScreening, setConsentScreening] = useState(true)
  const [consentRetention, setConsentRetention] = useState(true)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // If already logged in, go straight to the Customer Claims Vault
  useEffect(() => {
    if (getStoredUser()) {
      navigate('/dashboard', { replace: true })
    }
  }, [navigate])

  const handleRequestOtp = async () => {
    if (!identifier.trim()) {
      setError('Please enter your Email, Phone Number, or Customer ID first.')
      return
    }
    setError('')
    setLoading(true)
    try {
      const res = await api.requestOtp(identifier.trim())
      setOtpRequestedMessage(res.message)
      if (import.meta.env.DEV && res.demo_otp_code) {
        setOtpCode(res.demo_otp_code)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to request OTP.')
    } finally {
      setLoading(false)
    }
  }

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await api.login({
        identifier: identifier.trim(),
        password: authMethod === 'password' ? password : undefined,
        otp_code: authMethod === 'otp' ? otpCode.trim() : undefined,
      })
      navigate('/dashboard', { replace: true })
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please check your credentials.')
    } finally {
      setLoading(false)
    }
  }

  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!consentData || !consentScreening || !consentRetention) {
      setError('Please accept all required privacy and evidence screening consents to register.')
      return
    }
    setError('')
    setLoading(true)
    try {
      await api.register({
        name: regName.trim(),
        email: regEmail.trim(),
        phone: regPhone.trim(),
        password: regPassword,
        declared_insurer: regInsurer.trim() || 'Bharat General Insurance',
        consents: {
          data_processing_consent: consentData,
          evidence_screening_consent: consentScreening,
          retention_policy_acknowledged: consentRetention,
        },
      })
      navigate('/dashboard', { replace: true })
    } catch (err: any) {
      setError(err.message || 'Registration failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50 flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center mb-6">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-50 border border-blue-200 text-blue-700 text-[11px] font-bold mb-3 shadow-xs">
          <Shield className="w-3.5 h-3.5" />
          {t('login_badge')}
        </div>
        <div className="flex items-center justify-center gap-2.5 mb-2">
          <div className="w-11 h-11 rounded-2xl bg-brand-600 flex items-center justify-center text-white shadow-md">
            <Shield className="w-6 h-6" />
          </div>
          <span className="text-3xl font-extrabold text-brand-900 tracking-tight">
            ClaimSathi <span className="text-brand-500">AI</span>
          </span>
        </div>
        <p className="text-xs sm:text-sm text-gray-600 font-medium">
          {t('login_subtitle')}
        </p>
      </div>

      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        {/* Quick Demo Test Account Selector (Development/Demo mode only) */}
        {mode === 'login' && import.meta.env.DEV && (
          <div className="mb-4 bg-white/95 backdrop-blur-md rounded-2xl border border-gray-200/90 p-3.5 shadow-sm">
            <div className="flex items-center gap-1.5 text-[11px] font-bold text-gray-700 mb-2">
              <Sparkles className="w-3.5 h-3.5 text-amber-500" />
              <span>{t('login_quick_demo_title')}</span>
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              {DEMO_ACCOUNTS.map((acc) => (
                <button
                  key={acc.id}
                  type="button"
                  onClick={() => {
                    setIdentifier(acc.id)
                    setPassword(acc.pwd)
                    setAuthMethod('password')
                    setError('')
                  }}
                  className={`text-left p-2 rounded-xl border text-[11px] transition-all flex flex-col justify-between ${acc.color}`}
                  title={`Click to fill: ${acc.id} (${acc.pwd})`}
                >
                  <span className="font-bold truncate">{acc.name}</span>
                  <span className="text-[10px] opacity-75 truncate">{acc.city}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="bg-white py-7 px-6 shadow-xl rounded-3xl border border-gray-200 sm:px-8">
          {/* Mode Switcher Tabs */}
          <div className="grid grid-cols-2 gap-2 bg-gray-100 p-1.5 rounded-2xl mb-6">
            <button
              type="button"
              onClick={() => {
                setMode('login')
                setError('')
              }}
              className={`flex items-center justify-center gap-1.5 py-2.5 rounded-xl text-xs font-bold transition-all ${
                mode === 'login'
                  ? 'bg-white text-brand-700 shadow-xs'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              <KeyRound className="w-3.5 h-3.5" /> {t('login_tab_signin')}
            </button>
            <button
              type="button"
              onClick={() => {
                setMode('register')
                setError('')
              }}
              className={`flex items-center justify-center gap-1.5 py-2.5 rounded-xl text-xs font-bold transition-all ${
                mode === 'register'
                  ? 'bg-white text-brand-700 shadow-xs'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              <UserPlus className="w-3.5 h-3.5" /> {t('login_tab_register')}
            </button>
          </div>

          {error && (
            <div className="mb-5 flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-2xl p-3.5 text-xs">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {mode === 'login' ? (
            <form onSubmit={handleLoginSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-gray-700 mb-1.5">
                  {t('login_id_label')}
                </label>
                <input
                  type="text"
                  required
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  placeholder={t('login_id_placeholder')}
                  className="w-full rounded-xl border border-gray-300 px-3.5 py-2.5 text-xs focus:ring-2 focus:ring-brand-500 focus:outline-none"
                />
              </div>

              {/* Password vs OTP Toggle */}
              <div className="flex items-center justify-between pt-1">
                <label className="text-xs font-bold text-gray-700">
                  {authMethod === 'password' ? t('login_pwd_label') : t('login_otp_label')}
                </label>
                <button
                  type="button"
                  onClick={() => {
                    setAuthMethod(authMethod === 'password' ? 'otp' : 'password')
                    setError('')
                    setOtpRequestedMessage('')
                  }}
                  className="text-xs font-semibold text-brand-600 hover:underline inline-flex items-center gap-1"
                >
                  {authMethod === 'password' ? (
                    <>
                      <Smartphone className="w-3.5 h-3.5" /> {t('login_otp_toggle_to_otp')}
                    </>
                  ) : (
                    <>
                      <Lock className="w-3.5 h-3.5" /> {t('login_otp_toggle_to_pwd')}
                    </>
                  )}
                </button>
              </div>

              {authMethod === 'password' ? (
                <div>
                  <input
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder={t('login_pwd_placeholder')}
                    className="w-full rounded-xl border border-gray-300 px-3.5 py-2.5 text-xs focus:ring-2 focus:ring-brand-500 focus:outline-none"
                  />
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="flex gap-2">
                    <input
                      type="text"
                      required
                      value={otpCode}
                      onChange={(e) => setOtpCode(e.target.value)}
                      placeholder={t('login_otp_placeholder')}
                      className="flex-1 rounded-xl border border-gray-300 px-3.5 py-2.5 text-xs focus:ring-2 focus:ring-brand-500 focus:outline-none font-mono"
                    />
                    <button
                      type="button"
                      onClick={handleRequestOtp}
                      disabled={loading}
                      className="px-3.5 py-2.5 rounded-xl bg-blue-50 border border-blue-200 text-blue-700 text-xs font-bold hover:bg-blue-100 shrink-0"
                    >
                      {t('login_otp_send_btn')}
                    </button>
                  </div>
                  {otpRequestedMessage && (
                    <p className="text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl px-3 py-1.5">
                      {otpRequestedMessage}
                    </p>
                  )}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full mt-2 inline-flex items-center justify-center gap-2 py-3 px-4 rounded-2xl bg-brand-600 text-white font-bold text-xs shadow-md hover:bg-brand-700 transition-colors disabled:opacity-50"
              >
                {loading ? 'Authenticating...' : t('login_submit_btn')}
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>
          ) : (
            <form onSubmit={handleRegisterSubmit} className="space-y-3.5">
              <div>
                <label className="block text-xs font-bold text-gray-700 mb-1">Full Name</label>
                <input
                  type="text"
                  required
                  value={regName}
                  onChange={(e) => setRegName(e.target.value)}
                  placeholder="e.g. Karthik Subramanian"
                  className="w-full rounded-xl border border-gray-300 px-3.5 py-2 text-xs focus:ring-2 focus:ring-brand-500 focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-gray-700 mb-1">Email Address</label>
                  <input
                    type="email"
                    required
                    value={regEmail}
                    onChange={(e) => setRegEmail(e.target.value)}
                    placeholder="karthik@example.com"
                    className="w-full rounded-xl border border-gray-300 px-3.5 py-2 text-xs focus:ring-2 focus:ring-brand-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-gray-700 mb-1">Phone Number</label>
                  <input
                    type="text"
                    required
                    value={regPhone}
                    onChange={(e) => setRegPhone(e.target.value)}
                    placeholder="+91-9845012345"
                    className="w-full rounded-xl border border-gray-300 px-3.5 py-2 text-xs focus:ring-2 focus:ring-brand-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-gray-700 mb-1">Password</label>
                  <input
                    type="password"
                    required
                    minLength={4}
                    value={regPassword}
                    onChange={(e) => setRegPassword(e.target.value)}
                    placeholder="Create password"
                    className="w-full rounded-xl border border-gray-300 px-3.5 py-2 text-xs focus:ring-2 focus:ring-brand-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-gray-700 mb-1">Declared Insurer</label>
                  <input
                    type="text"
                    value={regInsurer}
                    onChange={(e) => setRegInsurer(e.target.value)}
                    placeholder="Bharat General Insurance"
                    className="w-full rounded-xl border border-gray-300 px-3.5 py-2 text-xs focus:ring-2 focus:ring-brand-500 focus:outline-none"
                  />
                </div>
              </div>

              {/* Mandatory Consents (Step 1 of PDF) */}
              <div className="bg-gray-50 rounded-2xl p-3.5 border border-gray-200 space-y-2 text-[11px] text-gray-700">
                <div className="font-bold text-gray-900 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                  Customer Privacy &amp; Screening Consents
                </div>
                <label className="flex items-start gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={consentData}
                    onChange={(e) => setConsentData(e.target.checked)}
                    className="mt-0.5 rounded text-brand-600"
                  />
                  <span>I consent to multilingual AI voice/text processing for claim preparation.</span>
                </label>
                <label className="flex items-start gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={consentScreening}
                    onChange={(e) => setConsentScreening(e.target.checked)}
                    className="mt-0.5 rounded text-brand-600"
                  />
                  <span>I consent to C2PA, SynthID, SHA-256 &amp; perceptual hash (pHash) evidence screening.</span>
                </label>
                <label className="flex items-start gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={consentRetention}
                    onChange={(e) => setConsentRetention(e.target.checked)}
                    className="mt-0.5 rounded text-brand-600"
                  />
                  <span>I acknowledge the Customer Claims Vault retention and privacy policy.</span>
                </label>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full inline-flex items-center justify-center gap-2 py-3 px-4 rounded-2xl bg-emerald-600 text-white font-bold text-xs shadow-md hover:bg-emerald-700 transition-colors disabled:opacity-50"
              >
                {loading ? 'Creating Customer Account...' : 'Register & Generate Customer ID'}
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}

