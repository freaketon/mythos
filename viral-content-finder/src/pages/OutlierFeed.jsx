import { useState, useMemo } from 'react'
import {
  Flame, TrendingUp, Eye, Heart, MessageCircle, Share2,
  Bookmark, Clock, Filter, Zap, X, Play
} from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { generateOutlierReels, formatNumber } from '../data/fakeData'

const lifecycleColors = {
  emerging: { bg: 'bg-brand-500/12', text: 'text-brand-400', label: 'Emerging', dot: 'bg-brand-500' },
  rising: { bg: 'bg-accent-500/12', text: 'text-accent-400', label: 'Rising', dot: 'bg-accent-500' },
  peaking: { bg: 'bg-yellow-400/12', text: 'text-yellow-400', label: 'Peaking', dot: 'bg-yellow-400' },
  saturated: { bg: 'bg-red-400/12', text: 'text-red-400', label: 'Saturated', dot: 'bg-red-400' },
}

function ReelCard({ reel, onSelect }) {
  const lc = lifecycleColors[reel.lifecycle]

  return (
    <div
      className="glass-card rounded-2xl overflow-hidden hover:border-brand-500/20 transition-all duration-300 cursor-pointer group hover:shadow-[0_0_30px_rgba(0,232,123,0.06)]"
      onClick={() => onSelect(reel)}
    >
      {/* Thumbnail */}
      <div
        className="relative h-52 flex items-center justify-center overflow-hidden"
        style={{ background: `linear-gradient(135deg, ${reel.thumbnailColor}, ${reel.thumbnailColor}cc)` }}
      >
        <div className="absolute inset-0 bg-black/30 group-hover:bg-black/20 transition-colors duration-300" />
        <div className="w-14 h-14 rounded-full bg-white/10 backdrop-blur-sm flex items-center justify-center group-hover:scale-110 transition-transform duration-300">
          <Play className="w-6 h-6 text-white/90 ml-0.5" />
        </div>

        {/* Multiplier Badge */}
        <div className="absolute top-3 left-3 flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-black/50 backdrop-blur-md border border-white/10">
          <Zap className="w-3.5 h-3.5 text-brand-400" />
          <span className="text-sm font-bold text-white">{reel.multiplier}x</span>
        </div>

        {/* Lifecycle Badge */}
        <div className={`absolute top-3 right-3 px-2.5 py-1.5 rounded-xl text-xs font-semibold backdrop-blur-md ${lc.bg} ${lc.text} border border-white/5`}>
          {lc.label}
        </div>

        {/* Time */}
        <div className="absolute bottom-3 right-3 flex items-center gap-1 px-2.5 py-1 rounded-lg bg-black/50 backdrop-blur-md text-xs text-white/80 border border-white/5">
          <Clock className="w-3 h-3" />
          {reel.timeAgo}
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        {/* Creator */}
        <div className="flex items-center gap-2.5 mb-3">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-accent-400 to-brand-500 flex items-center justify-center text-xs font-bold text-white flex-shrink-0">
            {reel.creator.name.charAt(0)}
          </div>
          <div className="min-w-0">
            <div className="text-sm font-medium text-surface-100 truncate">{reel.creator.name}</div>
            <div className="text-xs text-surface-400">{reel.creator.handle}</div>
          </div>
        </div>

        {/* Topic */}
        <p className="text-sm text-surface-200 mb-4 line-clamp-2 leading-relaxed">
          {reel.topic}
        </p>

        {/* Stats */}
        <div className="grid grid-cols-4 gap-2 pt-3 border-t border-surface-800/50">
          {[
            { icon: Eye, value: reel.views },
            { icon: Heart, value: reel.likes },
            { icon: MessageCircle, value: reel.comments },
            { icon: Bookmark, value: reel.saves },
          ].map(({ icon: Icon, value }, i) => (
            <div key={i} className="text-center">
              <div className="flex items-center justify-center gap-1 text-surface-200">
                <Icon className="w-3 h-3 text-surface-400" />
                <span className="text-xs font-medium">{formatNumber(value)}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function BreakdownPanel({ reel, onClose }) {
  if (!reel) return null
  const lc = lifecycleColors[reel.lifecycle]
  const b = reel.breakdown

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-end">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg h-full bg-surface-900 border-l border-surface-800/50 overflow-y-auto animate-slide-up">
        <div className="sticky top-0 bg-surface-900/90 backdrop-blur-xl border-b border-surface-800/50 p-5 flex items-center justify-between z-10">
          <h2 className="text-lg font-bold text-white" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            Why It's Working
          </h2>
          <button onClick={onClose} className="p-2 rounded-xl hover:bg-surface-800/50 transition-colors">
            <X className="w-5 h-5 text-surface-300" />
          </button>
        </div>

        <div className="p-5 space-y-6">
          {/* Header */}
          <div>
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-accent-400 to-brand-500 flex items-center justify-center text-sm font-bold text-white">
                {reel.creator.name.charAt(0)}
              </div>
              <div>
                <div className="font-medium text-surface-100">{reel.creator.name}</div>
                <div className="text-sm text-surface-400">{reel.creator.handle}</div>
              </div>
            </div>
            <p className="text-surface-200 mb-4">{reel.topic}</p>
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-brand-500/12 text-brand-400 text-sm font-bold border border-brand-500/20">
                <Zap className="w-4 h-4" /> {reel.multiplier}x above baseline
              </span>
              <span className={`px-3 py-1.5 rounded-xl text-sm font-semibold ${lc.bg} ${lc.text} border border-white/5`}>
                {lc.label}
              </span>
            </div>
          </div>

          {/* Engagement Velocity Chart */}
          <div>
            <h3 className="text-sm font-semibold text-surface-100 mb-3 flex items-center gap-2" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              <TrendingUp className="w-4 h-4 text-brand-400" />
              Engagement Velocity
            </h3>
            <div className="glass-card rounded-2xl p-4">
              <ResponsiveContainer width="100%" height={160}>
                <AreaChart data={reel.velocityData}>
                  <defs>
                    <linearGradient id="viewsGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#00E87B" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#00E87B" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="hour"
                    tick={{ fill: '#6e7681', fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => `${v}h`}
                  />
                  <YAxis
                    tick={{ fill: '#6e7681', fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => formatNumber(v)}
                    width={45}
                  />
                  <Tooltip
                    contentStyle={{
                      background: '#141b27',
                      border: '1px solid rgba(0,232,123,0.15)',
                      borderRadius: '12px',
                      fontSize: '12px',
                      boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
                    }}
                    labelFormatter={(v) => `Hour ${v}`}
                    formatter={(v) => [formatNumber(v), 'Views']}
                  />
                  <Area
                    type="monotone"
                    dataKey="views"
                    stroke="#00E87B"
                    strokeWidth={2}
                    fill="url(#viewsGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Content Breakdown */}
          <div>
            <h3 className="text-sm font-semibold text-surface-100 mb-3 flex items-center gap-2" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              <Flame className="w-4 h-4 text-accent-400" />
              Content Breakdown
            </h3>
            <div className="space-y-2">
              {[
                { label: 'Hook Type', value: b.hookType, highlight: true },
                { label: 'Content Format', value: b.contentFormat },
                { label: 'Audio', value: b.audio.name, trending: b.audio.trending },
                { label: 'Duration', value: `${b.duration} seconds` },
                { label: 'Text Overlays', value: `${b.textOverlays} overlays used` },
                { label: 'CTA Style', value: b.ctaStyle },
                { label: 'Posted At', value: `${b.postingHour}:00` },
              ].map(({ label, value, highlight, trending }) => (
                <div
                  key={label}
                  className="flex items-center justify-between p-3 rounded-xl bg-surface-800/40 border border-surface-700/30"
                >
                  <span className="text-sm text-surface-400">{label}</span>
                  <span className={`text-sm font-medium ${highlight ? 'text-brand-400' : 'text-surface-100'}`}>
                    {value}
                    {trending && (
                      <span className="ml-2 text-xs px-1.5 py-0.5 rounded-md bg-brand-500/12 text-brand-400 border border-brand-500/20">
                        trending
                      </span>
                    )}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Key Stats */}
          <div>
            <h3 className="text-sm font-semibold text-surface-100 mb-3" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Performance Stats
            </h3>
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: 'Views', value: formatNumber(reel.views), icon: Eye, color: 'text-brand-400' },
                { label: 'Likes', value: formatNumber(reel.likes), icon: Heart, color: 'text-pink-400' },
                { label: 'Comments', value: formatNumber(reel.comments), icon: MessageCircle, color: 'text-accent-400' },
                { label: 'Shares', value: formatNumber(reel.shares), icon: Share2, color: 'text-yellow-400' },
                { label: 'Saves', value: formatNumber(reel.saves), icon: Bookmark, color: 'text-purple-400' },
                { label: 'Engagement', value: `${((reel.likes + reel.comments + reel.saves) / reel.views * 100).toFixed(1)}%`, icon: TrendingUp, color: 'text-brand-400' },
              ].map(({ label, value, icon: Icon, color }) => (
                <div key={label} className="p-3.5 rounded-xl bg-surface-800/40 border border-surface-700/30">
                  <div className="flex items-center gap-2 mb-1.5">
                    <Icon className={`w-3.5 h-3.5 ${color}`} />
                    <span className="text-xs text-surface-400">{label}</span>
                  </div>
                  <div className="text-xl font-bold text-surface-100">{value}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function OutlierFeed({ userConfig }) {
  const reels = useMemo(() => generateOutlierReels(24), [])
  const [selectedReel, setSelectedReel] = useState(null)
  const [filterLifecycle, setFilterLifecycle] = useState('all')
  const [sortBy, setSortBy] = useState('multiplier')

  const filteredReels = useMemo(() => {
    let result = [...reels]
    if (filterLifecycle !== 'all') {
      result = result.filter((r) => r.lifecycle === filterLifecycle)
    }
    if (sortBy === 'multiplier') result.sort((a, b) => b.multiplier - a.multiplier)
    else if (sortBy === 'views') result.sort((a, b) => b.views - a.views)
    else if (sortBy === 'recent') result.sort((a, b) => a.hoursAgo - b.hoursAgo)
    return result
  }, [reels, filterLifecycle, sortBy])

  return (
    <div>
      {/* Page Header */}
      <div className="mb-8">
        <div className="flex items-center gap-4 mb-2">
          <div className="p-2.5 rounded-2xl bg-brand-500/10 border border-brand-500/20">
            <Flame className="w-6 h-6 text-brand-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Outlier Feed
            </h1>
            <p className="text-sm text-surface-300">
              Reels outperforming their creator's baseline right now
            </p>
          </div>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
        {[
          { label: 'Outliers Detected', value: filteredReels.length, color: 'text-brand-400' },
          { label: 'Avg Multiplier', value: `${(filteredReels.reduce((a, r) => a + r.multiplier, 0) / filteredReels.length).toFixed(1)}x`, color: 'text-yellow-400' },
          { label: 'Emerging Trends', value: filteredReels.filter((r) => r.lifecycle === 'emerging').length, color: 'text-accent-400' },
          { label: 'Peaking Now', value: filteredReels.filter((r) => r.lifecycle === 'peaking').length, color: 'text-pink-400' },
        ].map(({ label, value, color }) => (
          <div key={label} className="glass-card p-4 rounded-2xl">
            <div className="text-xs text-surface-400 mb-1.5">{label}</div>
            <div className={`text-2xl font-bold ${color}`}>{value}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 mb-8">
        <div className="flex items-center gap-1.5 mr-2">
          <Filter className="w-4 h-4 text-surface-400" />
          <span className="text-sm text-surface-400">Filter:</span>
        </div>
        {['all', 'emerging', 'rising', 'peaking', 'saturated'].map((f) => {
          const active = filterLifecycle === f
          return (
            <button
              key={f}
              onClick={() => setFilterLifecycle(f)}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-medium transition-all duration-200 border ${
                active
                  ? 'bg-brand-500/12 text-brand-400 border-brand-500/30 shadow-[0_0_8px_rgba(0,232,123,0.1)]'
                  : 'bg-surface-800/40 text-surface-300 border-surface-700/30 hover:border-surface-700'
              }`}
            >
              {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          )
        })}

        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-surface-400">Sort:</span>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="bg-surface-800/40 border border-surface-700/30 text-surface-100 text-xs rounded-xl px-3 py-1.5 focus:outline-none focus:border-brand-500/50 transition-colors"
          >
            <option value="multiplier">Highest Multiplier</option>
            <option value="views">Most Views</option>
            <option value="recent">Most Recent</option>
          </select>
        </div>
      </div>

      {/* Reel Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredReels.map((reel) => (
          <ReelCard key={reel.id} reel={reel} onSelect={setSelectedReel} />
        ))}
      </div>

      {filteredReels.length === 0 && (
        <div className="text-center py-16">
          <div className="text-surface-400 mb-2">No outliers match this filter.</div>
          <button
            onClick={() => setFilterLifecycle('all')}
            className="text-brand-400 text-sm hover:underline"
          >
            Clear filters
          </button>
        </div>
      )}

      {/* Breakdown Panel */}
      <BreakdownPanel reel={selectedReel} onClose={() => setSelectedReel(null)} />
    </div>
  )
}
