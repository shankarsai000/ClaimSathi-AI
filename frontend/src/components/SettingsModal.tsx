import { useState, useEffect } from 'react'
import { X, Globe, User, ShieldCheck, Check, FileText, Mic } from 'lucide-react'
import { APP_LANGUAGES, useAppSettings, type AppLanguageCode } from '../i18n'
import { getStoredUser, setStoredAuth, getStoredToken } from '../api'
import type { UserProfile } from '../types'

export default function SettingsModal() {
  const {
    appLanguage,
    setAppLanguage,
    preferredReportLanguage,
    setPreferredReportLanguage,
    defaultVoiceLanguage,
    setDefaultVoiceLanguage,
    isSettingsOpen,
    setIsSettingsOpen,
    t,
  } = useAppSettings()

  const [activeTab, setActiveTab] = useState<'language' | 'profile'>('language')
  const [user, setUser] = useState<UserProfile | null>(getStoredUser())
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [insurer, setInsurer] = useState('')
  const [policyNumber, setPolicyNumber] = useState('')
  const [vehicleReg, setVehicleReg] = useState('')
  const [savedNotice, setSavedNotice] = useState(false)

  useEffect(() => {
    if (isSettingsOpen) {
      const u = getStoredUser()
      setUser(u)
      setName(u?.name || '')
      setPhone(u?.phone || '')
      setInsurer(u?.declared_insurer || 'Bharat General Insurance')
      setPolicyNumber(localStorage.getItem('claimsathi_user_policy') || 'CS-2026-000085')
      setVehicleReg(localStorage.getItem('claimsathi_user_vehicle_reg') || 'KA-17-EA-4590')
      setSavedNotice(false)
    }
  }, [isSettingsOpen])

  if (!isSettingsOpen) return null

  const handleSaveProfile = () => {
    if (user) {
      const updatedUser: UserProfile = {
        ...user,
        name: name.trim() || user.name,
        phone: phone.trim() || user.phone,
        declared_insurer: insurer.trim() || user.declared_insurer,
      }
      const token = getStoredToken() || ''
      setStoredAuth(token, updatedUser)
      setUser(updatedUser)
    }
    localStorage.setItem('claimsathi_user_policy', policyNumber.trim() || 'CS-2026-000085')
    localStorage.setItem('claimsathi_user_vehicle_reg', vehicleReg.trim() || 'KA-17-EA-4590')
    setSavedNotice(true)
    setTimeout(() => setSavedNotice(false), 2500)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4">
      <div className="bg-white rounded-3xl border border-gray-200 shadow-2xl max-w-2xl w-full overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 bg-gradient-to-r from-brand-900 to-brand-700 text-white">
          <div className="flex items-center gap-2.5">
            <Globe className="w-5 h-5 text-blue-200" />
            <h2 className="text-base font-bold">{t('settings_title')}</h2>
          </div>
          <button
            type="button"
            onClick={() => setIsSettingsOpen(false)}
            className="p-1.5 rounded-xl bg-white/10 hover:bg-white/20 text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 bg-gray-50 px-6 pt-3 gap-2">
          <button
            type="button"
            onClick={() => setActiveTab('language')}
            className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-t-2xl text-xs font-bold border-b-2 transition-colors ${
              activeTab === 'language'
                ? 'bg-white border-brand-600 text-brand-700'
                : 'border-transparent text-gray-500 hover:text-gray-800'
            }`}
          >
            <Globe className="w-4 h-4" />
            {t('settings_tab_lang')}
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('profile')}
            className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-t-2xl text-xs font-bold border-b-2 transition-colors ${
              activeTab === 'profile'
                ? 'bg-white border-brand-600 text-brand-700'
                : 'border-transparent text-gray-500 hover:text-gray-800'
            }`}
          >
            <User className="w-4 h-4" />
            {t('settings_tab_profile')}
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-5 max-h-[75vh] overflow-y-auto">
          {activeTab === 'language' ? (
            <>
              {/* 1. App Display Language */}
              <div className="space-y-2.5">
                <label className="block text-sm font-bold text-gray-900">
                  {t('choose_app_lang')}
                </label>
                <p className="text-xs text-gray-500 leading-relaxed">
                  {t('choose_app_lang_desc')}
                </p>
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5 pt-1">
                  {APP_LANGUAGES.map((lang) => {
                    const active = appLanguage === lang.code
                    return (
                      <button
                        key={lang.code}
                        type="button"
                        onClick={() => setAppLanguage(lang.code)}
                        className={`flex flex-col items-center justify-center p-3 rounded-2xl border text-center transition-all ${
                          active
                            ? 'bg-brand-600 text-white border-brand-600 shadow-sm'
                            : 'bg-gray-50 text-gray-800 border-gray-200 hover:bg-blue-50 hover:border-blue-200'
                        }`}
                      >
                        <span className="text-sm font-bold">{lang.native}</span>
                        <span
                          className={`text-[11px] mt-0.5 ${
                            active ? 'text-blue-100' : 'text-gray-500'
                          }`}
                        >
                          {lang.label}
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* 2. Preferred Report Download Language */}
              <div className="bg-blue-50/60 border border-blue-200 rounded-2xl p-4 space-y-2">
                <div className="flex items-center gap-2 text-xs font-bold text-blue-900">
                  <FileText className="w-4 h-4 text-blue-600" />
                  <span>{t('choose_report_lang')}</span>
                </div>
                <p className="text-[11px] text-blue-800">
                  When generating your 9-Section Claim Dossier, you can download both the official English insurer copy and a translated copy in your preferred language:
                </p>
                <div className="flex flex-wrap gap-2 pt-1">
                  {APP_LANGUAGES.map((lang) => (
                    <button
                      key={lang.code}
                      type="button"
                      onClick={() => setPreferredReportLanguage(lang.code as AppLanguageCode)}
                      className={`px-3 py-1.5 rounded-xl text-xs font-bold border transition-all ${
                        preferredReportLanguage === lang.code
                          ? 'bg-blue-700 text-white border-blue-700'
                          : 'bg-white text-gray-700 border-gray-200 hover:bg-blue-100'
                      }`}
                    >
                      {lang.native} ({lang.label})
                    </button>
                  ))}
                </div>
              </div>

              {/* 3. Default Voice Recognition Mode */}
              <div className="bg-gray-50 border border-gray-200 rounded-2xl p-4 space-y-2">
                <div className="flex items-center gap-2 text-xs font-bold text-gray-900">
                  <Mic className="w-4 h-4 text-brand-600" />
                  <span>{t('choose_voice_mode')}</span>
                </div>
                <select
                  value={defaultVoiceLanguage}
                  onChange={(e) => setDefaultVoiceLanguage(e.target.value)}
                  className="w-full rounded-xl border border-gray-300 bg-white px-3 py-2 text-xs font-semibold text-gray-800"
                >
                  <option value="indic-auto">
                    🌐 Auto-Detect All 10+ Languages (Locks onto 1st spoken language)
                  </option>
                  <option value="kn-IN">🇮🇳 Kannada / ಕನ್ನಡ (kn-IN)</option>
                  <option value="te-IN">🇮🇳 Telugu / తెలుగు (te-IN)</option>
                  <option value="hi-IN">🇮🇳 Hindi / हिन्दी (hi-IN)</option>
                  <option value="ta-IN">🇮🇳 Tamil / தமிழ் (ta-IN)</option>
                  <option value="mr-IN">🇮🇳 Marathi / मराठी (mr-IN)</option>
                  <option value="en-IN">🇮🇳 Indian English (en-IN)</option>
                </select>
              </div>
            </>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between bg-emerald-50 border border-emerald-200 rounded-2xl p-3.5">
                <div className="flex items-center gap-2.5">
                  <ShieldCheck className="w-5 h-5 text-emerald-600" />
                  <div>
                    <div className="text-xs font-bold text-emerald-900">
                      Authenticated Customer ID: <span className="font-mono">{user?.customer_id}</span>
                    </div>
                    <div className="text-[11px] text-emerald-700">
                      Email: {user?.email} &bull; Consent Recorded: Yes
                    </div>
                  </div>
                </div>
              </div>

              <div className="grid sm:grid-cols-2 gap-3.5 text-xs">
                <div>
                  <label className="block font-bold text-gray-700 mb-1">Full Name (English)</label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full rounded-xl border border-gray-300 px-3 py-2 text-xs"
                  />
                </div>
                <div>
                  <label className="block font-bold text-gray-700 mb-1">Phone Number</label>
                  <input
                    type="text"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    className="w-full rounded-xl border border-gray-300 px-3 py-2 text-xs"
                  />
                </div>
                <div>
                  <label className="block font-bold text-gray-700 mb-1">Declared Insurer</label>
                  <input
                    type="text"
                    value={insurer}
                    onChange={(e) => setInsurer(e.target.value)}
                    className="w-full rounded-xl border border-gray-300 px-3 py-2 text-xs"
                  />
                </div>
                <div>
                  <label className="block font-bold text-gray-700 mb-1">
                    Default Policy Number
                  </label>
                  <input
                    type="text"
                    value={policyNumber}
                    onChange={(e) => setPolicyNumber(e.target.value)}
                    className="w-full rounded-xl border border-gray-300 px-3 py-2 text-xs font-mono"
                  />
                </div>
                <div className="sm:col-span-2">
                  <label className="block font-bold text-gray-700 mb-1">
                    Default Vehicle Registration Number
                  </label>
                  <input
                    type="text"
                    value={vehicleReg}
                    onChange={(e) => setVehicleReg(e.target.value)}
                    className="w-full rounded-xl border border-gray-300 px-3 py-2 text-xs font-mono"
                  />
                </div>
              </div>

              {savedNotice && (
                <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl px-3 py-2">
                  <Check className="w-4 h-4" /> Profile &amp; policy preferences saved!
                </div>
              )}

              <button
                type="button"
                onClick={handleSaveProfile}
                className="px-5 py-2.5 rounded-xl bg-brand-600 text-white text-xs font-bold hover:bg-brand-700"
              >
                {t('save_settings_btn')}
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 bg-gray-50 border-t border-gray-200 flex items-center justify-between">
          <span className="text-[11px] text-gray-500">
            Active UI Language: <b>{APP_LANGUAGES.find((l) => l.code === appLanguage)?.native}</b>
          </span>
          <button
            type="button"
            onClick={() => setIsSettingsOpen(false)}
            className="px-4 py-2 rounded-xl bg-gray-900 text-white text-xs font-bold hover:bg-gray-800"
          >
            {t('close_btn')}
          </button>
        </div>
      </div>
    </div>
  )
}

