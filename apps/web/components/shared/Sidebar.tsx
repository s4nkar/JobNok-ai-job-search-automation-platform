'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useClerk, useUser } from '@clerk/nextjs'
import { useQuery } from '@tanstack/react-query'
import { cn } from '@jobnok/ui'
import {
  FileText, Linkedin, FileSearch, PenLine, MessageSquare,
  Briefcase, Compass, DollarSign, Mail, Radar, LogOut,
  Settings, ChevronLeft, ChevronRight, Check, X, LayoutDashboard,
} from 'lucide-react'
import { useToast } from '@jobnok/ui'
import { apiGet } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { UserProfile } from '@/lib/types'
import { useSidebar } from '@/components/providers/SidebarProvider'

const navItems = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/templates', label: 'Smart Templates', icon: FileText },
  { href: '/linkedin-fill', label: 'LinkedIn Auto-Fill', icon: Linkedin },
  { href: '/resume-tailor', label: 'Resume Tailor', icon: FileSearch },
  { href: '/cover-letter', label: 'Cover Letter', icon: PenLine },
  { href: '/interview-prep', label: 'Interview Prep', icon: MessageSquare },
  { href: '/tracker', label: 'Follow-Up Tracker', icon: Briefcase },
  { href: '/startup-scout', label: 'Startup Scout', icon: Radar },
  { href: '/startup-hunt', label: 'Startup Hunt', icon: Compass },
  { href: '/salary', label: 'Salary Research', icon: DollarSign },
  { href: '/bulk-email', label: 'Bulk Email', icon: Mail },
]

export function Sidebar() {
  const pathname = usePathname()
  const router = useRouter()
  const { toast } = useToast()
  const { signOut } = useClerk()
  const { user } = useUser()

  const [userEmail, setUserEmail] = useState<string | null>(null)
  const [confirmSignOut, setConfirmSignOut] = useState(false)
  const { collapsed, toggleCollapsed: toggleCollapsedShared } = useSidebar()

  // Single fixed-position tooltip — bypasses all overflow clipping
  const [tooltip, setTooltip] = useState<{ label: string; y: number } | null>(null)

  const showTip = useCallback((e: React.MouseEvent<HTMLElement>, label: string) => {
    const rect = e.currentTarget.getBoundingClientRect()
    setTooltip({ label, y: rect.top + rect.height / 2 })
  }, [])
  const hideTip = useCallback(() => setTooltip(null), [])

  function toggleCollapsed() {
    if (!collapsed) setTooltip(null)   // clear any visible tip when collapsing
    toggleCollapsedShared()
  }

  useEffect(() => {
    if (user) setUserEmail(user.primaryEmailAddress?.emailAddress ?? null)
  }, [user])

  const { data: profile } = useQuery({
    queryKey: queryKeys.profile,
    queryFn: () => apiGet<UserProfile>('/api/profile'),
  })
  const userName = profile?.full_name || null
  const photoUrl = profile?.cv_photo_url || null

  async function doSignOut() {
    await signOut()
    toast({ title: 'Signed out' })
    router.push('/login')
    router.refresh()
  }

  const initials = userName
    ? userName.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()
    : userEmail?.[0]?.toUpperCase() ?? '?'

  return (
    <>
      {/* Fixed tooltip — rendered outside aside so it's never clipped */}
      {collapsed && tooltip && (
        <div
          className="fixed z-[9999] pointer-events-none"
          style={{ top: tooltip.y, left: 68, transform: 'translateY(-50%)' }}
        >
          <div className="px-2.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700/60 text-slate-100 text-xs font-medium whitespace-nowrap shadow-lg">
            {tooltip.label}
          </div>
        </div>
      )}

      <aside
        className={cn(
          'relative flex-shrink-0 flex flex-col h-screen sticky top-0 border-r shadow-[4px_0_16px_-4px_rgba(15,23,42,0.06)] transition-[width] duration-200 ease-in-out',
          collapsed ? 'w-[60px]' : 'w-64'
        )}
        style={{ backgroundColor: 'hsl(var(--sidebar-bg))', borderColor: 'hsl(var(--sidebar-border))' }}
      >
        {/* ── Toggle button — fixed on right edge, same position always ── */}
        <button
          onClick={toggleCollapsed}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="absolute -right-3 top-[22px] z-20 w-6 h-6 rounded-full flex items-center justify-center shadow-md border transition-all duration-150 hover:scale-110"
          style={{
            backgroundColor: 'hsl(var(--sidebar-bg))',
            borderColor: 'hsl(var(--sidebar-border))',
          }}
        >
          {collapsed
            ? <ChevronRight className="h-3 w-3 text-muted-foreground" />
            : <ChevronLeft className="h-3 w-3 text-muted-foreground" />
          }
        </button>

        {/* ── Brand ── */}
        <div
          className="px-3 py-[18px] border-b flex items-center"
          style={{ borderColor: 'hsl(var(--sidebar-border))' }}
        >
          {collapsed
            ? <img src="/brand-icon.png" alt="JobNok" className="w-8 h-8 flex-shrink-0 mx-auto" />
            : <img src="/logo.png" alt="JobNok" className="h-8 w-auto" />
          }
        </div>

        {/* ── Nav ── */}
        <nav className="flex-1 overflow-y-auto py-4 px-2 scrollbar-hide">
          <div className={cn(
            'transition-all duration-200',
            collapsed ? 'h-0 opacity-0 overflow-hidden mb-0' : 'opacity-100 mb-3'
          )}>
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest px-3 whitespace-nowrap">Tools</p>
          </div>

          <div className="space-y-0.5">
            {navItems.map((item) => {
              const Icon = item.icon
              const active = pathname === item.href || pathname.startsWith(item.href + '/')
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onMouseEnter={collapsed ? (e) => showTip(e, item.label) : undefined}
                  onMouseLeave={collapsed ? hideTip : undefined}
                  className={cn(
                    'relative flex items-center rounded-xl text-[13px] font-medium transition-all duration-150',
                    collapsed ? 'justify-center gap-0 px-0 py-2.5 w-full' : 'gap-3 px-3 py-2.5',
                    active
                      ? 'bg-accent text-accent-foreground'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                  )}
                >
                  {active && (
                    <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-primary rounded-r-full" />
                  )}
                  <Icon className={cn(
                    'flex-shrink-0 transition-colors',
                    collapsed ? 'h-[18px] w-[18px]' : 'h-4 w-4',
                    active ? 'text-primary' : 'text-muted-foreground'
                  )} />
                  <span className={cn(
                    'transition-all duration-200 whitespace-nowrap overflow-hidden',
                    collapsed ? 'w-0 opacity-0' : 'flex-1 opacity-100'
                  )}>
                    {item.label}
                  </span>
                </Link>
              )
            })}
          </div>
        </nav>

        {/* ── Bottom — profile + sign out ── */}
        <div className="px-2 pb-3 pt-3 border-t space-y-1" style={{ borderColor: 'hsl(var(--sidebar-border))' }}>

          {/* Profile */}
          <Link
            href="/profile"
            onMouseEnter={collapsed ? (e) => showTip(e, userName || 'My Profile') : undefined}
            onMouseLeave={collapsed ? hideTip : undefined}
            className={cn(
              'flex items-center rounded-xl transition-all duration-150 group w-full',
              collapsed ? 'justify-center gap-0 px-0 py-2' : 'gap-3 px-3 py-2.5',
              pathname === '/profile' ? 'bg-accent' : 'hover:bg-muted'
            )}
          >
            <div className="w-7 h-7 rounded-full flex-shrink-0 overflow-hidden bg-primary flex items-center justify-center">
              {photoUrl
                ? <img src={photoUrl} alt="" className="w-full h-full object-cover" />
                : <span className="text-[10px] font-bold text-primary-foreground">{initials}</span>
              }
            </div>
            {!collapsed && (
              <>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-medium text-foreground truncate leading-tight">{userName || 'My Profile'}</p>
                  {userEmail && <p className="text-[10px] text-muted-foreground truncate leading-tight">{userEmail}</p>}
                </div>
                <Settings className="h-3.5 w-3.5 text-muted-foreground group-hover:text-foreground flex-shrink-0" />
              </>
            )}
          </Link>

          {/* Sign out — expanded */}
          {!collapsed && (
            confirmSignOut ? (
              <div className="flex items-center gap-2 px-3 py-2">
                <span className="text-[12px] text-muted-foreground flex-1">Sign out?</span>
                <button onClick={doSignOut} className="text-[11px] font-semibold text-destructive hover:text-destructive/80 px-2 py-1 rounded-lg hover:bg-destructive/10 transition-colors">Yes</button>
                <button onClick={() => setConfirmSignOut(false)} className="text-[11px] font-semibold text-muted-foreground hover:text-foreground px-2 py-1 rounded-lg hover:bg-muted transition-colors">Cancel</button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmSignOut(true)}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-all duration-150"
              >
                <LogOut className="h-4 w-4" />
                Sign out
              </button>
            )
          )}

          {/* Sign out — collapsed (icon with 2-step confirm) */}
          {collapsed && (
            confirmSignOut ? (
              <div className="flex items-center justify-center gap-2 py-2">
                <button
                  onClick={doSignOut}
                  onMouseEnter={(e) => showTip(e, 'Confirm')}
                  onMouseLeave={hideTip}
                  className="w-7 h-7 rounded-lg flex items-center justify-center bg-destructive/15 text-destructive hover:bg-destructive/25 transition-colors"
                >
                  <Check className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => setConfirmSignOut(false)}
                  onMouseEnter={(e) => showTip(e, 'Cancel')}
                  onMouseLeave={hideTip}
                  className="w-7 h-7 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmSignOut(true)}
                onMouseEnter={(e) => showTip(e, 'Sign out')}
                onMouseLeave={hideTip}
                className="w-full flex items-center justify-center py-2.5 rounded-xl text-muted-foreground hover:text-destructive hover:bg-muted transition-colors"
              >
                <LogOut className="h-[18px] w-[18px]" />
              </button>
            )
          )}
        </div>
      </aside >
    </>
  )
}
