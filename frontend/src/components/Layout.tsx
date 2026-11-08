import { useEffect, useState } from 'react'
import { Outlet, Link, useLocation, useNavigate, Navigate } from 'react-router-dom'
import { LayoutDashboard, PlusCircle, Shield, UserCheck, LogOut, Settings, Globe } from 'lucide-react'
import { getStoredUser, clearStoredAuth } from '../api'
import type { UserProfile } from '../types'
import { APP_LANGUAGES, useAppSettings, type AppLanguageCode } from '../i18n'
import SettingsModal from './SettingsModal'

export default function Layout() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const [user, setUser] = useState<UserProfile | null>(getStoredUser())
  const { appLanguage, setAppLanguage, setIsSettingsOpen, t } = useAppSettings()

  useEffect(() => {
    const syncAuth = () => setUser(getStoredUser())
    window.addEventListener('claimsathi-auth-change', syncAuth)
    return () => window.removeEventListener('claimsathi-auth-change', syncAuth)
  }, [])

  // Require login first before accessing protected pages
  if (!user) {
    return <Navigate to="/login" replace />
  }

  const handleLogout = () => {
    clearStoredAuth()
    navigate('/login', { replace: true })
  }

  const navItems = [
    { to: '/dashboard', label: t('nav_vault'), icon: LayoutDashboard },
    { to: '/claims/new', label: t('nav_new_claim'), icon: PlusCircle },
  ]

  return (
    <div className="min-h-screen flex flex-col bg-gray-50/60">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-30 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-3">
          <Link to="/dashboard" className="flex items-center gap-2 shrink-0">
            <Shield className="w-7 h-7 text-brand-600" />
            <div>
              <span className="text-xl font-bold text-brand-900">
                ClaimSathi <span className="text-brand-500">AI</span>
              </span>
            </div>
          </Link>

          <div className="flex items-center gap-2 sm:gap-2.5 flex-wrap justify-end">
            <nav className="flex items-center gap-1">
              {navItems.map(({ to, label, icon: Icon }) => (
                <Link
                  key={to}
                  to={to}
                  className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs sm:text-sm font-medium transition-colors ${
                    pathname.startsWith(to)
                      ? 'bg-brand-50 text-brand-700'
                      : 'text-gray-600 hover:bg-gray-100'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span className="hidden md:inline">{label}</span>
                </Link>
              ))}
            </nav>

            {/* Quick App Language Switcher */}
            <div className="inline-flex items-center gap-1 bg-blue-50/80 border border-blue-200 rounded-xl px-2.5 py-1">
              <Globe className="w-3.5 h-3.5 text-blue-600 shrink-0" />
              <select
                value={appLanguage}
                onChange={(e) => setAppLanguage(e.target.value as AppLanguageCode)}
                aria-label="App Display Language"
                className="bg-transparent text-xs font-bold text-blue-900 focus:outline-none cursor-pointer"
              >
                {APP_LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.native} ({l.label})
                  </option>
                ))}
              </select>
            </div>

            {/* Settings & Profile Modal Trigger */}
            <button
              type="button"
              onClick={() => setIsSettingsOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-gray-100 hover:bg-gray-200 text-gray-800 text-xs font-bold transition-colors border border-gray-200"
              title={t('nav_settings')}
            >
              <Settings className="w-3.5 h-3.5 text-brand-600" />
              <span className="hidden sm:inline">{t('nav_settings')}</span>
            </button>

            <div className="hidden lg:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold">
              <UserCheck className="w-3.5 h-3.5 text-emerald-600" />
              <span>{user.customer_id}</span>
              <span className="text-emerald-600">&bull; {user.name}</span>
            </div>

            <button
              type="button"
              onClick={handleLogout}
              title={t('nav_sign_out')}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl border border-gray-200 text-gray-600 text-xs font-semibold hover:bg-red-50 hover:text-red-600 hover:border-red-200 transition-colors"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{t('nav_sign_out')}</span>
            </button>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">
        <Outlet />
      </main>

      {/* Global Settings & Profile Modal */}
      <SettingsModal />
    </div>
  )
}
