import { useState, useMemo } from 'react'
import {
  Flame, TrendingUp, Eye, Heart, MessageCircle, Share2,
  Bookmark, Clock, ChevronDown, Filter, Zap, X, Play
} from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { generateOutlierReels, formatNumber, niches } from '../data/fakeData'

const lifecycleColors = {
  emerging: { bg: 'bg-emerald-400/15', text: 'text-emerald-400', label: 'Emerging' },
  rising: { bg: 'bg-brand-400/15', text: 'text-brand-400', label: 'Rising' },
  peaking: { bg: 'bg-yellow-400/15', text: 'text-yellow-400', label: 'Peaking' },
  saturated: { bg: 'bg-red-400/15', text: 'text-red-400', label: 'Saturated' },
}

function ReelCard({ reel, onSelect }) {
  const lc = lifecycleColors[reel.lifecycle]

  return (
    <div
      className="bg-surface-900 border border-surface-800 rounded-2xl overflow-hidden hover:border-surface-700 transition-all cursor-pointer group"
      onClick={() => onSelect(reel)}
    >
      {/* Thumbnail */}
      <div
        className="relative h-48 flex items-center justify-center"
        style={{ background: `linear-gradient(135deg, ${reel.thumbnailColor}, ${reel.thumbnailColor}dd)` }}
      >
        <div className="absolute inset-0 bg-black/20" />
        <Play className="w-12 h-12 text-white/70 group-hover:text-white/90 transition-colors drop-shadow-lg" />

        {/* Multiplier Badge */}
        <div className="absolute top-3 left-3 flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-black/60 backdrop-blur-sm">
          <Zap className="w-3.5 h-3.5 text-yellow-400" />
          <span className="text-sm font-bold text-white">{reel.multiplier}x</span>
        </div>

        {/* Lifecycle Badge */}
        <div className={`absolute top-3 right-3 px-2.5 py-1 rounded-lg text-xs font-semibold ${lc.bg} ${lc.text}`}>
          {lc.label}
        </div>

        {/* Time */}
        <div className="absolute bottom-3 right-3 flex items-center gap-1 px-2 py-0.5 rounded-md bg-black/60 text-xs text-white/80">
          <Clock className="w-3 h-3" />
          {reel.timeAgo}
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        {/* Creator */}
        <div className="flex items-center gap-2.5 mb-3">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-400 to-pink-400 flex items-center justify-center text-xs font-bold text-white flex-shrink-0">
            {reel.creator.name.charAt(0)}
          </div>
          <div className="min-w-0">
            <div className="text-sm font-medium text-surface-100 truncate">{reel.creator.name}</div>
            <div className="text-xs text-surface-300">{reel.creator.handle}</div>
          </div>
        </div>

        {/* Topic */}
        <p className="text-sm text-surface-200 mb-3 line-clamp-2 leading-relaxed">
          {reel.topic}
        </p>

        {/* Stats */}
        <div className="grid grid-cols-4 gap-2">
          {[
            { icon: Eye, value: reel.views, label: 'Views' },
            { icon: Heart, value: reel.likes, label: 'Likes' },
            { icon: MessageCircle, value: reel.comments, label: 'Comments' },
            { icon: Bookmark, value: reel.saves, label: 'Saves' },
          ].map(({ icon: Icon, value, label }) => (
            <div key={label} className="text-center">
              <div className="flex items-center justify-center gap-1 text-surface-100">
                <Icon className="w-3 h-3 text-surface-300" />
                <span className="text-xs font-semibold">{formatNumber(value)}</span>
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
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg h-full bg-surface-900 border-l border-surface-800 overflow-y-auto animate-slide-up">
        <div className="sticky top-0 bg-surface-900/90 backdrop-blur-xl border-b border-surface-800 p-4 flex items-center justify-between z-10">
          <h2 className="text-lg font-semibold text-surface-100">Why It's Working</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-surface-800 transition-colors">
            <X className="w-5 h-5 text-surface-300" />
          </button>
        </div>

        <div className="p-5 space-y-6">
          {/* Header */}
          <div>
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-purple-400 to-pink-400 flex items-center justify-center text-sm font-bold text-white">
                {reel.creator.name.charAt(0)}
              </div>
              <div>
                <div className="font-medium text-surface-100">{reel.creator.name}</div>
                <div className="text-sm text-surface-300">{reel.creator.handle}</div>
              </div>
            </div>
            <p className="text-surface-200 mb-3">{reel.topic}</p>
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-yellow-400/15 text-yellow-400 text-sm font-bold">
                <Zap className="w-4 h-4" /> {reel.multiplier}x above baseline
              </span>
              <span className={`px-3 py-1.5 rounded-lg text-sm font-semibold ${lc.bg} ${lc.text}`}>
                {lc.label}
              </span>
            </div>
          </div>

          {/* Engagement Velocity Chart */}
          <div>
            <h3 className="text-sm font-semibold text-surface-100 mb-3 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-brand-400" />
              Engagement Velocity
            </h3>
            <div className="bg-surface-800/50 rounded-xl p-4 border border-surface-800">
              <ResponsiveContainer width="100%" height={160}>
                <AreaChart data={reel.velocityData}>
                  <defs>
                    <linearGradient id="viewsGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b5cff" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#3b5cff" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="hour"
                    tick={{ fill: '#64748b', fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => `${v}h`}
                  />
                  <YAxis
                    tick={{ fill: '#64748b', fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => formatNumber(v)}
                    width={45}
                  />
                  <Tooltip
                    contentStyle={{
                      background: '#1e293b',
                      border: '1px solid #334155',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                    labelFormatter={(v) => `Hour ${v}`}
                    formatter={(v) => [formatNumber(v), 'Views']}
                  />
                  <Area
                    type="monotone"
                    dataKey="views"
                    stroke="#3b5cff"
                    strokeWidth={2}
                    fill="url(#viewsGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Content Breakdown */}
          <div>
            <h3 className="text-sm font-semibold text-surface-100 mb-3 flex items-center gap-2">
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
                  className="flex items-center justify-between p-3 rounded-xl bg-surface-800/50 border border-surface-800"
                >
                  <span className="text-sm text-surface-300">{label}</span>
                  <span className={`text-sm font-medium ${highlight ? 'text-brand-400' : 'text-surface-100'}`}>
                    {value}
                    {trending && (
                      <span className="ml-2 text-xs px-1.5 py-0.5 rounded bg-emerald-400/15 text-emerald-400">
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
            <h3 className="text-sm font-semibold text-surface-100 mb-3">Performance Stats</h3>
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: 'Views', value: formatNumber(reel.views), icon: Eye },
                { label: 'Likes', value: formatNumber(reel.likes), icon: Heart },
                { label: 'Comments', value: formatNumber(reel.comments), icon: MessageCircle },
                { label: 'Shares', value: formatNumber(reel.shares), icon: Share2 },
                { label: 'Saves', value: formatNumber(reel.saves), icon: Bookmark },
                { label: 'Engagement Rate', value: `${((reel.likes + reel.comments + reel.saves) / reel.views * 100).toFixed(1)}%`, icon: TrendingUp },
              ].map(({ label, value, icon: Icon }) => (
                <div key={label} className="p-3 rounded-xl bg-surface-800/50 border border-surface-800">
                  <div className="flex items-center gap-2 mb-1">
                    <Icon className="w-3.5 h-3.5 text-surface-300" />
                    <span className="text-xs text-surface-300">{label}</span>
                  </div>
                  <div className="text-lg font-bold text-surface-100">{value}</div>
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
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2 rounded-xl bg-accent-400/15">
            <Flame className="w-5 h-5 text-accent-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-surface-100">Outlier Feed</h1>
            <p className="text-sm text-surface-300">
              Reels outperforming their creator's baseline right now
            </p>
          </div>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        {[
          { label: 'Outliers Detected', value: filteredReels.length, color: 'text-brand-400' },
          { label: 'Avg Multiplier', value: `${(filteredReels.reduce((a, r) => a + r.multiplier, 0) / filteredReels.length).toFixed(1)}x`, color: 'text-yellow-400' },
          { label: 'Emerging Trends', value: filteredReels.filter((r) => r.lifecycle === 'emerging').length, color: 'text-emerald-400' },
          { label: 'Peaking Now', value: filteredReels.filter((r) => r.lifecycle === 'peaking').length, color: 'text-accent-400' },
        ].map(({ label, value, color }) => (
          <div key={label} className="p-3 rounded-xl bg-surface-900 border border-surface-800">
            <div className="text-xs text-surface-300 mb-1">{label}</div>
            <div className={`text-xl font-bold ${color}`}>{value}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 mb-6">
        <div className="flex items-center gap-1.5 mr-2">
          <Filter className="w-4 h-4 text-surface-300" />
          <span className="text-sm text-surface-300">Filter:</span>
        </div>
        {['all', 'emerging', 'rising', 'peaking', 'saturated'].map((f) => (
          <button
            key={f}
            onClick={() => setFilterLifecycle(f)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              filterLifecycle === f
                ? 'bg-brand-500/15 text-brand-400 border border-brand-500/30'
                : 'bg-surface-800 text-surface-300 border border-surface-800 hover:border-surface-700'
            }`}
          >
            {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}

        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-surface-300">Sort:</span>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="bg-surface-800 border border-surface-800 text-surface-100 text-xs rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-brand-500"
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
          <div className="text-surface-300 mb-2">No outliers match this filter.</div>
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
