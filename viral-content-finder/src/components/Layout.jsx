import { NavLink } from 'react-router-dom'
import { Flame, Zap, FileText, BarChart3, Bell } from 'lucide-react'

const navItems = [
  { to: '/', label: 'Outlier Feed', icon: Flame },
  { to: '/briefs', label: 'Content Briefs', icon: FileText },
  { to: '/digest', label: 'Daily Digest', icon: BarChart3 },
]

export default function Layout({ children, userConfig }) {
  return (
    <div className="min-h-screen bg-surface-900">
      {/* Nav — Dark translucent #0E0E12 with blur, cream text */}
      <header className="fixed top-0 left-0 right-0 z-50 glass-card border-b border-white/[0.06]">
        <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-card-green flex items-center justify-center animate-pulse-glow">
              <Zap className="w-5 h-5 text-cream" />
            </div>
            <span className="font-bold text-lg tracking-tight">
              <span className="text-gradient-cream">TURBO</span>
              <span className="text-cream-muted mx-2 font-light">|</span>
              <span className="text-cream hidden sm:inline">Viral Finder</span>
            </span>
          </div>

          <nav className="flex items-center gap-1">
            {navItems.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `flex items-center gap-2 px-3.5 py-2 rounded-xl text-sm font-medium transition-all duration-200 ${
                    isActive
                      ? 'bg-brand-400/12 text-brand-300 shadow-[0_0_12px_rgba(63,169,110,0.12)]'
                      : 'text-cream-muted hover:text-cream hover:bg-white/[0.04]'
                  }`
                }
              >
                <Icon className="w-4 h-4" />
                <span className="hidden md:inline">{label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            <button className="relative p-2 rounded-xl text-cream-muted hover:text-brand-400 hover:bg-white/[0.04] transition-all duration-200">
              <Bell className="w-4.5 h-4.5" />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-yellow-400 shadow-[0_0_6px_rgba(245,197,66,0.5)]" />
            </button>
            <div className="w-8 h-8 rounded-full bg-showcase-card flex items-center justify-center text-xs font-bold text-cream ring-2 ring-surface-800">
              {userConfig?.niches?.[0]?.charAt(0).toUpperCase() || 'U'}
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="pt-16 min-h-screen">
        <div className="max-w-7xl mx-auto px-4 py-8">
          {children}
        </div>
      </main>
    </div>
  )
}
