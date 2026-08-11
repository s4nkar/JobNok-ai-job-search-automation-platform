'use client'

import { useAuth } from '@clerk/nextjs'
import { Loader2 } from 'lucide-react'
import { Sidebar } from '@/components/shared/Sidebar'

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { isLoaded } = useAuth()

  // Clerk's client session can still be hydrating for a moment right after an
  // OAuth redirect — gating here means no page's data queries mount (and race
  // ahead of the session with an unauthenticated request) until it's ready.
  if (!isLoaded) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
      </div>
    )
  }

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <div className="max-w-6xl mx-auto px-8 py-8">
          {children}
        </div>
      </main>
    </div>
  )
}
