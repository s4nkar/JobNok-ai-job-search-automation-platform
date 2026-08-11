'use client'

import { useAuth } from '@clerk/nextjs'
import { Loader2 } from 'lucide-react'
import { cn } from '@jobnok/ui'
import { Sidebar } from '@/components/shared/Sidebar'
import { SidebarProvider, useSidebar } from '@/components/providers/SidebarProvider'

function DashboardContent({ children }: { children: React.ReactNode }) {
  const { collapsed } = useSidebar()

  return (
    <main className="flex-1 overflow-auto">
      <div className={cn('mx-auto px-8 py-8', collapsed ? 'max-w-none' : 'max-w-6xl')}>
        {children}
      </div>
    </main>
  )
}

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
    <SidebarProvider>
      <div className="flex min-h-screen bg-background">
        <Sidebar />
        <DashboardContent>{children}</DashboardContent>
      </div>
    </SidebarProvider>
  )
}
