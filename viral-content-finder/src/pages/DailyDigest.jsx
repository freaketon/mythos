import { useMemo } from 'react'
import {
  BarChart3, TrendingUp, Flame, Zap, Eye, ArrowUpRight,
  AlertTriangle, CheckCircle, Clock, Bell, ChevronRight,
  Send, Sparkles
} from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar, Cell } from 'recharts'
import { generateDailyDigest, formatNumber } from '../data/fakeData'

const statusConfig = {
  emerging: { bg: 'bg-emerald-400/15', text: 'text-emerald-400', border: 'border-emerald-400/20', dot: 'bg-emerald-400' },
  peaking: { bg: 'bg-yellow-400/15', text: 'text-yellow-400', border: 'border-yellow-400/20', dot: 'bg-yellow-400' },
  saturated: { bg: 'bg-red-400/15', text: 'text-red-400', border: 'border-red-400/20', dot: 'bg-red-400' },
}

function TrendAlert({ trend }) {
  const sc = statusConfig[trend.status]

  return (
    <div className={`p-4 rounded-xl border ${sc.border} ${sc.bg.replace('/15', '/5')}`}>
      <div className="flex items-start gap-3">
        <div className={`w-2 h-2 rounded-full mt-2 ${sc.dot}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <h4 className="text-sm font-semibold text-surface-100">{trend.title}</h4>
            <span className={`px-2 py-0.5 rounded-md text-xs font-semibold ${sc.bg} ${sc.text}`}>
              {trend.status}
            </span>
            <span className="text-xs font-bold text-emerald-400">{trend.velocity}</span>
          </div>
          <p className="text-sm text-surface-300 leading-relaxed mb-2">{trend.description}</p>
          <div className="text-xs text-surface-300">
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
    { name: 'Fitness', count: 8, fill: '#10b981' },
    { name: 'Food', count: 5, fill: '#f97316' },
    { name: 'Fashion', count: 4, fill: '#ec4899' },
    { name: 'Tech', count: 3, fill: '#3b5cff' },
    { name: 'Beauty', count: 3, fill: '#a855f7' },
  ]

  return (
    <div>
      {/* Page Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2 rounded-xl bg-purple-500/15">
            <BarChart3 className="w-5 h-5 text-purple-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-surface-100">Daily Digest</h1>
            <p className="text-sm text-surface-300">{digest.date}</p>
          </div>
        </div>
      </div>

      {/* Morning Push Notification Preview */}
      <div className="p-4 rounded-xl bg-gradient-to-r from-brand-500/10 to-purple-500/10 border border-brand-500/20 mb-6">
        <div className="flex items-start gap-3">
          <div className="p-2 rounded-lg bg-brand-500/20">
            <Bell className="w-4 h-4 text-brand-400" />
          </div>
          <div className="flex-1">
            <div className="text-xs text-brand-400 font-medium mb-1">MORNING PUSH</div>
            <p className="text-sm text-surface-100 font-medium mb-1">
              3 Reels broke out in your niche overnight. Here's what to film today.
            </p>
            <p className="text-xs text-surface-300">
              The "One Thing" advice format is emerging fast (+340% in 6h). We've generated briefs based on this pattern.
            </p>
          </div>
          <ChevronRight className="w-4 h-4 text-surface-300 flex-shrink-0 mt-1" />
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        {[
          { label: 'New Outliers', value: digest.summary.newOutliers, icon: Flame, color: 'text-accent-400', iconBg: 'bg-accent-400/15' },
          { label: 'Avg Multiplier', value: digest.summary.avgMultiplier, icon: Zap, color: 'text-yellow-400', iconBg: 'bg-yellow-400/15' },
          { label: 'Top Niche', value: 'Fitness', icon: TrendingUp, color: 'text-emerald-400', iconBg: 'bg-emerald-400/15' },
          { label: 'Emerging Trends', value: digest.summary.emergingTrends, icon: Sparkles, color: 'text-brand-400', iconBg: 'bg-brand-400/15' },
        ].map(({ label, value, icon: Icon, color, iconBg }) => (
          <div key={label} className="p-4 rounded-xl bg-surface-900 border border-surface-800">
            <div className="flex items-center gap-2 mb-2">
              <div className={`p-1.5 rounded-lg ${iconBg}`}>
                <Icon className={`w-3.5 h-3.5 ${color}`} />
              </div>
              <span className="text-xs text-surface-300">{label}</span>
            </div>
            <div className={`text-2xl font-bold ${color}`}>{value}</div>
          </div>
        ))}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        {/* Hourly Activity */}
        <div className="p-4 rounded-xl bg-surface-900 border border-surface-800">
          <h3 className="text-sm font-semibold text-surface-100 mb-3 flex items-center gap-2">
            <Clock className="w-4 h-4 text-surface-300" />
            Outlier Activity by Hour
          </h3>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={hourlyActivity}>
              <defs>
                <linearGradient id="activityGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b5cff" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#3b5cff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="hour"
                tick={{ fill: '#64748b', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                interval={5}
              />
              <YAxis
                tick={{ fill: '#64748b', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                width={25}
              />
              <Tooltip
                contentStyle={{
                  background: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '8px',
                  fontSize: '12px',
                }}
              />
              <Area
                type="monotone"
                dataKey="outliers"
                stroke="#3b5cff"
                strokeWidth={2}
                fill="url(#activityGradient)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Niche Distribution */}
        <div className="p-4 rounded-xl bg-surface-900 border border-surface-800">
          <h3 className="text-sm font-semibold text-surface-100 mb-3 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-surface-300" />
            Outliers by Niche
          </h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={nicheDistribution} layout="vertical">
              <XAxis type="number" tick={{ fill: '#64748b', fontSize: 10 }} tickLine={false} axisLine={false} />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={60}
              />
              <Tooltip
                contentStyle={{
                  background: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '8px',
                  fontSize: '12px',
                }}
              />
              <Bar dataKey="count" radius={[0, 6, 6, 0]} barSize={20}>
                {nicheDistribution.map((entry, i) => (
                  <Cell key={i} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Trend Alerts */}
      <div className="mb-6">
        <h2 className="text-base font-semibold text-surface-100 mb-4 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-yellow-400" />
          Trend Alerts
        </h2>
        <div className="space-y-3">
          {digest.trendAlerts.map((trend) => (
            <TrendAlert key={trend.id} trend={trend} />
          ))}
        </div>
      </div>

      {/* Top Outliers Preview */}
      <div className="mb-6">
        <h2 className="text-base font-semibold text-surface-100 mb-4 flex items-center gap-2">
          <Flame className="w-4 h-4 text-accent-400" />
          Top Outliers Today
        </h2>
        <div className="space-y-2">
          {digest.topOutliers.map((reel, i) => (
            <div
              key={reel.id}
              className="flex items-center gap-4 p-3 rounded-xl bg-surface-900 border border-surface-800 hover:border-surface-700 transition-colors"
            >
              <div className="w-8 h-8 rounded-lg bg-surface-800 flex items-center justify-center text-sm font-bold text-surface-300">
                {i + 1}
              </div>
              <div
                className="w-12 h-12 rounded-lg flex-shrink-0"
                style={{ background: `linear-gradient(135deg, ${reel.thumbnailColor}, ${reel.thumbnailColor}dd)` }}
              />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-surface-100 truncate">{reel.topic}</div>
                <div className="text-xs text-surface-300">
                  {reel.creator.handle} · {reel.timeAgo}
                </div>
              </div>
              <div className="text-right flex-shrink-0">
                <div className="flex items-center gap-1 text-sm font-bold text-yellow-400">
                  <Zap className="w-3.5 h-3.5" />
                  {reel.multiplier}x
                </div>
                <div className="text-xs text-surface-300 flex items-center gap-1">
                  <Eye className="w-3 h-3" />
                  {formatNumber(reel.views)}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Email Signup CTA */}
      <div className="p-6 rounded-2xl bg-gradient-to-br from-surface-900 to-surface-800 border border-surface-800">
        <div className="flex items-start gap-4">
          <div className="p-3 rounded-xl bg-brand-500/15">
            <Send className="w-5 h-5 text-brand-400" />
          </div>
          <div className="flex-1">
            <h3 className="text-base font-semibold text-surface-100 mb-1">
              Get this digest every morning
            </h3>
            <p className="text-sm text-surface-300 mb-4">
              Receive your personalized outlier report and content briefs at 7:00 AM daily.
            </p>
            <div className="flex gap-2">
              <input
                type="email"
                placeholder="your@email.com"
                className="flex-1 px-4 py-2.5 bg-surface-900 border border-surface-700 rounded-xl text-sm text-surface-100 placeholder:text-surface-300 focus:outline-none focus:border-brand-500 transition-colors"
              />
              <button className="px-5 py-2.5 rounded-xl bg-brand-500 text-white text-sm font-medium hover:bg-brand-600 transition-colors">
                Subscribe
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
