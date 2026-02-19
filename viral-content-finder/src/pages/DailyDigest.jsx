import { useMemo } from 'react'
import {
  BarChart3, TrendingUp, Flame, Zap, Eye,
  AlertTriangle, Clock, Bell, ChevronRight,
  Send, Sparkles
} from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar, Cell } from 'recharts'
import { generateDailyDigest, formatNumber } from '../data/fakeData'

const statusConfig = {
  emerging: { bg: 'bg-brand-400/12', text: 'text-brand-400', border: 'border-brand-400/20', dot: 'bg-brand-400' },
  peaking: { bg: 'bg-yellow-400/12', text: 'text-yellow-400', border: 'border-yellow-400/20', dot: 'bg-yellow-400' },
  saturated: { bg: 'bg-red-400/12', text: 'text-red-400', border: 'border-red-400/20', dot: 'bg-red-400' },
}

function TrendAlert({ trend }) {
  const sc = statusConfig[trend.status]

  return (
    <div className={`p-4 rounded-2xl border ${sc.border} bg-surface-800/30`}>
      <div className="flex items-start gap-3">
        <div className={`w-2 h-2 rounded-full mt-2 ${sc.dot} shadow-[0_0_6px_currentColor]`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1.5">
            <h4 className="text-sm font-semibold text-cream">
              {trend.title}
            </h4>
            <span className={`px-2 py-0.5 rounded-lg text-xs font-semibold ${sc.bg} ${sc.text}`}>
              {trend.status}
            </span>
            <span className="text-xs font-bold text-brand-400">{trend.velocity}</span>
          </div>
          <p className="text-sm text-cream-muted leading-relaxed mb-2" style={{ fontFamily: "'DM Sans', sans-serif" }}>{trend.description}</p>
          <div className="text-xs text-cream-muted/60">
            {trend.reelsCount} Reels detected
          </div>
        </div>
      </div>
    </div>
  )
}

export default function DailyDigest({ userConfig }) {
  const digest = useMemo(() => generateDailyDigest(), [])

  const hourlyActivity = Array.from({ length: 24 }, (_, i) => ({
    hour: `${i}:00`,
    outliers: Math.floor(Math.random() * 8) + (i >= 8 && i <= 22 ? 3 : 0),
  }))

  const nicheDistribution = [
    { name: 'Fitness', count: 8, fill: '#3FA96E' },
    { name: 'Food', count: 5, fill: '#a855f7' },
    { name: 'Fashion', count: 4, fill: '#f472b6' },
    { name: 'Tech', count: 3, fill: '#F5C542' },
    { name: 'Beauty', count: 3, fill: '#2dd4bf' },
  ]

  return (
    <div>
      {/* Page Header */}
      <div className="mb-8">
        <div className="flex items-center gap-4 mb-2">
          <div className="p-2.5 rounded-2xl bg-game-teal">
            <BarChart3 className="w-6 h-6 text-cream" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-cream">
              Daily Digest
            </h1>
            <p className="text-sm text-cream-muted" style={{ fontFamily: "'DM Sans', sans-serif" }}>{digest.date}</p>
          </div>
        </div>
      </div>

      {/* Morning Push — beige style */}
      <div className="p-5 rounded-2xl bg-beige mb-8">
        <div className="flex items-start gap-4">
          <div className="p-2.5 rounded-xl bg-card-green">
            <Bell className="w-5 h-5 text-cream" />
          </div>
          <div className="flex-1">
            <div className="text-xs text-brand-500 font-bold mb-1.5 tracking-wider uppercase">Morning Push</div>
            <p className="text-sm text-surface-900 font-medium mb-1.5">
              3 Reels broke out in your niche overnight. Here's what to film today.
            </p>
            <p className="text-xs text-surface-400 leading-relaxed" style={{ fontFamily: "'DM Sans', sans-serif" }}>
              The "One Thing" advice format is emerging fast (+340% in 6h). We've generated briefs based on this pattern.
            </p>
          </div>
          <ChevronRight className="w-5 h-5 text-surface-400 flex-shrink-0 mt-1" />
        </div>
      </div>

      {/* Summary Stats — game-card colored */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
        {[
          { label: 'New Outliers', value: digest.summary.newOutliers, icon: Flame, bg: 'bg-card-green', textColor: 'text-cream' },
          { label: 'Avg Multiplier', value: digest.summary.avgMultiplier, icon: Zap, bg: 'bg-cta-amber', textColor: 'text-surface-900' },
          { label: 'Top Niche', value: 'Fitness', icon: TrendingUp, bg: 'bg-showcase-card', textColor: 'text-cream' },
          { label: 'Emerging Trends', value: digest.summary.emergingTrends, icon: Sparkles, bg: 'bg-game-teal', textColor: 'text-cream' },
        ].map(({ label, value, icon: Icon, bg, textColor }) => (
          <div key={label} className={`${bg} p-4 rounded-2xl`}>
            <div className={`flex items-center gap-2 mb-2.5 ${textColor} opacity-75`}>
              <Icon className="w-3.5 h-3.5" />
              <span className="text-xs">{label}</span>
            </div>
            <div className={`text-2xl font-bold ${textColor}`}>{value}</div>
          </div>
        ))}
      </div>

      {/* Charts Row — showcase dark bg */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-8">
        {/* Hourly Activity */}
        <div className="glass-card p-5 rounded-2xl">
          <h3 className="text-sm font-semibold text-cream mb-4 flex items-center gap-2">
            <Clock className="w-4 h-4 text-cream-muted" />
            Outlier Activity by Hour
          </h3>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={hourlyActivity}>
              <defs>
                <linearGradient id="activityGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3FA96E" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#3FA96E" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="hour"
                tick={{ fill: '#6b6565', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                interval={5}
              />
              <YAxis
                tick={{ fill: '#6b6565', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                width={25}
              />
              <Tooltip
                contentStyle={{
                  background: '#0E0E12',
                  border: '1px solid rgba(63,169,110,0.2)',
                  borderRadius: '12px',
                  fontSize: '12px',
                  color: '#FFF8EE',
                  boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
                }}
              />
              <Area
                type="monotone"
                dataKey="outliers"
                stroke="#3FA96E"
                strokeWidth={2}
                fill="url(#activityGradient)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Niche Distribution */}
        <div className="glass-card p-5 rounded-2xl">
          <h3 className="text-sm font-semibold text-cream mb-4 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-cream-muted" />
            Outliers by Niche
          </h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={nicheDistribution} layout="vertical">
              <XAxis type="number" tick={{ fill: '#6b6565', fontSize: 10 }} tickLine={false} axisLine={false} />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: '#c8bfb0', fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={60}
              />
              <Tooltip
                contentStyle={{
                  background: '#0E0E12',
                  border: '1px solid rgba(168,85,247,0.2)',
                  borderRadius: '12px',
                  fontSize: '12px',
                  color: '#FFF8EE',
                  boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
                }}
              />
              <Bar dataKey="count" radius={[0, 8, 8, 0]} barSize={18}>
                {nicheDistribution.map((entry, i) => (
                  <Cell key={i} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Trend Alerts */}
      <div className="mb-8">
        <h2 className="text-lg font-bold text-cream mb-4 flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-yellow-400" />
          Trend Alerts
        </h2>
        <div className="space-y-3">
          {digest.trendAlerts.map((trend) => (
            <TrendAlert key={trend.id} trend={trend} />
          ))}
        </div>
      </div>

      {/* Top Outliers Preview */}
      <div className="mb-8">
        <h2 className="text-lg font-bold text-cream mb-4 flex items-center gap-2">
          <Flame className="w-5 h-5 text-brand-400" />
          Top Outliers Today
        </h2>
        <div className="space-y-2">
          {digest.topOutliers.map((reel, i) => {
            const thumbGradients = ['bg-card-green', 'bg-game-purple', 'bg-game-amber', 'bg-game-teal', 'bg-game-red']
            return (
              <div
                key={reel.id}
                className="flex items-center gap-4 p-4 rounded-2xl glass-card hover:border-brand-400/15 transition-all duration-200"
              >
                <div className="w-8 h-8 rounded-xl bg-surface-800 flex items-center justify-center text-sm font-bold text-cream-muted">
                  {i + 1}
                </div>
                <div className={`w-12 h-12 rounded-xl flex-shrink-0 ${thumbGradients[i % thumbGradients.length]}`} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-cream truncate">{reel.topic}</div>
                  <div className="text-xs text-cream-muted">
                    {reel.creator.handle} · {reel.timeAgo}
                  </div>
                </div>
                <div className="text-right flex-shrink-0">
                  <div className="flex items-center gap-1 text-sm font-bold text-yellow-400">
                    <Zap className="w-3.5 h-3.5" />
                    {reel.multiplier}x
                  </div>
                  <div className="text-xs text-cream-muted flex items-center gap-1">
                    <Eye className="w-3 h-3" />
                    {formatNumber(reel.views)}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Email Signup CTA — amber/yellow */}
      <div className="p-6 rounded-2xl bg-cta-amber">
        <div className="flex items-start gap-4">
          <div className="p-3 rounded-2xl bg-surface-900/15">
            <Send className="w-6 h-6 text-surface-900" />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-bold text-surface-900 mb-1.5">
              Get this digest every morning
            </h3>
            <p className="text-sm text-surface-900/70 mb-5 leading-relaxed" style={{ fontFamily: "'DM Sans', sans-serif" }}>
              Receive your personalized outlier report and content briefs at 7:00 AM daily.
            </p>
            <div className="flex gap-2">
              <input
                type="email"
                placeholder="your@email.com"
                className="flex-1 px-4 py-3 bg-white/30 border border-surface-900/10 rounded-xl text-sm text-surface-900 placeholder:text-surface-900/50 focus:outline-none focus:bg-white/50 transition-all duration-200"
              />
              <button className="px-6 py-3 rounded-xl bg-surface-900 text-cream text-sm font-bold hover:bg-surface-950 transition-all duration-200">
                Subscribe
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
