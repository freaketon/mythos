import { NavLink, useLocation } from 'react-router-dom'
import { Flame, Zap, FileText, BarChart3, Bell, Settings } from 'lucide-react'

const navItems = [
  { to: '/', label: 'Outlier Feed', icon: Flame },
  { to: '/briefs', label: 'Content Briefs', icon: FileText },
  { to: '/digest', label: 'Daily Digest', icon: BarChart3 },
]

export default function Layout({ children, userConfig }) {
  const location = useLocation()

  return (
    <div className="min-h-screen bg-surface-950">
      {/* Top Bar */}
      <header className="fixed top-0 left-0 right-0 z-50 bg-surface-900/80 backdrop-blur-xl border-b border-surface-800">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-500 to-purple-500 flex items-center justify-center">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <span className="font-bold text-lg tracking-tight">
              <span className="text-brand-400">TURBO</span>
              <span className="text-surface-300 mx-1.5 font-light">|</span>
              <span className="text-surface-100 hidden sm:inline">Viral Finder</span>
            </span>
          </div>

          <nav className="flex items-center gap-1">
            {navItems.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                    isActive
                      ? 'bg-brand-500/15 text-brand-400'
                      : 'text-surface-300 hover:text-surface-100 hover:bg-surface-800'
                  }`
                }
              >
                <Icon className="w-4 h-4" />
                <span className="hidden md:inline">{label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <button className="relative p-2 rounded-lg text-surface-300 hover:text-surface-100 hover:bg-surface-800 transition-colors">
              <Bell className="w-4 h-4" />
              <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-red-500" />
            </button>
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-400 to-pink-400 flex items-center justify-center text-xs font-bold text-white">
              {userConfig?.niches?.[0]?.charAt(0).toUpperCase() || 'U'}
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="pt-14 min-h-screen">
        <div className="max-w-7xl mx-auto px-4 py-6">
          {children}
        </div>
      </main>
    </div>
  )
}
