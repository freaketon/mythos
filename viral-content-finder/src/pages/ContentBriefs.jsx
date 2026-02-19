import { useState, useMemo } from 'react'
import {
  FileText, Sparkles, Clock, Target, Music, Video,
  ChevronRight, CheckCircle, Lightbulb, TrendingUp,
  RefreshCw, Copy, Check
} from 'lucide-react'
import { generateContentBriefs } from '../data/fakeData'

const lifecycleColors = {
  emerging: { bg: 'bg-brand-400/12', text: 'text-brand-400', label: 'Emerging' },
  peaking: { bg: 'bg-yellow-400/12', text: 'text-yellow-400', label: 'Peaking' },
  rising: { bg: 'bg-accent-500/12', text: 'text-accent-400', label: 'Rising' },
  saturated: { bg: 'bg-red-400/12', text: 'text-red-400', label: 'Saturated' },
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

  /* Rotate through game-card gradients for the brief number */
  const numGradients = ['bg-card-green', 'bg-showcase-card', 'bg-game-amber']
  const numBg = numGradients[index % numGradients.length]

  return (
    <div
      className={`glass-card rounded-2xl overflow-hidden transition-all duration-300 ${
        expanded ? 'border-brand-400/25 shadow-[0_0_30px_rgba(63,169,110,0.06)]' : 'hover:border-white/[0.08]'
      }`}
    >
      {/* Header */}
      <div className="p-5 cursor-pointer" onClick={onToggle}>
        <div className="flex items-start gap-4">
          <div className={`w-11 h-11 rounded-2xl ${numBg} flex items-center justify-center text-white font-bold text-lg flex-shrink-0 shadow-lg`}>
            {index + 1}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-2">
              <h3 className="text-base font-semibold text-cream">
                {brief.title}
              </h3>
              <span className={`px-2 py-0.5 rounded-lg text-xs font-semibold ${lc.bg} ${lc.text} border border-white/5`}>
                {lc.label}
              </span>
            </div>
            <p className="text-sm text-cream-muted leading-relaxed" style={{ fontFamily: "'DM Sans', sans-serif" }}>{brief.hook}</p>

            <div className="flex items-center gap-4 mt-3">
              <span className="flex items-center gap-1.5 text-xs text-cream-muted">
                <Target className="w-3.5 h-3.5 text-brand-400" />
                {brief.confidence}% confidence
              </span>
              <span className="flex items-center gap-1.5 text-xs text-cream-muted">
                <TrendingUp className="w-3.5 h-3.5 text-accent-400" />
                {brief.estimatedReach}
              </span>
              <span className="flex items-center gap-1.5 text-xs text-cream-muted">
                <Sparkles className="w-3.5 h-3.5 text-yellow-400" />
                Based on {brief.basedOn} outliers
              </span>
            </div>
          </div>
          <ChevronRight
            className={`w-5 h-5 text-cream-muted transition-transform duration-300 flex-shrink-0 ${expanded ? 'rotate-90' : ''}`}
          />
        </div>
      </div>

      {/* Expanded Details */}
      {expanded && (
        <div className="px-5 pb-5 border-t border-white/[0.06]">
          <div className="pt-5 space-y-5">
            {/* Format & Audio */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {[
                { icon: Video, color: 'text-accent-400', label: 'Format', value: brief.format },
                { icon: Music, color: 'text-pink-400', label: 'Audio', value: brief.audio },
                { icon: Clock, color: 'text-teal-400', label: 'Duration', value: brief.duration },
              ].map(({ icon: Icon, color, label, value }) => (
                <div key={label} className="p-3.5 rounded-xl bg-surface-800/40 border border-white/[0.04]">
                  <div className="flex items-center gap-2 mb-1.5">
                    <Icon className={`w-3.5 h-3.5 ${color}`} />
                    <span className="text-xs text-cream-muted">{label}</span>
                  </div>
                  <div className="text-sm font-medium text-cream">{value}</div>
                </div>
              ))}
            </div>

            {/* Key Points — beige section style */}
            <div className="p-4 rounded-2xl bg-beige/5 border border-beige/10">
              <h4 className="text-sm font-semibold text-cream mb-3 flex items-center gap-2">
                <Lightbulb className="w-4 h-4 text-yellow-400" />
                Shooting Notes
              </h4>
              <div className="space-y-2">
                {brief.keyPoints.map((point, i) => (
                  <div key={i} className="flex items-start gap-3 p-3 rounded-xl bg-surface-800/30 border border-white/[0.04]">
                    <CheckCircle className="w-4 h-4 text-brand-400 mt-0.5 flex-shrink-0" />
                    <span className="text-sm text-cream/80" style={{ fontFamily: "'DM Sans', sans-serif" }}>{point}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={handleCopy}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-cta-amber text-surface-900 text-sm font-bold hover:shadow-[0_0_20px_rgba(245,197,66,0.25)] transition-all duration-200"
              >
                {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                {copied ? 'Copied!' : 'Copy Brief'}
              </button>
              <button className="flex items-center gap-2 px-5 py-2.5 rounded-xl border border-white/[0.08] text-cream-muted text-sm font-medium hover:bg-white/[0.04] transition-all duration-200">
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
      <div className="mb-8">
        <div className="flex items-center gap-4 mb-2">
          <div className="p-2.5 rounded-2xl bg-showcase-card">
            <FileText className="w-6 h-6 text-cream" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-cream">
              Content Briefs
            </h1>
            <p className="text-sm text-cream-muted" style={{ fontFamily: "'DM Sans', sans-serif" }}>
              AI-generated briefs based on today's top outlier patterns
            </p>
          </div>
        </div>
      </div>

      {/* Context Banner — rewards pink style with lavender blob */}
      <div className="p-4 rounded-2xl bg-rewards-pink mb-8 relative overflow-hidden">
        <div className="relative z-10 flex items-start gap-3">
          <Sparkles className="w-5 h-5 text-accent-600 mt-0.5 flex-shrink-0" />
          <div>
            <div className="text-sm font-medium text-surface-900 mb-1">
              Fresh briefs generated from 23 outlier Reels detected in the last 24 hours
            </div>
            <div className="text-xs text-surface-500">
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

      {/* Generate More — amber CTA */}
      <div className="mt-8 text-center">
        <button className="inline-flex items-center gap-2 px-8 py-3 rounded-2xl bg-cta-amber text-surface-900 font-bold hover:shadow-[0_0_20px_rgba(245,197,66,0.25)] transition-all duration-200">
          <RefreshCw className="w-4 h-4" />
          Generate 3 More Briefs
        </button>
      </div>
    </div>
  )
}
