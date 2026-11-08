import { useEffect, useState } from 'react'
import { Outlet, Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, PlusCircle, Shield, UserCheck } from 'lucide-react'
import { api, getStoredUser } from '../api'
import type { UserProfile } from '../types'

const navItems = [
  { to: '/dashboard', label: 'Customer Claims Vault', icon: LayoutDashboard },
  { to: '/claims/new', label: 'New Claim Wizard', icon: PlusCircle },
]

export default function Layout() {
  const { pathname } = useLocation()
  const [user, setUser] = useState<UserProfile | null>(getStoredUser())

  useEffect(() => {
    const syncAuth = () => setUser(getStoredUser())
    window.addEventListener('claimsathi-auth-change', syncAuth)

    // Auto-initialize Rahul's seeded account (USR-100001) if no session is stored yet
    if (!getStoredUser()) {
      api
        .login({ identifier: 'USR-100001', demo_quick_login: true })
        .then((res) => setUser(res.user))
        .catch(() => {})
    }

    return () => window.removeEventListener('claimsathi-auth-change', syncAuth)
  }, [])

  return (
    <div className="min-h-screen flex flex-col bg-gray-50/60">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-30 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
          <Link to="/" className="flex items-center gap-2 shrink-0">
            <Shield className="w-7 h-7 text-brand-600" />
            <div>
              <span className="text-xl font-bold text-brand-900">
                ClaimSathi <span className="text-brand-500">AI</span>
              </span>
              <span className="hidden md:inline-block ml-2 text-[11px] font-semibold bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded-full">
                Multilingual Intake + Evidence Integrity + Dossier Engine
              </span>
            </div>
          </Link>

          <div className="flex items-center gap-3">
            <nav className="flex items-center gap-1">
              {navItems.map(({ to, label, icon: Icon }) => (
                <Link
                  key={to}
                  to={to}
                  className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    pathname.startsWith(to)
                      ? 'bg-brand-50 text-brand-700'
                      : 'text-gray-600 hover:bg-gray-100'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span className="hidden sm:inline">{label}</span>
                </Link>
              ))}
            </nav>

            {user && (
              <Link
                to="/dashboard"
                title="View Customer Claims Vault & Account Settings"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold hover:bg-emerald-100 transition-colors"
              >
                <UserCheck className="w-3.5 h-3.5 text-emerald-600" />
                <span>{user.customer_id}</span>
                <span className="hidden sm:inline text-emerald-600">&bull; {user.name}</span>
              </Link>
            )}
          </div>
        </div>
      </header>

      {/* Demo & Compliance Banner */}
      <div className="bg-amber-50 border-b border-amber-200 text-amber-900 text-center text-xs py-1.5 px-4 font-medium">
        🛡️ <strong>ClaimSathi AI Platform (Phases 1–7)</strong> – Real C2PA/SynthID Provenance Inspection, SHA-256 + 64-bit DCT pHash Screening, 9-Section Claim Dossier &amp; Mock Insurer Integration Gateway.
      </div>

      {/* Content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">
        <Outlet />
      </main>
    </div>
  )
}
