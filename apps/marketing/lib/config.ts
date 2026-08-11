// Single source of truth for env-driven config in the marketing app.
// The dashboard app lives on a separate subdomain, so every internal
// "log in" / "sign up" / "dashboard" link has to be absolute.

export const config = {
  appUrl: process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000',
} as const
