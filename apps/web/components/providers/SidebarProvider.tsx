'use client'

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

const SidebarContext = createContext<{
  collapsed: boolean
  toggleCollapsed: () => void
  mobileOpen: boolean
  toggleMobileOpen: () => void
  closeMobile: () => void
} | null>(null)

export function SidebarProvider({ children }: { children: ReactNode }) {
  // Open by default on first visit (no stored preference yet). A returning
  // user who explicitly collapsed it gets that choice restored.
  const [collapsed, setCollapsed] = useState(false)
  // Mobile off-canvas drawer state - separate from `collapsed` (a desktop-only
  // icon-width preference). Always starts closed regardless of `collapsed`.
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    if (localStorage.getItem('sidebar_collapsed') === 'true') setCollapsed(true)
  }, [])

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev
      localStorage.setItem('sidebar_collapsed', String(next))
      return next
    })
  }

  function toggleMobileOpen() {
    setMobileOpen((prev) => !prev)
  }

  function closeMobile() {
    setMobileOpen(false)
  }

  return (
    <SidebarContext.Provider value={{ collapsed, toggleCollapsed, mobileOpen, toggleMobileOpen, closeMobile }}>
      {children}
    </SidebarContext.Provider>
  )
}

export function useSidebar() {
  const ctx = useContext(SidebarContext)
  if (!ctx) throw new Error('useSidebar must be used within SidebarProvider')
  return ctx
}
