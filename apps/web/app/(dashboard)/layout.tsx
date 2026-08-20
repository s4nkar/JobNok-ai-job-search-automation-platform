'use client'

import { useAuth } from '@clerk/nextjs'
import { Loader2, Menu } from 'lucide-react'
import { cn } from '@jobnok/ui'
import { Sidebar } from '@/components/shared/Sidebar'
import { SidebarProvider, useSidebar } from '@/components/providers/SidebarProvider'

function DashboardContent({ children }: { children: React.ReactNode }) {
  const { collapsed, toggleMobileOpen } = useSidebar()

  // No `overflow-auto` here: the sidebar sticks itself to the viewport
  // (`h-screen sticky top-0`), which only works if the page/window is the
  // actual scrolling element. Any ancestor with `overflow-auto` (even one
  // that never visibly scrolls, because it always stretches to fit its
  // content) becomes the containing block for descendant `sticky` elements
  // instead of the window — silently breaking every sticky filter panel on
  // every dashboard page.
  return (
    <main className="flex-1 min-w-0">
      {/* Mobile-only header bar - the sidebar itself becomes an off-canvas
          drawer below md, so this is the only way to open it there. */}
      <div className="md:hidden sticky top-0 z-30 flex items-center gap-3 px-4 py-3 bg-white border-b border-slate-100">
        <button
          onClick={toggleMobileOpen}
          aria-label="Open menu"
          className="h-9 w-9 -ml-1.5 rounded-lg flex items-center justify-center text-slate-600 hover:bg-slate-100 transition-colors"
        >
          <Menu className="h-5 w-5" />
        </button>
        <img src="/brand-icon.png" alt="JobNok" className="h-6 w-6" />
      </div>
      <div className={cn('mx-auto px-4 py-6 md:px-8 md:py-8', collapsed ? 'max-w-none' : 'max-w-6xl')}>
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
