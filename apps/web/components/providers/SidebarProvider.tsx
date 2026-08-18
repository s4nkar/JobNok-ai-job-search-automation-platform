'use client'

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

const SidebarContext = createContext<{ collapsed: boolean; toggleCollapsed: () => void } | null>(null)

export function SidebarProvider({ children }: { children: ReactNode }) {
  // Open by default on first visit (no stored preference yet). A returning
  // user who explicitly collapsed it gets that choice restored.
  const [collapsed, setCollapsed] = useState(false)

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

  return (
    <SidebarContext.Provider value={{ collapsed, toggleCollapsed }}>
      {children}
    </SidebarContext.Provider>
  )
}

export function useSidebar() {
  const ctx = useContext(SidebarContext)
  if (!ctx) throw new Error('useSidebar must be used within SidebarProvider')
  return ctx
}
