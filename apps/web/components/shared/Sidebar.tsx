'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useClerk, useUser } from '@clerk/nextjs'
import { cn } from '@/lib/utils'
import {
  FileText, Linkedin, FileSearch, PenLine, MessageSquare,
  Briefcase, Compass, DollarSign, Mail, Radar, LogOut,
  Settings, ChevronLeft, ChevronRight, Check, X,
} from 'lucide-react'
import { useToast } from '@/components/ui/use-toast'
import { apiFetch } from '@/lib/api'

const navItems = [
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

  const [userName, setUserName] = useState<string | null>(null)
  const [userEmail, setUserEmail] = useState<string | null>(null)
  const [photoUrl, setPhotoUrl] = useState<string | null>(null)
  const [confirmSignOut, setConfirmSignOut] = useState(false)
  const [collapsed, setCollapsed] = useState(false)

  // Single fixed-position tooltip — bypasses all overflow clipping
  const [tooltip, setTooltip] = useState<{ label: string; y: number } | null>(null)

  const showTip = useCallback((e: React.MouseEvent<HTMLElement>, label: string) => {
    const rect = e.currentTarget.getBoundingClientRect()
    setTooltip({ label, y: rect.top + rect.height / 2 })
  }, [])
  const hideTip = useCallback(() => setTooltip(null), [])

  useEffect(() => {
    if (localStorage.getItem('sidebar_collapsed') === 'true') setCollapsed(true)
  }, [])

  function toggleCollapsed() {
    setCollapsed(prev => {
      const next = !prev
      localStorage.setItem('sidebar_collapsed', String(next))
      if (next) setTooltip(null)   // clear any visible tip on collapse
      return next
    })
  }

  useEffect(() => {
    if (user) setUserEmail(user.primaryEmailAddress?.emailAddress ?? null)
  }, [user])

  useEffect(() => {
    apiFetch('/api/profile')
      .then(r => r.json())
      .then(p => {
        setUserName(p.full_name || null)
        setPhotoUrl(p.cv_photo_url || null)
      })
      .catch(() => { })
  }, [])

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
          <div className="px-2.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700/60 text-slate-200 text-xs font-medium whitespace-nowrap shadow-lg">
            {tooltip.label}
          </div>
        </div>
      )}

      <aside
        className={cn(
          'relative flex-shrink-0 flex flex-col h-screen sticky top-0 border-r transition-[width] duration-200 ease-in-out',
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
            ? <ChevronRight className="h-3 w-3 text-slate-400" />
            : <ChevronLeft className="h-3 w-3 text-slate-400" />
          }
        </button>

        {/* ── Brand ── */}
        <div
          className="px-3 py-[18px] border-b flex items-center gap-3"
          style={{ borderColor: 'hsl(var(--sidebar-border))' }}
        >
          <img src="/brand-icon.png" alt="" className="w-8 h-8 flex-shrink-0" />
          <div className={cn(
            'min-w-0 transition-all duration-200',
            collapsed ? 'w-0 opacity-0 overflow-hidden' : 'flex-1 opacity-100'
          )}>
            <img src="/wordmark-white.png" alt="JobNok" className="h-3.5 w-auto" />
            <p className="text-[10px] text-slate-500 mt-1.5 leading-none whitespace-nowrap">AI Job Search Toolkit</p>
          </div>
        </div>

        {/* ── Nav ── */}
        <nav className="flex-1 overflow-y-auto py-4 px-2 scrollbar-hide">
          <div className={cn(
            'transition-all duration-200',
            collapsed ? 'h-0 opacity-0 overflow-hidden mb-0' : 'opacity-100 mb-3'
          )}>
            <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest px-3 whitespace-nowrap">Tools</p>
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
                      ? 'bg-indigo-500/15 text-indigo-300'
                      : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'
                  )}
                >
                  {active && (
                    <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-indigo-400 rounded-r-full" />
                  )}
                  <Icon className={cn(
                    'flex-shrink-0 transition-colors',
                    collapsed ? 'h-[18px] w-[18px]' : 'h-4 w-4',
                    active ? 'text-indigo-400' : 'text-slate-500 group-hover:text-slate-300'
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
              pathname === '/profile' ? 'bg-indigo-500/15' : 'hover:bg-white/5'
            )}
          >
            <div className="w-7 h-7 rounded-full flex-shrink-0 overflow-hidden bg-indigo-600 flex items-center justify-center">
              {photoUrl
                ? <img src={photoUrl} alt="" className="w-full h-full object-cover" />
                : <span className="text-[10px] font-bold text-white">{initials}</span>
              }
            </div>
            {!collapsed && (
              <>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-medium text-slate-300 truncate leading-tight">{userName || 'My Profile'}</p>
                  {userEmail && <p className="text-[10px] text-slate-500 truncate leading-tight">{userEmail}</p>}
                </div>
                <Settings className="h-3.5 w-3.5 text-slate-600 group-hover:text-slate-400 flex-shrink-0" />
              </>
            )}
          </Link>

          {/* Sign out — expanded */}
          {!collapsed && (
            confirmSignOut ? (
              <div className="flex items-center gap-2 px-3 py-2">
                <span className="text-[12px] text-slate-400 flex-1">Sign out?</span>
                <button onClick={doSignOut} className="text-[11px] font-semibold text-red-400 hover:text-red-300 px-2 py-1 rounded-lg hover:bg-red-500/10 transition-colors">Yes</button>
                <button onClick={() => setConfirmSignOut(false)} className="text-[11px] font-semibold text-slate-400 hover:text-slate-300 px-2 py-1 rounded-lg hover:bg-white/5 transition-colors">Cancel</button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmSignOut(true)}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-all duration-150"
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
                  className="w-7 h-7 rounded-lg flex items-center justify-center bg-red-500/15 text-red-400 hover:bg-red-500/25 transition-colors"
                >
                  <Check className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => setConfirmSignOut(false)}
                  onMouseEnter={(e) => showTip(e, 'Cancel')}
                  onMouseLeave={hideTip}
                  className="w-7 h-7 rounded-lg flex items-center justify-center text-slate-500 hover:bg-white/5 hover:text-slate-300 transition-colors"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmSignOut(true)}
                onMouseEnter={(e) => showTip(e, 'Sign out')}
                onMouseLeave={hideTip}
                className="w-full flex items-center justify-center py-2.5 rounded-xl text-slate-500 hover:text-red-400 hover:bg-white/5 transition-colors"
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
