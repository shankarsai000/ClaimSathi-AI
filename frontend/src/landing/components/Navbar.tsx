import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Shield, ArrowRight, Menu, X } from 'lucide-react'
import { getStoredUser } from '../../api'

interface NavbarProps {
  onOpenPilotModal: () => void
}

export default function Navbar({ onOpenPilotModal }: NavbarProps) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const isLoggedIn = Boolean(getStoredUser())

  const navLinks = [
    { href: '#playground', label: 'Interactive Demo' },
    { href: '#how-it-works', label: 'How It Works' },
    { href: '#anti-fraud', label: 'Anti-Fraud' },
    { href: '#compliance', label: 'Compliance' },
  ]

  return (
    <header className="sticky top-0 z-50 backdrop-blur-md bg-white/88 border-b border-slate-200/80">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
        {/* Left: Brand */}
        <a href="#top" className="flex items-center gap-2.5 shrink-0">
          <div className="w-9 h-9 rounded-xl bg-brand-600 flex items-center justify-center text-white shadow-xs">
            <Shield className="w-5 h-5" />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-lg font-extrabold tracking-tight text-slate-900">
              ClaimSathi <span className="text-brand-600">AI</span>
            </span>
            <span className="hidden sm:inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-brand-700 border border-blue-200">
              MOTOR 2W/4W
            </span>
          </div>
        </a>

        {/* Center: Clean 4-item navigation */}
        <nav className="hidden md:flex items-center gap-7">
          {navLinks.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="text-sm font-semibold text-slate-600 hover:text-slate-950 transition-colors"
            >
              {item.label}
            </a>
          ))}
        </nav>

        {/* Right: Dual-CTA Pattern */}
        <div className="hidden md:flex items-center gap-3 shrink-0">
          <Link
            to={isLoggedIn ? '/dashboard' : '/login'}
            className="px-3.5 py-2 rounded-xl text-sm font-semibold text-slate-700 hover:text-slate-950 hover:bg-slate-100 transition-colors"
          >
            {isLoggedIn ? 'Open Vault' : 'Sign In'}
          </Link>
          <button
            type="button"
            onClick={onOpenPilotModal}
            className="px-4 py-2 rounded-xl text-sm font-semibold text-slate-700 border border-slate-200 hover:border-slate-300 bg-white transition-all"
          >
            Book Pilot
          </button>
          <Link
            to={isLoggedIn ? '/claims/new' : '/login'}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-sm font-bold shadow-xs transition-all"
          >
            <span>Launch Live Demo</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>

        {/* Mobile menu button */}
        <button
          type="button"
          onClick={() => setMobileOpen((prev) => !prev)}
          aria-label="Toggle Menu"
          className="md:hidden p-2 rounded-xl text-slate-700 hover:bg-slate-100"
        >
          {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="md:hidden border-t border-slate-200 bg-white px-4 py-4 space-y-3">
          <div className="flex flex-col space-y-2">
            {navLinks.map((item) => (
              <a
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                className="px-3 py-2 rounded-xl text-sm font-semibold text-slate-700 hover:bg-slate-100"
              >
                {item.label}
              </a>
            ))}
          </div>
          <div className="pt-2 border-t border-slate-100 flex flex-col gap-2">
            <button
              type="button"
              onClick={() => {
                setMobileOpen(false)
                onOpenPilotModal()
              }}
              className="w-full py-2.5 rounded-xl border border-slate-200 text-sm font-semibold text-slate-800"
            >
              Book Surveyor / Insurer Pilot
            </button>
            <Link
              to={isLoggedIn ? '/claims/new' : '/login'}
              onClick={() => setMobileOpen(false)}
              className="w-full py-2.5 rounded-xl bg-brand-600 text-white text-sm font-bold text-center"
            >
              Launch Live Demo
            </Link>
          </div>
        </div>
      )}
    </header>
  )
}
