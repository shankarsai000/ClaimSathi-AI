import { useEffect, useState } from 'react'
import { Outlet, Link, useLocation, useNavigate, Navigate } from 'react-router-dom'
import { LayoutDashboard, PlusCircle, Shield, UserCheck, LogOut, Settings, Globe } from 'lucide-react'
import { getStoredUser, clearStoredAuth, api } from '../api'
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
    const handleExpired = () => {
      setUser(null)
      navigate('/login', { replace: true })
    }
    window.addEventListener('claimsathi-auth-change', syncAuth)
    window.addEventListener('claimsathi-session-expired', handleExpired)
    return () => {
      window.removeEventListener('claimsathi-auth-change', syncAuth)
      window.removeEventListener('claimsathi-session-expired', handleExpired)
    }
  }, [navigate])

  // Require login first before accessing protected pages
  if (!user) {
    return <Navigate to="/login" replace />
  }

  const handleLogout = async () => {
    await api.logout()
    navigate('/login', { replace: true })
  }

  const navItems = [
    { to: '/dashboard', label: t('nav_vault'), icon: LayoutDashboard },
    { to: '/claims/new', label: t('nav_new_claim'), icon: PlusCircle },
    { to: '/evidence-verify', label: 'Evidence & Instant Estimate', icon: Shield },
  ]

  return (
    <div className="min-h-screen flex flex-col bg-gray-50/60">
      {/* Header - Fixed Viewport Collision & Clean 3-Zone Flex Nav */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-40 shadow-xs box-border px-4 sm:px-6 py-3 min-h-[68px] no-print">
        <div className="max-w-[1440px] mx-auto flex items-center justify-between gap-3 flex-wrap lg:flex-nowrap">
          {/* Left Zone: Brand */}
          <Link to="/dashboard" className="flex items-center gap-2 shrink-0">
            <div className="w-9 h-9 rounded-xl bg-brand-50 flex items-center justify-center border border-brand-100">
              <Shield className="w-5 h-5 text-brand-600" />
            </div>
            <div>
              <span className="text-lg sm:text-xl font-bold tracking-tight text-brand-900">
                ClaimSathi <span className="text-brand-500">AI</span>
              </span>
            </div>
          </Link>

          {/* Center Zone: Main Navigation Tabs */}
          <nav className="flex items-center gap-1.5 sm:gap-2 shrink-0 order-3 lg:order-2 overflow-x-auto py-1 max-w-full">
            {navItems.map(({ to, label, icon: Icon }) => (
              <Link
                key={to}
                to={to}
                className={`flex items-center gap-1.5 px-3 py-1.5 sm:px-3.5 sm:py-2 rounded-lg text-xs sm:text-[13px] font-semibold whitespace-nowrap transition-all ${
                  pathname.startsWith(to)
                    ? 'bg-brand-50 text-brand-700 shadow-xs border border-brand-200/60'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                }`}
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span>{label}</span>
              </Link>
            ))}
          </nav>

          {/* Right Zone: Utility, User Badge & Actions */}
          <div className="flex items-center gap-2 shrink-0 order-2 lg:order-3">
            {/* Quick App Language Switcher */}
            <div className="inline-flex items-center gap-1 bg-blue-50/80 border border-blue-200 rounded-lg px-2.5 py-1.5 shrink-0">
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
              className="inline-flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg bg-gray-100 hover:bg-gray-200 text-gray-800 text-xs font-bold transition-colors border border-gray-200 shrink-0"
              title={t('nav_settings')}
            >
              <Settings className="w-3.5 h-3.5 text-brand-600 shrink-0" />
              <span className="hidden xl:inline">{t('nav_settings')}</span>
            </button>

            {/* User Badge */}
            <div className="hidden md:inline-flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold shrink-0">
              <UserCheck className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
              <span>{user.customer_id}</span>
              <span className="text-emerald-600 hidden xl:inline">&bull; {user.name}</span>
            </div>

            {/* Sign Out Button */}
            <button
              type="button"
              onClick={handleLogout}
              title={t('nav_sign_out')}
              className="inline-flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 text-xs font-semibold hover:bg-red-50 hover:text-red-600 hover:border-red-200 transition-colors shrink-0"
            >
              <LogOut className="w-3.5 h-3.5 shrink-0" />
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
