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
    <div className="min-h-screen bg-surface-950 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        {/* Logo */}
        <div className="text-center mb-8 animate-slide-up">
          <div className="inline-flex items-center gap-3 mb-6">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-brand-500 to-purple-500 flex items-center justify-center shadow-lg shadow-brand-500/25">
              <Zap className="w-7 h-7 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">
                <span className="text-brand-400">TURBO</span>
                <span className="text-surface-300 mx-2 font-light">|</span>
                <span className="text-surface-100">Viral Content Finder</span>
              </h1>
            </div>
          </div>
          <p className="text-surface-300 text-sm max-w-md mx-auto">
            Find viral content before it peaks. Get AI-powered briefs for what to post next.
          </p>
        </div>

        {/* Progress */}
        <div className="flex items-center gap-2 mb-8 justify-center">
          {[0, 1, 2].map((s) => (
            <div
              key={s}
              className={`h-1.5 rounded-full transition-all duration-500 ${
                s <= step ? 'w-16 bg-brand-500' : 'w-8 bg-surface-800'
              }`}
            />
          ))}
        </div>

        {/* Step 0: Pick Niches */}
        {step === 0 && (
          <div className="animate-slide-up">
            <div className="text-center mb-6">
              <h2 className="text-xl font-semibold text-surface-100 mb-2">
                What niches do you create in?
              </h2>
              <p className="text-surface-300 text-sm">Select 1-5 niches to track. You can change these later.</p>
            </div>
            <div className="grid grid-cols-2 gap-3 mb-8">
              {niches.map((niche) => {
                const selected = selectedNiches.includes(niche.id)
                return (
                  <button
                    key={niche.id}
                    onClick={() => toggleNiche(niche.id)}
                    className={`flex items-center gap-3 p-4 rounded-xl border transition-all text-left ${
                      selected
                        ? 'border-brand-500 bg-brand-500/10 shadow-lg shadow-brand-500/10'
                        : 'border-surface-800 bg-surface-900 hover:border-surface-700'
                    }`}
                  >
                    <span className="text-2xl">{niche.emoji}</span>
                    <div className="flex-1">
                      <div className="font-medium text-sm text-surface-100">{niche.label}</div>
                    </div>
                    {selected && (
                      <div className="w-5 h-5 rounded-full bg-brand-500 flex items-center justify-center">
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
              className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-brand-500 text-white font-semibold transition-all hover:bg-brand-600 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Continue
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Step 1: Pick Competitors */}
        {step === 1 && (
          <div className="animate-slide-up">
            <div className="text-center mb-6">
              <h2 className="text-xl font-semibold text-surface-100 mb-2">
                Pick accounts to watch
              </h2>
              <p className="text-surface-300 text-sm">
                We'll track these creators to detect outlier content in your niche.
              </p>
            </div>

            <div className="relative mb-4">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-300" />
              <input
                type="text"
                placeholder="Search accounts..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-surface-900 border border-surface-800 rounded-xl text-sm text-surface-100 placeholder:text-surface-300 focus:outline-none focus:border-brand-500 transition-colors"
              />
            </div>

            <div className="space-y-2 max-h-80 overflow-y-auto mb-6 pr-1">
              {filteredCompetitors.map((comp) => {
                const selected = selectedCompetitors.includes(comp.id)
                return (
                  <button
                    key={comp.id}
                    onClick={() => toggleCompetitor(comp.id)}
                    className={`w-full flex items-center gap-3 p-3 rounded-xl border transition-all text-left ${
                      selected
                        ? 'border-brand-500 bg-brand-500/10'
                        : 'border-surface-800 bg-surface-900 hover:border-surface-700'
                    }`}
                  >
                    <div className="w-10 h-10 rounded-full bg-gradient-to-br from-purple-400 to-pink-400 flex items-center justify-center text-sm font-bold text-white">
                      {comp.name.charAt(0)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-sm text-surface-100 truncate">{comp.name}</div>
                      <div className="text-xs text-surface-300">{comp.handle} · {(comp.followers / 1000).toFixed(0)}K followers</div>
                    </div>
                    {selected && (
                      <div className="w-5 h-5 rounded-full bg-brand-500 flex items-center justify-center flex-shrink-0">
                        <Check className="w-3 h-3 text-white" />
                      </div>
                    )}
                  </button>
                )
              })}
              {filteredCompetitors.length === 0 && (
                <div className="text-center py-8 text-surface-300 text-sm">
                  No accounts found in selected niches.
                </div>
              )}
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setStep(0)}
                className="px-6 py-3 rounded-xl border border-surface-700 text-surface-300 font-medium hover:bg-surface-800 transition-colors"
              >
                Back
              </button>
              <button
                onClick={() => setStep(2)}
                disabled={selectedCompetitors.length === 0}
                className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl bg-brand-500 text-white font-semibold transition-all hover:bg-brand-600 disabled:opacity-40 disabled:cursor-not-allowed"
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
            <div className="relative inline-block mb-8">
              <div className="w-24 h-24 rounded-3xl bg-gradient-to-br from-brand-500 to-purple-500 flex items-center justify-center animate-pulse-glow">
                <Sparkles className="w-12 h-12 text-white" />
              </div>
            </div>

            <h2 className="text-xl font-semibold text-surface-100 mb-3">
              Scanning your niches...
            </h2>
            <p className="text-surface-300 text-sm mb-8 max-w-sm mx-auto">
              Our AI is analyzing thousands of Reels across your selected niches to find outliers.
            </p>

            <div className="space-y-3 max-w-sm mx-auto mb-8 text-left">
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
                    <div className="w-5 h-5 rounded-full bg-emerald-500 flex items-center justify-center">
                      <Check className="w-3 h-3 text-white" />
                    </div>
                  ) : (
                    <div className="w-5 h-5 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
                  )}
                  <span className={item.done ? 'text-surface-100' : 'text-surface-300'}>
                    {item.label}
                  </span>
                </div>
              ))}
            </div>

            <button
              onClick={handleComplete}
              className="inline-flex items-center gap-2 px-8 py-3 rounded-xl bg-brand-500 text-white font-semibold transition-all hover:bg-brand-600"
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
