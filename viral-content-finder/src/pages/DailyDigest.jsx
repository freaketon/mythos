import { useMemo } from 'react'
import {
  BarChart3, TrendingUp, Flame, Zap, Eye,
  AlertTriangle, Clock, Bell, ChevronRight,
  Send, Sparkles
} from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar, Cell } from 'recharts'
import { generateDailyDigest, formatNumber } from '../data/fakeData'

const statusConfig = {
  emerging: { bg: 'bg-brand-500/12', text: 'text-brand-400', border: 'border-brand-500/20', dot: 'bg-brand-500' },
  peaking: { bg: 'bg-yellow-400/12', text: 'text-yellow-400', border: 'border-yellow-400/20', dot: 'bg-yellow-400' },
  saturated: { bg: 'bg-red-400/12', text: 'text-red-400', border: 'border-red-400/20', dot: 'bg-red-400' },
}

function TrendAlert({ trend }) {
  const sc = statusConfig[trend.status]

  return (
    <div className={`p-4 rounded-2xl border ${sc.border} bg-surface-900/40`}>
      <div className="flex items-start gap-3">
        <div className={`w-2 h-2 rounded-full mt-2 ${sc.dot} shadow-[0_0_6px_currentColor]`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1.5">
            <h4 className="text-sm font-semibold text-surface-100" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              {trend.title}
            </h4>
            <span className={`px-2 py-0.5 rounded-lg text-xs font-semibold ${sc.bg} ${sc.text}`}>
              {trend.status}
            </span>
            <span className="text-xs font-bold text-brand-400">{trend.velocity}</span>
          </div>
          <p className="text-sm text-surface-300 leading-relaxed mb-2">{trend.description}</p>
          <div className="text-xs text-surface-400">
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
    { name: 'Fitness', count: 8, fill: '#00E87B' },
    { name: 'Food', count: 5, fill: '#a855f7' },
    { name: 'Fashion', count: 4, fill: '#f472b6' },
    { name: 'Tech', count: 3, fill: '#c084fc' },
    { name: 'Beauty', count: 3, fill: '#34d399' },
  ]

  return (
    <div>
      {/* Page Header */}
      <div className="mb-8">
        <div className="flex items-center gap-4 mb-2">
          <div className="p-2.5 rounded-2xl bg-accent-500/10 border border-accent-500/20">
            <BarChart3 className="w-6 h-6 text-accent-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Daily Digest
            </h1>
            <p className="text-sm text-surface-300">{digest.date}</p>
          </div>
        </div>
      </div>

      {/* Morning Push Notification Preview */}
      <div className="p-5 rounded-2xl bg-gradient-to-r from-brand-500/8 to-accent-500/8 border border-brand-500/15 mb-8">
        <div className="flex items-start gap-4">
          <div className="p-2.5 rounded-xl bg-brand-500/15 border border-brand-500/20">
            <Bell className="w-5 h-5 text-brand-400" />
          </div>
          <div className="flex-1">
            <div className="text-xs text-brand-400 font-semibold mb-1.5 tracking-wider uppercase">Morning Push</div>
            <p className="text-sm text-surface-100 font-medium mb-1.5">
              3 Reels broke out in your niche overnight. Here's what to film today.
            </p>
            <p className="text-xs text-surface-400 leading-relaxed">
              The "One Thing" advice format is emerging fast (+340% in 6h). We've generated briefs based on this pattern.
            </p>
          </div>
          <ChevronRight className="w-5 h-5 text-surface-400 flex-shrink-0 mt-1" />
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
        {[
          { label: 'New Outliers', value: digest.summary.newOutliers, icon: Flame, color: 'text-brand-400', iconBg: 'bg-brand-500/12' },
          { label: 'Avg Multiplier', value: digest.summary.avgMultiplier, icon: Zap, color: 'text-yellow-400', iconBg: 'bg-yellow-400/12' },
          { label: 'Top Niche', value: 'Fitness', icon: TrendingUp, color: 'text-accent-400', iconBg: 'bg-accent-500/12' },
          { label: 'Emerging Trends', value: digest.summary.emergingTrends, icon: Sparkles, color: 'text-purple-400', iconBg: 'bg-purple-500/12' },
        ].map(({ label, value, icon: Icon, color, iconBg }) => (
          <div key={label} className="glass-card p-4 rounded-2xl">
            <div className="flex items-center gap-2 mb-2.5">
              <div className={`p-1.5 rounded-lg ${iconBg}`}>
                <Icon className={`w-3.5 h-3.5 ${color}`} />
              </div>
              <span className="text-xs text-surface-400">{label}</span>
            </div>
            <div className={`text-2xl font-bold ${color}`}>{value}</div>
          </div>
        ))}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-8">
        {/* Hourly Activity */}
        <div className="glass-card p-5 rounded-2xl">
          <h3 className="text-sm font-semibold text-surface-100 mb-4 flex items-center gap-2" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            <Clock className="w-4 h-4 text-surface-400" />
            Outlier Activity by Hour
          </h3>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={hourlyActivity}>
              <defs>
                <linearGradient id="activityGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#00E87B" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#00E87B" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="hour"
                tick={{ fill: '#6e7681', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                interval={5}
              />
              <YAxis
                tick={{ fill: '#6e7681', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                width={25}
              />
              <Tooltip
                contentStyle={{
                  background: '#141b27',
                  border: '1px solid rgba(0,232,123,0.15)',
                  borderRadius: '12px',
                  fontSize: '12px',
                  boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
                }}
              />
              <Area
                type="monotone"
                dataKey="outliers"
                stroke="#00E87B"
                strokeWidth={2}
                fill="url(#activityGradient)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Niche Distribution */}
        <div className="glass-card p-5 rounded-2xl">
          <h3 className="text-sm font-semibold text-surface-100 mb-4 flex items-center gap-2" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            <BarChart3 className="w-4 h-4 text-surface-400" />
            Outliers by Niche
          </h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={nicheDistribution} layout="vertical">
              <XAxis type="number" tick={{ fill: '#6e7681', fontSize: 10 }} tickLine={false} axisLine={false} />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: '#8b949e', fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={60}
              />
              <Tooltip
                contentStyle={{
                  background: '#141b27',
                  border: '1px solid rgba(168,85,247,0.15)',
                  borderRadius: '12px',
                  fontSize: '12px',
                  boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
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
        <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
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
        <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
          <Flame className="w-5 h-5 text-brand-400" />
          Top Outliers Today
        </h2>
        <div className="space-y-2">
          {digest.topOutliers.map((reel, i) => (
            <div
              key={reel.id}
              className="flex items-center gap-4 p-4 rounded-2xl glass-card hover:border-brand-500/15 transition-all duration-200"
            >
              <div className="w-8 h-8 rounded-xl bg-surface-800/80 flex items-center justify-center text-sm font-bold text-surface-300">
                {i + 1}
              </div>
              <div
                className="w-12 h-12 rounded-xl flex-shrink-0"
                style={{ background: `linear-gradient(135deg, ${reel.thumbnailColor}, ${reel.thumbnailColor}cc)` }}
              />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-surface-100 truncate">{reel.topic}</div>
                <div className="text-xs text-surface-400">
                  {reel.creator.handle} · {reel.timeAgo}
                </div>
              </div>
              <div className="text-right flex-shrink-0">
                <div className="flex items-center gap-1 text-sm font-bold text-brand-400">
                  <Zap className="w-3.5 h-3.5" />
                  {reel.multiplier}x
                </div>
                <div className="text-xs text-surface-400 flex items-center gap-1">
                  <Eye className="w-3 h-3" />
                  {formatNumber(reel.views)}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Email Signup CTA */}
      <div className="p-6 rounded-2xl bg-gradient-to-br from-surface-900/80 to-surface-800/40 border border-surface-700/30">
        <div className="flex items-start gap-4">
          <div className="p-3 rounded-2xl bg-gradient-to-br from-brand-500/15 to-accent-500/15 border border-brand-500/15">
            <Send className="w-6 h-6 text-brand-400" />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-bold text-white mb-1.5" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Get this digest every morning
            </h3>
            <p className="text-sm text-surface-300 mb-5 leading-relaxed">
              Receive your personalized outlier report and content briefs at 7:00 AM daily.
            </p>
            <div className="flex gap-2">
              <input
                type="email"
                placeholder="your@email.com"
                className="flex-1 px-4 py-3 bg-surface-900/60 border border-surface-700/50 rounded-xl text-sm text-surface-100 placeholder:text-surface-400 focus:outline-none focus:border-brand-500/50 focus:shadow-[0_0_12px_rgba(0,232,123,0.1)] transition-all duration-200"
              />
              <button className="px-6 py-3 rounded-xl bg-gradient-to-r from-brand-500 to-brand-600 text-white text-sm font-semibold hover:shadow-[0_0_20px_rgba(0,232,123,0.25)] transition-all duration-200">
                Subscribe
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
