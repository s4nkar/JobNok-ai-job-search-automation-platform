'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { cn } from '@/lib/utils'
import { createClient } from '@/lib/supabase/client'
import {
  FileText,
  Linkedin,
  FileSearch,
  PenLine,
  MessageSquare,
  Briefcase,
  Compass,
  DollarSign,
  Mail,
  Search,
  LogOut,
  Zap,
} from 'lucide-react'
import { useToast } from '@/components/ui/use-toast'

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

  async function handleSignOut() {
    await supabase.auth.signOut()
    toast({ title: 'Signed out' })
    router.push('/login')
    router.refresh()
  }

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
                <Icon
                  className={cn(
                    'h-4 w-4 flex-shrink-0 transition-colors',
                    active ? 'text-indigo-400' : 'text-slate-500 group-hover:text-slate-300'
                  )}
                />
                <span className="truncate">{item.label}</span>
              </Link>
            )
          })}
        </div>
      </nav>

      {/* Bottom */}
      <div className="px-3 py-4 border-t" style={{ borderColor: 'hsl(var(--sidebar-border))' }}>
        <button
          onClick={handleSignOut}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium text-slate-400 hover:text-white hover:bg-white/5 transition-all duration-150"
        >
          <LogOut className="h-4 w-4 text-slate-500" />
          Sign out
        </button>
      </div>
    </aside>
  )
}
