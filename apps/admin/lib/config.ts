// Single source of truth for env vars in this app - never hardcode URLs.

export const config = {
  appUrl: process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3002',
}
