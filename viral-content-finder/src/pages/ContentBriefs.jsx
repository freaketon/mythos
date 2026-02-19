import { useState, useMemo } from 'react'
import {
  FileText, Sparkles, Clock, Target, Music, Video,
  ChevronRight, CheckCircle, Lightbulb, TrendingUp,
  RefreshCw, Copy, Check
} from 'lucide-react'
import { generateContentBriefs } from '../data/fakeData'

const lifecycleColors = {
  emerging: { bg: 'bg-emerald-400/15', text: 'text-emerald-400', label: 'Emerging' },
  peaking: { bg: 'bg-yellow-400/15', text: 'text-yellow-400', label: 'Peaking' },
  rising: { bg: 'bg-brand-400/15', text: 'text-brand-400', label: 'Rising' },
  saturated: { bg: 'bg-red-400/15', text: 'text-red-400', label: 'Saturated' },
}

function BriefCard({ brief, index, expanded, onToggle }) {
  const [copied, setCopied] = useState(false)
  const lc = lifecycleColors[brief.trendLifecycle]

  const handleCopy = (e) => {
    e.stopPropagation()
    const text = `${brief.title}\n\nHook: ${brief.hook}\nFormat: ${brief.format}\nAudio: ${brief.audio}\nDuration: ${brief.duration}\n\nKey Points:\n${brief.keyPoints.map((p) => `- ${p}`).join('\n')}`
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div
      className={`bg-surface-900 border rounded-2xl overflow-hidden transition-all ${
        expanded ? 'border-brand-500/30 shadow-lg shadow-brand-500/5' : 'border-surface-800 hover:border-surface-700'
      }`}
    >
      {/* Header */}
      <div
        className="p-5 cursor-pointer"
        onClick={onToggle}
      >
        <div className="flex items-start gap-4">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500 to-purple-500 flex items-center justify-center text-white font-bold text-lg flex-shrink-0">
            {index + 1}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-2">
              <h3 className="text-base font-semibold text-surface-100">{brief.title}</h3>
              <span className={`px-2 py-0.5 rounded-md text-xs font-semibold ${lc.bg} ${lc.text}`}>
                {lc.label}
              </span>
            </div>
            <p className="text-sm text-surface-300 leading-relaxed">{brief.hook}</p>

            <div className="flex items-center gap-4 mt-3">
              <span className="flex items-center gap-1.5 text-xs text-surface-300">
                <Target className="w-3.5 h-3.5 text-brand-400" />
                {brief.confidence}% confidence
              </span>
              <span className="flex items-center gap-1.5 text-xs text-surface-300">
                <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
                {brief.estimatedReach}
              </span>
              <span className="flex items-center gap-1.5 text-xs text-surface-300">
                <Sparkles className="w-3.5 h-3.5 text-yellow-400" />
                Based on {brief.basedOn} outliers
              </span>
            </div>
          </div>
          <ChevronRight
            className={`w-5 h-5 text-surface-300 transition-transform flex-shrink-0 ${expanded ? 'rotate-90' : ''}`}
          />
        </div>
      </div>

      {/* Expanded Details */}
      {expanded && (
        <div className="px-5 pb-5 border-t border-surface-800">
          <div className="pt-4 space-y-4">
            {/* Format & Audio */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="p-3 rounded-xl bg-surface-800/50 border border-surface-800">
                <div className="flex items-center gap-2 mb-1.5">
                  <Video className="w-3.5 h-3.5 text-purple-400" />
                  <span className="text-xs text-surface-300">Format</span>
                </div>
                <div className="text-sm font-medium text-surface-100">{brief.format}</div>
              </div>
              <div className="p-3 rounded-xl bg-surface-800/50 border border-surface-800">
                <div className="flex items-center gap-2 mb-1.5">
                  <Music className="w-3.5 h-3.5 text-pink-400" />
                  <span className="text-xs text-surface-300">Audio</span>
                </div>
                <div className="text-sm font-medium text-surface-100">{brief.audio}</div>
              </div>
              <div className="p-3 rounded-xl bg-surface-800/50 border border-surface-800">
                <div className="flex items-center gap-2 mb-1.5">
                  <Clock className="w-3.5 h-3.5 text-brand-400" />
                  <span className="text-xs text-surface-300">Duration</span>
                </div>
                <div className="text-sm font-medium text-surface-100">{brief.duration}</div>
              </div>
            </div>

            {/* Key Points */}
            <div>
              <h4 className="text-sm font-semibold text-surface-100 mb-3 flex items-center gap-2">
                <Lightbulb className="w-4 h-4 text-yellow-400" />
                Shooting Notes
              </h4>
              <div className="space-y-2">
                {brief.keyPoints.map((point, i) => (
                  <div key={i} className="flex items-start gap-3 p-3 rounded-xl bg-surface-800/30">
                    <CheckCircle className="w-4 h-4 text-emerald-400 mt-0.5 flex-shrink-0" />
                    <span className="text-sm text-surface-200">{point}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={handleCopy}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-brand-500 text-white text-sm font-medium hover:bg-brand-600 transition-colors"
              >
                {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                {copied ? 'Copied!' : 'Copy Brief'}
              </button>
              <button className="flex items-center gap-2 px-4 py-2 rounded-xl border border-surface-700 text-surface-300 text-sm font-medium hover:bg-surface-800 transition-colors">
                <RefreshCw className="w-4 h-4" />
                Regenerate
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function ContentBriefs({ userConfig }) {
  const briefs = useMemo(() => generateContentBriefs(userConfig?.niches), [userConfig])
  const [expandedId, setExpandedId] = useState(briefs[0]?.id)

  return (
    <div>
      {/* Page Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2 rounded-xl bg-brand-500/15">
            <FileText className="w-5 h-5 text-brand-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-surface-100">Content Briefs</h1>
            <p className="text-sm text-surface-300">
              AI-generated briefs based on today's top outlier patterns
            </p>
          </div>
        </div>
      </div>

      {/* Context Banner */}
      <div className="p-4 rounded-xl bg-gradient-to-r from-brand-500/10 to-purple-500/10 border border-brand-500/20 mb-6">
        <div className="flex items-start gap-3">
          <Sparkles className="w-5 h-5 text-brand-400 mt-0.5 flex-shrink-0" />
          <div>
            <div className="text-sm font-medium text-surface-100 mb-1">
              Fresh briefs generated from 23 outlier Reels detected in the last 24 hours
            </div>
            <div className="text-xs text-surface-300">
              Updated 12 minutes ago. Briefs are tailored to your selected niches and current trends.
            </div>
          </div>
        </div>
      </div>

      {/* Briefs */}
      <div className="space-y-4">
        {briefs.map((brief, i) => (
          <BriefCard
            key={brief.id}
            brief={brief}
            index={i}
            expanded={expandedId === brief.id}
            onToggle={() => setExpandedId(expandedId === brief.id ? null : brief.id)}
          />
        ))}
      </div>

      {/* Generate More */}
      <div className="mt-6 text-center">
        <button className="inline-flex items-center gap-2 px-6 py-3 rounded-xl border border-surface-700 text-surface-300 font-medium hover:bg-surface-800 transition-colors">
          <RefreshCw className="w-4 h-4" />
          Generate 3 More Briefs
        </button>
      </div>
    </div>
  )
}
