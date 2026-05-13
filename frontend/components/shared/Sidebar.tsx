'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { cn } from '@/lib/utils'
import { createClient } from '@/lib/supabase/client'
import {
  FileText, Linkedin, FileSearch, PenLine, MessageSquare,
  Briefcase, Compass, DollarSign, Mail, Search, LogOut,
  Zap, User, ChevronRight, Settings,
} from 'lucide-react'
import { useToast } from '@/components/ui/use-toast'
import { apiFetch } from '@/lib/api'

const navItems = [
  { href: '/templates',          label: 'Smart Templates',    icon: FileText },
  { href: '/linkedin-fill',      label: 'LinkedIn Auto-Fill', icon: Linkedin },
  { href: '/resume-tailor',      label: 'Resume Tailor',      icon: FileSearch },
  { href: '/cover-letter',       label: 'Cover Letter',       icon: PenLine },
  { href: '/interview-prep',     label: 'Interview Prep',     icon: MessageSquare },
  { href: '/tracker',            label: 'Follow-Up Tracker',  icon: Briefcase },
  { href: '/recent-job-search',  label: 'Recent Job Search',  icon: Search },
  { href: '/startup-hunt',       label: 'Startup Hunt',       icon: Compass },
  { href: '/salary',             label: 'Salary Research',    icon: DollarSign },
  { href: '/bulk-email',         label: 'Bulk Email',         icon: Mail },
]

export function Sidebar() {
  const pathname = usePathname()
  const router = useRouter()
  const { toast } = useToast()
  const supabase = createClient()

  const [userName, setUserName] = useState<string | null>(null)
  const [userEmail, setUserEmail] = useState<string | null>(null)
  const [photoUrl, setPhotoUrl] = useState<string | null>(null)
  const [confirmSignOut, setConfirmSignOut] = useState(false)

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => {
      if (data.user) setUserEmail(data.user.email ?? null)
    })
    apiFetch('/api/profile')
      .then(r => r.json())
      .then(p => {
        setUserName(p.full_name || null)
        setPhotoUrl(p.cv_photo_url || null)
      })
      .catch(() => {})
  }, [])

  async function doSignOut() {
    await supabase.auth.signOut()
    toast({ title: 'Signed out' })
    router.push('/login')
    router.refresh()
  }

  const initials = userName
    ? userName.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()
    : userEmail?.[0]?.toUpperCase() ?? '?'

  return (
    <aside className="w-64 flex-shrink-0 flex flex-col h-screen sticky top-0 border-r" style={{ backgroundColor: 'hsl(var(--sidebar-bg))', borderColor: 'hsl(var(--sidebar-border))' }}>
      {/* Brand */}
      <div className="px-5 py-5 border-b" style={{ borderColor: 'hsl(var(--sidebar-border))' }}>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl gradient-brand flex items-center justify-center shadow-brand-sm flex-shrink-0">
            <Zap className="h-4 w-4 text-white" />
          </div>
          <div className="min-w-0">
            <p className="font-bold text-white text-sm tracking-tight leading-none">QuickJob</p>
            <p className="text-[10px] text-slate-500 mt-1 leading-none">AI Job Search Toolkit</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-5 px-3 scrollbar-hide">
        <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest px-3 mb-3">Tools</p>
        <div className="space-y-0.5">
          {navItems.map((item) => {
            const Icon = item.icon
            const active = pathname === item.href
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  'relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium transition-all duration-150 group',
                  active
                    ? 'bg-indigo-500/15 text-indigo-300'
                    : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'
                )}
              >
                {active && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-indigo-400 rounded-r-full" />
                )}
                <Icon className={cn('h-4 w-4 flex-shrink-0 transition-colors', active ? 'text-indigo-400' : 'text-slate-500 group-hover:text-slate-300')} />
                <span className="truncate">{item.label}</span>
              </Link>
            )
          })}
        </div>
      </nav>

      {/* Bottom — user section */}
      <div className="px-3 pb-4 pt-3 border-t space-y-1" style={{ borderColor: 'hsl(var(--sidebar-border))' }}>
        {/* Profile card */}
        <Link
          href="/profile"
          className={cn(
            'flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-150 group w-full',
            pathname === '/profile' ? 'bg-indigo-500/15' : 'hover:bg-white/5'
          )}
        >
          {/* Avatar */}
          <div className="w-7 h-7 rounded-full flex-shrink-0 overflow-hidden bg-indigo-600 flex items-center justify-center">
            {photoUrl
              ? <img src={photoUrl} alt="" className="w-full h-full object-cover" />
              : <span className="text-[10px] font-bold text-white">{initials}</span>
            }
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[13px] font-medium text-slate-300 truncate leading-tight">{userName || 'My Profile'}</p>
            {userEmail && <p className="text-[10px] text-slate-500 truncate leading-tight">{userEmail}</p>}
          </div>
          <Settings className="h-3.5 w-3.5 text-slate-600 group-hover:text-slate-400 flex-shrink-0" />
        </Link>

        {/* Sign out */}
        {confirmSignOut ? (
          <div className="flex items-center gap-2 px-3 py-2">
            <span className="text-[12px] text-slate-400 flex-1">Sign out?</span>
            <button
              onClick={doSignOut}
              className="text-[11px] font-semibold text-red-400 hover:text-red-300 px-2 py-1 rounded-lg hover:bg-red-500/10 transition-colors"
            >
              Yes
            </button>
            <button
              onClick={() => setConfirmSignOut(false)}
              className="text-[11px] font-semibold text-slate-400 hover:text-slate-300 px-2 py-1 rounded-lg hover:bg-white/5 transition-colors"
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            onClick={() => setConfirmSignOut(true)}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-all duration-150"
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </button>
        )}
      </div>
    </aside>
  )
}
