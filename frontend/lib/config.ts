// Single source of truth for all environment variables in the frontend.
// All values come from env — never hardcode limits, URLs, or keys.

export const config = {
  supabase: {
    url: process.env.NEXT_PUBLIC_SUPABASE_URL!,
    anonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  },

  app: {
    url: process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000',
    backendUrl: process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000',
  },

  rateLimits: {
    linkedinScrapesPerDay: parseInt(process.env.NEXT_PUBLIC_RATE_LIMIT_LINKEDIN || '10', 10),
    resumeTailorPerDay:    parseInt(process.env.NEXT_PUBLIC_RATE_LIMIT_RESUME || '5', 10),
    coverLetterPerDay:     parseInt(process.env.NEXT_PUBLIC_RATE_LIMIT_COVER_LETTER || '5', 10),
    interviewPrepPerDay:   parseInt(process.env.NEXT_PUBLIC_RATE_LIMIT_INTERVIEW || '10', 10),
    salaryResearchPerDay:  parseInt(process.env.NEXT_PUBLIC_RATE_LIMIT_SALARY || '5', 10),
    jobSearchPerDay:       parseInt(process.env.NEXT_PUBLIC_RATE_LIMIT_JOB_SEARCH || '10', 10),
    startupHuntPerDay:     parseInt(process.env.NEXT_PUBLIC_RATE_LIMIT_STARTUP_HUNT || '8', 10),
    bulkEmailPerCampaign:  parseInt(process.env.NEXT_PUBLIC_RATE_LIMIT_BULK_CAMPAIGN || '500', 10),
    bulkEmailPerMonth:     parseInt(process.env.NEXT_PUBLIC_RATE_LIMIT_BULK_MONTH || '3000', 10),
  },

  bulkEmail: {
    minDelaySeconds:     parseInt(process.env.NEXT_PUBLIC_BULK_EMAIL_MIN_DELAY || '20', 10),
    defaultDelaySeconds: parseInt(process.env.NEXT_PUBLIC_BULK_EMAIL_DEFAULT_DELAY || '30', 10),
  },

  linkedin: {
    cacheTtlDays: parseInt(process.env.NEXT_PUBLIC_LINKEDIN_CACHE_TTL_DAYS || '7', 10),
  },
} as const
