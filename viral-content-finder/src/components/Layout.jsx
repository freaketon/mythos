import { NavLink } from 'react-router-dom'
import { Flame, Zap, FileText, BarChart3, Bell } from 'lucide-react'

const navItems = [
  { to: '/', label: 'Outlier Feed', icon: Flame },
  { to: '/briefs', label: 'Content Briefs', icon: FileText },
  { to: '/digest', label: 'Daily Digest', icon: BarChart3 },
]

export default function Layout({ children, userConfig }) {
  return (
    <div className="min-h-screen bg-surface-950 bg-gradient-animated">
      {/* Top Bar — glass morphism */}
      <header className="fixed top-0 left-0 right-0 z-50 glass-card border-b border-surface-800/50">
        <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-500 to-accent-500 flex items-center justify-center animate-pulse-glow">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <span className="font-bold text-lg tracking-tight" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              <span className="text-gradient-green">TURBO</span>
              <span className="text-surface-400 mx-2 font-light">|</span>
              <span className="text-surface-100 hidden sm:inline">Viral Finder</span>
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
                      ? 'bg-brand-500/12 text-brand-400 shadow-[0_0_12px_rgba(0,232,123,0.1)]'
                      : 'text-surface-300 hover:text-surface-100 hover:bg-surface-800/50'
                  }`
                }
              >
                <Icon className="w-4 h-4" />
                <span className="hidden md:inline">{label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            <button className="relative p-2 rounded-xl text-surface-300 hover:text-brand-400 hover:bg-surface-800/50 transition-all duration-200">
              <Bell className="w-4.5 h-4.5" />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-brand-500 shadow-[0_0_6px_rgba(0,232,123,0.5)]" />
            </button>
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-500 to-accent-500 flex items-center justify-center text-xs font-bold text-white ring-2 ring-surface-800">
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
