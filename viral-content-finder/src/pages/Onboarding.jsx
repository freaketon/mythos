import { useState } from 'react'
import { Zap, Search, ArrowRight, Check, Sparkles, TrendingUp } from 'lucide-react'
import { niches, competitors } from '../data/fakeData'

export default function Onboarding({ onComplete }) {
  const [step, setStep] = useState(0)
  const [selectedNiches, setSelectedNiches] = useState([])
  const [selectedCompetitors, setSelectedCompetitors] = useState([])
  const [searchQuery, setSearchQuery] = useState('')

  const toggleNiche = (id) => {
    setSelectedNiches((prev) =>
      prev.includes(id) ? prev.filter((n) => n !== id) : [...prev, id]
    )
  }

  const toggleCompetitor = (id) => {
    setSelectedCompetitors((prev) =>
      prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id]
    )
  }

  const filteredCompetitors = competitors.filter(
    (c) =>
      selectedNiches.includes(c.niche) &&
      (searchQuery === '' ||
        c.handle.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.name.toLowerCase().includes(searchQuery.toLowerCase()))
  )

  const handleComplete = () => {
    onComplete({
      niches: selectedNiches,
      competitors: selectedCompetitors,
    })
  }

  return (
    <div className="min-h-screen bg-hero-glow flex items-center justify-center p-4">
      {/* Ambient glow effects */}
      <div className="fixed top-[-10%] left-1/3 w-[500px] h-[500px] bg-accent-500/10 rounded-full blur-[150px] pointer-events-none" />
      <div className="fixed bottom-[-5%] right-1/4 w-80 h-80 bg-brand-400/8 rounded-full blur-[120px] pointer-events-none" />

      <div className="w-full max-w-2xl relative z-10">
        {/* Logo */}
        <div className="text-center mb-10 animate-slide-up">
          <div className="inline-flex items-center gap-4 mb-6">
            <div className="w-14 h-14 rounded-2xl bg-card-green flex items-center justify-center shadow-lg shadow-brand-500/25 animate-pulse-glow">
              <Zap className="w-8 h-8 text-cream" />
            </div>
            <div className="text-left">
              <h1 className="text-3xl font-bold tracking-tight">
                <span className="text-gradient-cream">TURBO</span>
                <span className="text-cream-muted mx-2 font-light">|</span>
                <span className="text-cream">Viral Finder</span>
              </h1>
            </div>
          </div>
          <p className="text-cream-muted text-base max-w-md mx-auto leading-relaxed">
            Find viral content before it peaks. Get AI-powered briefs for what to post next.
          </p>
        </div>

        {/* Progress */}
        <div className="flex items-center gap-3 mb-10 justify-center">
          {[0, 1, 2].map((s) => (
            <div
              key={s}
              className={`h-1 rounded-full transition-all duration-700 ${
                s <= step
                  ? 'w-20 bg-showcase-card shadow-[0_0_8px_rgba(168,85,247,0.3)]'
                  : 'w-10 bg-surface-700'
              }`}
            />
          ))}
        </div>

        {/* Step 0: Pick Niches */}
        {step === 0 && (
          <div className="animate-slide-up">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold text-cream mb-2">
                What niches do you create in?
              </h2>
              <p className="text-cream-muted text-sm">Select 1-5 niches to track. You can change these later.</p>
            </div>
            <div className="grid grid-cols-2 gap-3 mb-8">
              {niches.map((niche) => {
                const selected = selectedNiches.includes(niche.id)
                return (
                  <button
                    key={niche.id}
                    onClick={() => toggleNiche(niche.id)}
                    className={`flex items-center gap-3 p-4 rounded-2xl border transition-all duration-200 text-left group ${
                      selected
                        ? 'border-brand-400/40 bg-brand-400/8 shadow-[0_0_20px_rgba(63,169,110,0.08)]'
                        : 'border-white/[0.06] bg-surface-800/50 hover:border-white/[0.12] hover:bg-surface-800/80'
                    }`}
                  >
                    <span className="text-2xl">{niche.emoji}</span>
                    <div className="flex-1">
                      <div className={`font-medium text-sm ${selected ? 'text-brand-300' : 'text-cream'}`}>
                        {niche.label}
                      </div>
                    </div>
                    {selected && (
                      <div className="w-5 h-5 rounded-full bg-brand-400 flex items-center justify-center shadow-[0_0_8px_rgba(63,169,110,0.4)]">
                        <Check className="w-3 h-3 text-white" />
                      </div>
                    )}
                  </button>
                )
              })}
            </div>
            <button
              onClick={() => setStep(1)}
              disabled={selectedNiches.length === 0}
              className="w-full flex items-center justify-center gap-2 py-3.5 rounded-2xl bg-cta-amber text-surface-900 font-bold transition-all duration-200 hover:shadow-[0_0_24px_rgba(245,197,66,0.3)] disabled:opacity-30 disabled:cursor-not-allowed disabled:shadow-none"
            >
              Continue
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Step 1: Pick Competitors */}
        {step === 1 && (
          <div className="animate-slide-up">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold text-cream mb-2">
                Pick accounts to watch
              </h2>
              <p className="text-cream-muted text-sm">
                We'll track these creators to detect outlier content in your niche.
              </p>
            </div>

            <div className="relative mb-4">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-cream-muted" />
              <input
                type="text"
                placeholder="Search accounts..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-11 pr-4 py-3 bg-surface-800/60 border border-white/[0.06] rounded-2xl text-sm text-cream placeholder:text-cream-muted focus:outline-none focus:border-accent-500/50 focus:shadow-[0_0_12px_rgba(168,85,247,0.1)] transition-all duration-200"
              />
            </div>

            <div className="space-y-2 max-h-80 overflow-y-auto mb-6 pr-1">
              {filteredCompetitors.map((comp) => {
                const selected = selectedCompetitors.includes(comp.id)
                return (
                  <button
                    key={comp.id}
                    onClick={() => toggleCompetitor(comp.id)}
                    className={`w-full flex items-center gap-3 p-3.5 rounded-2xl border transition-all duration-200 text-left ${
                      selected
                        ? 'border-brand-400/40 bg-brand-400/8'
                        : 'border-white/[0.06] bg-surface-800/50 hover:border-white/[0.12]'
                    }`}
                  >
                    <div className="w-10 h-10 rounded-full bg-showcase-card flex items-center justify-center text-sm font-bold text-cream">
                      {comp.name.charAt(0)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-sm text-cream truncate">{comp.name}</div>
                      <div className="text-xs text-cream-muted">{comp.handle} · {(comp.followers / 1000).toFixed(0)}K followers</div>
                    </div>
                    {selected && (
                      <div className="w-5 h-5 rounded-full bg-brand-400 flex items-center justify-center flex-shrink-0 shadow-[0_0_8px_rgba(63,169,110,0.4)]">
                        <Check className="w-3 h-3 text-white" />
                      </div>
                    )}
                  </button>
                )
              })}
              {filteredCompetitors.length === 0 && (
                <div className="text-center py-8 text-cream-muted text-sm">
                  No accounts found in selected niches.
                </div>
              )}
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setStep(0)}
                className="px-6 py-3.5 rounded-2xl border border-white/[0.08] text-cream-muted font-medium hover:bg-white/[0.04] transition-all duration-200"
              >
                Back
              </button>
              <button
                onClick={() => setStep(2)}
                disabled={selectedCompetitors.length === 0}
                className="flex-1 flex items-center justify-center gap-2 py-3.5 rounded-2xl bg-cta-amber text-surface-900 font-bold transition-all duration-200 hover:shadow-[0_0_24px_rgba(245,197,66,0.3)] disabled:opacity-30 disabled:cursor-not-allowed disabled:shadow-none"
              >
                Continue
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Scanning Animation */}
        {step === 2 && (
          <div className="animate-slide-up text-center">
            <div className="relative inline-block mb-10">
              <div className="w-28 h-28 rounded-3xl bg-showcase-card flex items-center justify-center animate-pulse-glow-purple">
                <Sparkles className="w-14 h-14 text-cream" />
              </div>
              <div className="absolute inset-[-8px] rounded-[28px] border border-accent-500/20 animate-spin" style={{ animationDuration: '8s' }} />
            </div>

            <h2 className="text-2xl font-bold text-cream mb-3">
              Scanning your niches...
            </h2>
            <p className="text-cream-muted text-base mb-10 max-w-sm mx-auto leading-relaxed">
              Our AI is analyzing thousands of Reels across your selected niches to find outliers.
            </p>

            <div className="space-y-3 max-w-sm mx-auto mb-10 text-left">
              {[
                { label: 'Analyzing engagement velocity patterns', done: true },
                { label: 'Detecting statistical outliers', done: true },
                { label: 'Decomposing content patterns', done: true },
                { label: 'Generating personalized briefs', done: false },
              ].map((item, i) => (
                <div
                  key={i}
                  className="flex items-center gap-3 text-sm"
                  style={{ animationDelay: `${i * 200}ms` }}
                >
                  {item.done ? (
                    <div className="w-6 h-6 rounded-full bg-brand-400/20 flex items-center justify-center">
                      <Check className="w-3.5 h-3.5 text-brand-400" />
                    </div>
                  ) : (
                    <div className="w-6 h-6 rounded-full border-2 border-accent-500 border-t-transparent animate-spin" />
                  )}
                  <span className={item.done ? 'text-cream' : 'text-cream-muted'}>
                    {item.label}
                  </span>
                </div>
              ))}
            </div>

            <button
              onClick={handleComplete}
              className="inline-flex items-center gap-2 px-8 py-3.5 rounded-2xl bg-cta-amber text-surface-900 font-bold transition-all duration-200 hover:shadow-[0_0_30px_rgba(245,197,66,0.3)]"
            >
              <TrendingUp className="w-4 h-4" />
              View Your Outlier Feed
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
