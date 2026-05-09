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
  DollarSign,
  Mail,
  Search,
  LogOut,
  Zap,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/use-toast'

const navItems = [
  { href: '/templates',      label: 'Smart Templates',    icon: FileText,     description: 'Reusable message templates' },
  { href: '/linkedin-fill',  label: 'LinkedIn Auto-Fill', icon: Linkedin,     description: 'Scrape & fill from profiles' },
  { href: '/resume-tailor',  label: 'Resume Tailor',      icon: FileSearch,   description: 'ATS score + keyword gaps' },
  { href: '/cover-letter',   label: 'Cover Letter',       icon: PenLine,      description: 'AI-generated cover letters' },
  { href: '/interview-prep', label: 'Interview Prep',     icon: MessageSquare, description: '10 STAR Q&As from JD' },
  { href: '/tracker',        label: 'Follow-Up Tracker',  icon: Briefcase,    description: 'Track every application' },
  { href: '/recent-job-search', label: 'Recent Job Search', icon: Search,     description: 'Find fresh ATS job postings' },
  { href: '/salary',         label: 'Salary Research',    icon: DollarSign,   description: 'Market rate breakdown' },
  { href: '/bulk-email',     label: 'Bulk Email',         icon: Mail,         description: 'Campaign sender with delays' },
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
    <aside className="w-64 flex-shrink-0 bg-slate-900 text-white flex flex-col h-screen sticky top-0">
      {/* Brand */}
      <div className="px-6 py-5 border-b border-slate-700">
        <div className="flex items-center gap-2">
          <Zap className="h-5 w-5 text-yellow-400" />
          <span className="font-bold text-lg tracking-tight">QuickJob</span>
        </div>
        <p className="text-xs text-slate-400 mt-0.5">AI Job Search Toolkit</p>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
        {navItems.map((item) => {
          const Icon = item.icon
          const active = pathname === item.href
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors group',
                active
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-white'
              )}
            >
              <Icon className={cn('h-4 w-4 flex-shrink-0', active ? 'text-yellow-400' : 'text-slate-500 group-hover:text-slate-300')} />
              <span className="truncate font-medium">{item.label}</span>
            </Link>
          )
        })}
      </nav>

      {/* Sign out */}
      <div className="px-3 py-4 border-t border-slate-700">
        <Button
          variant="ghost"
          size="sm"
          onClick={handleSignOut}
          className="w-full justify-start text-slate-400 hover:text-white hover:bg-slate-800"
        >
          <LogOut className="h-4 w-4 mr-2" />
          Sign out
        </Button>
      </div>
    </aside>
  )
}
