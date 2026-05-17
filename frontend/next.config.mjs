/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: '**.supabase.co' },
      { protocol: 'https', hostname: 'media.licdn.com' },
      { protocol: 'https', hostname: 'avatars.githubusercontent.com' },
      { protocol: 'https', hostname: 'lh3.googleusercontent.com' },
    ],
  },
  // afterFiles rewrites run only when Next.js finds no matching page/API route.
  // /api/auth/callback is a real Next.js route so it is never rewritten.
  // All other /api/* paths have no Next.js routes and are proxied to FastAPI.
  // In production nginx intercepts /api/* before Next.js sees it, so this
  // rewrite is a no-op there. In dev (no nginx) it routes to the FastAPI
  // container using the server-side BACKEND_URL env var.
  //
  // IMPORTANT: rewrites() is called once at server startup, not per-request.
  // BACKEND_URL is frozen at that point — changing it requires a restart.
  // Never rely on this rewrite as a prod routing fallback; always use nginx.
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000'
    return {
      beforeFiles: [],
      afterFiles: [
        {
          source: '/api/:path*',
          destination: `${backendUrl}/api/:path*`,
        },
      ],
      fallback: [],
    }
  },
  async headers() {
    return [
      {
        source: '/api/:path*',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-XSS-Protection', value: '1; mode=block' },
        ],
      },
    ]
  },
}

export default nextConfig
