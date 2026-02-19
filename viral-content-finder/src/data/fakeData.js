// Fake data for the Viral Content Finder MVP demo

export const niches = [
  { id: 'fitness', label: 'Fitness & Wellness', emoji: '💪', color: '#10b981' },
  { id: 'food', label: 'Food & Cooking', emoji: '🍳', color: '#f97316' },
  { id: 'fashion', label: 'Fashion & Style', emoji: '👗', color: '#ec4899' },
  { id: 'tech', label: 'Tech & Gadgets', emoji: '📱', color: '#3b5cff' },
  { id: 'travel', label: 'Travel & Adventure', emoji: '✈️', color: '#a855f7' },
  { id: 'business', label: 'Business & Finance', emoji: '💼', color: '#facc15' },
  { id: 'beauty', label: 'Beauty & Skincare', emoji: '✨', color: '#f472b6' },
  { id: 'comedy', label: 'Comedy & Entertainment', emoji: '😂', color: '#34d399' },
]

export const competitors = [
  { id: 1, handle: '@fitwithjess', name: 'Jessica Moore', niche: 'fitness', followers: 245000, avgViews: 35000 },
  { id: 2, handle: '@chefmarcus', name: 'Marcus Chen', niche: 'food', followers: 890000, avgViews: 120000 },
  { id: 3, handle: '@stylebyluna', name: 'Luna Park', niche: 'fashion', followers: 1200000, avgViews: 180000 },
  { id: 4, handle: '@techdaily', name: 'Tech Daily', niche: 'tech', followers: 560000, avgViews: 85000 },
  { id: 5, handle: '@wanderlustkim', name: 'Kim Nakamura', niche: 'travel', followers: 430000, avgViews: 62000 },
  { id: 6, handle: '@hustlehouse', name: 'Hustle House', niche: 'business', followers: 320000, avgViews: 48000 },
  { id: 7, handle: '@glowupgrace', name: 'Grace Liu', niche: 'beauty', followers: 780000, avgViews: 95000 },
  { id: 8, handle: '@bodybybri', name: 'Brianna Taylor', niche: 'fitness', followers: 510000, avgViews: 72000 },
  { id: 9, handle: '@maboroshi_eats', name: 'Maboroshi Eats', niche: 'food', followers: 340000, avgViews: 55000 },
  { id: 10, handle: '@minimalfit', name: 'Minimal Fit Co.', niche: 'fitness', followers: 190000, avgViews: 28000 },
  { id: 11, handle: '@nomadnico', name: 'Nico Fernandez', niche: 'travel', followers: 620000, avgViews: 90000 },
  { id: 12, handle: '@skincarebysa', name: 'Sarah Ahmed', niche: 'beauty', followers: 450000, avgViews: 68000 },
]

const hookTypes = [
  'Pattern Interrupt',
  'Controversial Take',
  'Before/After Reveal',
  'Question Hook',
  'Shocking Stat',
  'POV Format',
  'Tutorial Teaser',
  'Trend Remix',
  'Relatable Struggle',
  'Myth Buster',
]

const contentFormats = [
  'Talking Head + B-Roll',
  'Text Overlay Only',
  'Green Screen React',
  'Voiceover + Demo',
  'Duet/Stitch Style',
  'Transition Montage',
  'Day-in-the-Life',
  'Tutorial Walkthrough',
  'Skit / Comedy',
  'Product Showcase',
]

const audioTrends = [
  { name: 'Original Audio', trending: false },
  { name: '"Oh No" Remix — Capone', trending: true },
  { name: 'Aesthetic Lofi Beat #42', trending: true },
  { name: 'Voiceover — No Music', trending: false },
  { name: '"Money Trees" — Kendrick', trending: true },
  { name: 'Cinematic Tension Build', trending: true },
  { name: '"Nasty" — Tinashe', trending: true },
  { name: 'ASMR Natural Sound', trending: false },
  { name: '"APT." — ROSE & Bruno Mars', trending: true },
  { name: 'Motivational Speech Clip', trending: false },
]

const topics = {
  fitness: [
    '5-minute morning stretch routine',
    'Why your protein timing is wrong',
    'Gym hack: cable machine angles',
    'Walking 10K steps changed everything',
    'The exercise scientists say burns most fat',
    'Beginner workout mistakes to avoid',
  ],
  food: [
    '3-ingredient viral pasta hack',
    'Restaurant copycat: In-N-Out sauce',
    'Meal prep for the entire week in 1 hour',
    'The egg sandwich that broke the internet',
    'Air fryer trick nobody talks about',
    'Protein-packed overnight oats',
  ],
  fashion: [
    'Capsule wardrobe: 15 pieces, 30 outfits',
    'Thrift flip: $3 blazer transformation',
    'Quiet luxury on a budget',
    'Outfit formula that always works',
    'Spring 2026 trend you need to know',
    'How to style wide-leg pants',
  ],
  tech: [
    'iPhone setting 95% of people don\'t know',
    'AI tool that replaced my entire workflow',
    'Budget vs Premium: can you tell?',
    'This $30 gadget changed my desk setup',
    'Hidden macOS features power users need',
    'The app that saves me 2 hours daily',
  ],
  travel: [
    'Hidden gem: this town costs $20/day',
    'Airport hack that saves 45 minutes',
    'Solo travel safety tips nobody mentions',
    'The $200 flight trick airlines hate',
    'Best sunset spot in every continent',
    'Packing hack: 2 weeks in a carry-on',
  ],
  business: [
    'Side hustle that made $10K month one',
    'The pricing mistake killing your sales',
    'How I automated my entire business',
    'Networking script that actually works',
    'The 5am routine of a 7-figure founder',
    'Why your content isn\'t converting',
  ],
  beauty: [
    'Skincare order that actually matters',
    'Drugstore dupe for $85 serum',
    'Glass skin routine in 5 steps',
    'Dermatologist reacts to viral trends',
    'The ingredient combo that cleared my skin',
    'Makeup hack for hooded eyes',
  ],
  comedy: [
    'When your mom discovers Instagram',
    'Corporate meeting bingo',
    'Types of people at the gym',
    'Dating app red flags as filters',
    'When the WiFi goes out for 5 minutes',
    'POV: you\'re the group chat meme dealer',
  ],
}

const ctaStyles = [
  'Follow for more',
  'Save this for later',
  'Comment your experience',
  'Share with someone who needs this',
  'Link in bio',
  'No CTA (content speaks for itself)',
  'Drop a 🔥 if you agree',
  'Tag a friend',
]

function randomFrom(arr) {
  return arr[Math.floor(Math.random() * arr.length)]
}

function randomBetween(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min
}

function generateVelocityData(hours, views) {
  const points = []
  let cumulative = 0
  for (let i = 0; i <= hours; i++) {
    const growth = i < 3
      ? views * 0.15 * Math.random()
      : i < 8
        ? views * 0.08 * Math.random()
        : views * 0.03 * Math.random()
    cumulative += growth
    points.push({ hour: i, views: Math.round(Math.min(cumulative, views)) })
  }
  return points
}

function timeAgo(hours) {
  if (hours < 1) return `${Math.round(hours * 60)}m ago`
  if (hours < 24) return `${Math.round(hours)}h ago`
  return `${Math.round(hours / 24)}d ago`
}

export function generateOutlierReels(count = 20) {
  const reels = []
  for (let i = 0; i < count; i++) {
    const creator = randomFrom(competitors)
    const multiplier = randomBetween(5, 52)
    const views = creator.avgViews * multiplier
    const hoursAgo = Math.random() * 36 + 1
    const nicheTopics = topics[creator.niche] || topics.fitness
    const lifecycle = multiplier > 30
      ? 'emerging'
      : multiplier > 15
        ? 'peaking'
        : multiplier > 8
          ? 'rising'
          : 'saturated'

    reels.push({
      id: `reel-${i + 1}`,
      creator,
      topic: randomFrom(nicheTopics),
      views,
      likes: Math.round(views * (Math.random() * 0.08 + 0.03)),
      comments: Math.round(views * (Math.random() * 0.005 + 0.001)),
      shares: Math.round(views * (Math.random() * 0.02 + 0.005)),
      saves: Math.round(views * (Math.random() * 0.03 + 0.01)),
      multiplier,
      hoursAgo,
      timeAgo: timeAgo(hoursAgo),
      lifecycle,
      velocityData: generateVelocityData(Math.min(Math.round(hoursAgo), 24), views),
      breakdown: {
        hookType: randomFrom(hookTypes),
        contentFormat: randomFrom(contentFormats),
        audio: randomFrom(audioTrends),
        topic: randomFrom(nicheTopics),
        ctaStyle: randomFrom(ctaStyles),
        duration: randomBetween(7, 60),
        textOverlays: randomBetween(0, 8),
        postingHour: randomBetween(6, 23),
      },
      thumbnailColor: `hsl(${randomFrom([140, 155, 170, 260, 275, 290, 310])}, ${randomBetween(45, 70)}%, ${randomBetween(15, 30)}%)`,
    })
  }
  return reels.sort((a, b) => b.multiplier - a.multiplier)
}

export function generateContentBriefs(niches = ['fitness']) {
  return [
    {
      id: 'brief-1',
      title: 'The Morning Routine That\'s Going Viral',
      hook: 'Open with: "I tried the routine that got 4M views and here\'s what happened..."',
      format: 'Talking Head + B-Roll',
      audio: '"APT." — ROSE & Bruno Mars (trending)',
      duration: '15-20 seconds',
      keyPoints: [
        'Start with the controversial claim in first 2 seconds',
        'Show 3 quick cuts of the routine in action',
        'End with your honest reaction / results',
        'Use text overlay for the key stat',
      ],
      confidence: 87,
      basedOn: 3,
      niche: niches[0],
      trendLifecycle: 'emerging',
      estimatedReach: '50K-200K views',
    },
    {
      id: 'brief-2',
      title: 'Myth-Busting Format Is Exploding Right Now',
      hook: 'Start with: "Stop doing [common advice] — here\'s what actually works"',
      format: 'Green Screen React + Voiceover',
      audio: 'Cinematic Tension Build (trending)',
      duration: '20-30 seconds',
      keyPoints: [
        'Use the green screen to show the "bad advice" post',
        'React genuinely — frustration works better than calm',
        'Provide your counter-evidence in 3 bullet text overlays',
        'End with "Follow for more myth-busting"',
      ],
      confidence: 92,
      basedOn: 5,
      niche: niches[0],
      trendLifecycle: 'peaking',
      estimatedReach: '100K-500K views',
    },
    {
      id: 'brief-3',
      title: 'The "One Thing" Format',
      hook: 'Open: "If I could only give you ONE piece of advice about [niche]..."',
      format: 'Talking Head — Direct to Camera',
      audio: 'Voiceover — No Music',
      duration: '8-12 seconds',
      keyPoints: [
        'Look directly into the camera, no fancy editing needed',
        'Deliver one clear, actionable insight',
        'Pause for 1 beat before the reveal',
        'No CTA — let the content create the follow',
      ],
      confidence: 78,
      basedOn: 7,
      niche: niches[0],
      trendLifecycle: 'emerging',
      estimatedReach: '30K-150K views',
    },
  ]
}

export function generateDailyDigest() {
  return {
    date: 'Today, Feb 19 2026',
    summary: {
      newOutliers: 23,
      avgMultiplier: '18.4x',
      topNiche: 'Fitness & Wellness',
      emergingTrends: 5,
    },
    topOutliers: generateOutlierReels(5),
    trendAlerts: [
      {
        id: 'trend-1',
        title: '"One Thing" advice format',
        status: 'emerging',
        velocity: '+340% in 6h',
        description: 'Short, direct-to-camera Reels sharing a single piece of advice. 8-12 seconds. No music. Authenticity driving saves.',
        reelsCount: 47,
      },
      {
        id: 'trend-2',
        title: 'Split-screen transformations',
        status: 'peaking',
        velocity: '+890% in 12h',
        description: 'Before/after reveals using the split-screen transition. Working across fitness, beauty, and fashion niches.',
        reelsCount: 132,
      },
      {
        id: 'trend-3',
        title: '"APT." dance challenge remix',
        status: 'peaking',
        velocity: '+1200% in 18h',
        description: 'Creators adapting the APT dance with niche-specific twists. Highest engagement when combined with tutorial content.',
        reelsCount: 286,
      },
      {
        id: 'trend-4',
        title: 'Whispering voiceover ASMR tips',
        status: 'emerging',
        velocity: '+180% in 4h',
        description: 'ASMR-style whispered tips and tutorials. Unusually high save rates. Working especially well in skincare and cooking.',
        reelsCount: 19,
      },
      {
        id: 'trend-5',
        title: 'Green screen "proof" reactions',
        status: 'saturated',
        velocity: '+45% in 24h',
        description: 'Reacting to screenshots/articles as "proof" for claims. Still working but engagement velocity slowing significantly.',
        reelsCount: 520,
      },
    ],
    briefs: generateContentBriefs(),
  }
}

export function formatNumber(num) {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
  return num.toString()
}
