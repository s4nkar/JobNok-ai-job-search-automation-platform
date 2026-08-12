'use client'

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

const SidebarContext = createContext<{ collapsed: boolean; toggleCollapsed: () => void } | null>(null)

export function SidebarProvider({ children }: { children: ReactNode }) {
  // Collapsed by default on first visit (no stored preference yet). A
  // returning user who explicitly expanded it gets that choice restored.
  const [collapsed, setCollapsed] = useState(true)

  useEffect(() => {
    if (localStorage.getItem('sidebar_collapsed') === 'false') setCollapsed(false)
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
