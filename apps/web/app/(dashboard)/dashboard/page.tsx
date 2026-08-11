'use client'

import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard, Briefcase, TrendingUp, Users, Award, AlertCircle,
  Loader2, Clock, ArrowRight, Compass, FileText, Mail, ChevronRight, Sparkles, Target,
} from 'lucide-react'
import { JobApplication, EmailCampaign, StartupHuntSavedOpportunity, StartupHuntSource, Template, UserProfile } from '@/lib/types'
import { ScoutCompany } from '@/lib/types'
import { cn, formatDate, isOverdue } from '@jobnok/ui'
import { apiGet } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { tools, toolBadgeColors } from '@jobnok/ui'

const ACTIVE_STATUSES = ['Applied', 'Phone Screen', 'Interview'] as const
const INTERVIEWING_STATUSES = ['Phone Screen', 'Interview'] as const

interface ToolUsage {
  tool_slug: string
  use_count: number
  last_used_at: string
}

const PROFILE_FIELDS: Array<{ key: keyof UserProfile; label: string }> = [
  { key: 'full_name', label: 'Full name' },
  { key: 'phone', label: 'Phone number' },
  { key: 'address_city', label: 'Location' },
  { key: 'linkedin_url', label: 'LinkedIn' },
  { key: 'work_authorization', label: 'Work authorization' },
  { key: 'cv_photo_url', label: 'Profile photo' },
]

export default function DashboardPage() {
  const { data: applications = [], isLoading: l1 } = useQuery({
    queryKey: queryKeys.tracker,
    queryFn: () => apiGet<JobApplication[]>('/api/tracker'),
  })
  const { data: templates = [], isLoading: l2 } = useQuery({
    queryKey: queryKeys.templates,
    queryFn: () => apiGet<Template[]>('/api/templates'),
  })
  const { data: leads = [], isLoading: l3 } = useQuery({
    queryKey: queryKeys.startupHuntOpportunities,
    queryFn: () => apiGet<StartupHuntSavedOpportunity[]>('/api/startup-hunt/opportunities'),
  })
  const { data: scoutCompanies = [], isLoading: l4 } = useQuery({
    queryKey: queryKeys.startupScoutCompanies,
    queryFn: () => apiGet<ScoutCompany[]>('/api/startup-scout/companies'),
  })
  const { data: campaigns = [], isLoading: l5 } = useQuery({
    queryKey: queryKeys.campaigns,
    queryFn: () => apiGet<EmailCampaign[]>('/api/campaigns'),
  })
  const { data: profile, isLoading: l6 } = useQuery({
    queryKey: queryKeys.profile,
    queryFn: () => apiGet<UserProfile>('/api/profile'),
  })
  const { data: toolUsage = [], isLoading: l7 } = useQuery({
    queryKey: queryKeys.toolUsage,
    queryFn: () => apiGet<ToolUsage[]>('/api/usage/tools'),
  })
  const { data: huntSources = [], isLoading: l8 } = useQuery({
    queryKey: queryKeys.startupHuntSources,
    queryFn: () => apiGet<StartupHuntSource[]>('/api/startup-hunt/sources'),
  })
  const loading = l1 || l2 || l3 || l4 || l5 || l6 || l7 || l8

  const active = applications.filter((a) => (ACTIVE_STATUSES as readonly string[]).includes(a.status))
  const interviewing = applications.filter((a) => (INTERVIEWING_STATUSES as readonly string[]).includes(a.status))
  const offers = applications.filter((a) => a.status === 'Offer')
  const openLeads = leads.filter((l) => l.opportunity_status !== 'skipped')
  const sendingCampaigns = campaigns.filter((c) => c.status === 'sending' || c.status === 'queued')

  const mostUsedTools = [...toolUsage]
    .sort((a, b) => b.use_count - a.use_count)
    .slice(0, 5)
    .map((u) => ({ usage: u, tool: tools.find((t) => t.slug === u.tool_slug) }))
    .filter((u): u is { usage: ToolUsage; tool: (typeof tools)[number] } => Boolean(u.tool))

  const needsAttention = applications
    .filter((a) => a.follow_up_date && !['Rejected', 'Withdrawn'].includes(a.status))
    .sort((a, b) => new Date(a.follow_up_date!).getTime() - new Date(b.follow_up_date!).getTime())
    .slice(0, 6)
  const overdueCount = needsAttention.filter((a) => isOverdue(a.follow_up_date)).length

  const recentApplications = [...applications]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 5)

  const profileFilled = profile ? PROFILE_FIELDS.filter((f) => Boolean(profile[f.key])).length : 0
  const profilePercent = profile ? Math.round((profileFilled / PROFILE_FIELDS.length) * 100) : 0
  const missingFields = profile ? PROFILE_FIELDS.filter((f) => !profile[f.key]) : []

  const firstName = profile?.full_name?.split(' ')[0]

  const statTiles = [
    { label: 'Applications Tracked', value: applications.length, Icon: Briefcase, iconBg: 'bg-indigo-100', iconColor: 'text-indigo-600' },
    { label: 'Active', value: active.length, Icon: TrendingUp, iconBg: 'bg-blue-100', iconColor: 'text-blue-600' },
    { label: 'Interviewing', value: interviewing.length, Icon: Users, iconBg: 'bg-violet-100', iconColor: 'text-violet-600' },
    { label: 'Offers', value: offers.length, Icon: Award, iconBg: 'bg-emerald-100', iconColor: 'text-emerald-600' },
    { label: 'Follow-ups Due', value: overdueCount, Icon: AlertCircle, iconBg: 'bg-red-100', iconColor: 'text-red-600' },
    { label: 'Startup Leads', value: openLeads.length, Icon: Compass, iconBg: 'bg-orange-100', iconColor: 'text-orange-600' },
  ]

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
          <p className="text-sm text-slate-400">Loading your dashboard…</p>
        </div>
      </div>
    )
  }

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="flex items-center gap-4 mb-6">
        <div className="page-header-icon bg-indigo-100">
          <LayoutDashboard className="h-5 w-5 text-indigo-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            {firstName ? `Welcome back, ${firstName}` : 'Welcome back'}
          </h1>
          <p className="text-slate-500 text-sm mt-0.5">Here&apos;s where your job search stands right now</p>
        </div>
      </div>

      {/* Stat tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
        {statTiles.map(({ label, value, Icon, iconBg, iconColor }) => (
          <div key={label} className="bg-white rounded-2xl border border-slate-100 shadow-card p-4 flex flex-col gap-3">
            <div className={cn('w-9 h-9 rounded-xl flex items-center justify-center', iconBg)}>
              <Icon className={cn('h-4 w-4', iconColor)} />
            </div>
            <div>
              <p className="text-xl font-bold text-slate-900 leading-none tabular-nums">{value}</p>
              <p className="text-xs text-slate-500 mt-1">{label}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left column — activity */}
        <div className="lg:col-span-2 space-y-4">
          {/* Needs attention */}
          <div className="bg-white rounded-2xl border border-slate-100 shadow-card overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
              <h2 className="text-sm font-semibold text-slate-800">Needs Your Attention</h2>
              <Link href="/tracker" className="text-xs font-medium text-indigo-600 hover:underline flex items-center gap-0.5">
                View tracker <ChevronRight className="h-3 w-3" />
              </Link>
            </div>
            {needsAttention.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 px-6 text-center">
                <div className="w-11 h-11 rounded-xl bg-emerald-50 flex items-center justify-center mb-3">
                  <Award className="h-5 w-5 text-emerald-500" />
                </div>
                <p className="text-sm font-medium text-slate-600">All caught up</p>
                <p className="text-xs text-slate-400 mt-0.5">No follow-ups due right now</p>
              </div>
            ) : (
              <div className="divide-y divide-slate-50">
                {needsAttention.map((app) => {
                  const overdue = isOverdue(app.follow_up_date)
                  return (
                    <div key={app.id} className="flex items-center justify-between px-5 py-3">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-slate-800 truncate">{app.company}</p>
                        <p className="text-xs text-slate-500 truncate">{app.role}</p>
                      </div>
                      <span className={cn('flex items-center gap-1.5 text-xs font-medium flex-shrink-0 ml-3',
                        overdue ? 'text-red-600' : 'text-slate-500')}>
                        {overdue && <Clock className="h-3 w-3" />}
                        {formatDate(app.follow_up_date)}
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Recent applications */}
          <div className="bg-white rounded-2xl border border-slate-100 shadow-card overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
              <h2 className="text-sm font-semibold text-slate-800">Recent Applications</h2>
              <Link href="/tracker" className="text-xs font-medium text-indigo-600 hover:underline flex items-center gap-0.5">
                View all <ChevronRight className="h-3 w-3" />
              </Link>
            </div>
            {recentApplications.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 px-6 text-center">
                <div className="w-11 h-11 rounded-xl bg-slate-100 flex items-center justify-center mb-3">
                  <Briefcase className="h-5 w-5 text-slate-300" />
                </div>
                <p className="text-sm font-medium text-slate-600">No applications yet</p>
                <Link href="/tracker" className="text-xs text-indigo-600 hover:underline mt-1">Add your first one</Link>
              </div>
            ) : (
              <div className="divide-y divide-slate-50">
                {recentApplications.map((app) => (
                  <div key={app.id} className="flex items-center justify-between px-5 py-3">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-slate-800 truncate">{app.company}</p>
                      <p className="text-xs text-slate-500 truncate">{app.role}</p>
                    </div>
                    <span className="text-xs text-slate-400 flex-shrink-0 ml-3">{formatDate(app.applied_at)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right column — profile, quick actions, activity summary */}
        <div className="space-y-4">
          {/* Profile completeness */}
          {profile && profilePercent < 100 && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-sm font-semibold text-slate-800">Complete Your Profile</h2>
                <span className="text-xs font-bold text-indigo-600">{profilePercent}%</span>
              </div>
              <div className="h-1.5 w-full bg-slate-100 rounded-full overflow-hidden mb-3">
                <div className="h-full gradient-brand rounded-full transition-all" style={{ width: `${profilePercent}%` }} />
              </div>
              <p className="text-xs text-slate-500 mb-3">
                Missing: {missingFields.map((f) => f.label).join(', ')}
              </p>
              <Link
                href="/profile"
                className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:underline"
              >
                Finish your profile <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          )}

          {/* Most used tools */}
          <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
            <h2 className="text-sm font-semibold text-slate-800 mb-3">Most Used Tools</h2>
            {mostUsedTools.length === 0 ? (
              <div className="flex flex-col items-center text-center py-4">
                <div className="w-9 h-9 rounded-xl bg-indigo-50 flex items-center justify-center mb-2">
                  <Sparkles className="h-4 w-4 text-indigo-400" />
                </div>
                <p className="text-xs text-slate-500">No tool usage yet — pick a tool from the sidebar to get started</p>
              </div>
            ) : (
              <div className="space-y-1">
                {mostUsedTools.map(({ usage, tool }) => {
                  const Icon = tool.icon
                  return (
                    <Link
                      key={tool.slug}
                      href={tool.href}
                      className="flex items-center gap-2.5 px-2 py-1.5 -mx-2 rounded-xl hover:bg-slate-50 transition-colors"
                    >
                      <div className={cn('w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 border', toolBadgeColors[tool.color])}>
                        <Icon className="h-3.5 w-3.5" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-medium text-slate-700 truncate">{tool.label}</p>
                        <p className="text-[10px] text-slate-400">Last used {formatDate(usage.last_used_at)}</p>
                      </div>
                      <span className="text-xs font-semibold text-slate-500 tabular-nums flex-shrink-0">{usage.use_count}×</span>
                    </Link>
                  )
                })}
              </div>
            )}
          </div>

          {/* Activity summary */}
          <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5 space-y-3">
            <h2 className="text-sm font-semibold text-slate-800 mb-1">Your Activity</h2>
            {[
              { href: '/templates', Icon: FileText, label: 'Templates saved', value: templates.length },
              { href: '/startup-scout', Icon: Compass, label: 'Companies watched', value: scoutCompanies.length },
              { href: '/startup-hunt', Icon: Target, label: 'Target companies', value: huntSources.length, badge: huntSources.length === 0 ? 'Add targets' : undefined },
              { href: '/bulk-email', Icon: Mail, label: 'Email campaigns', value: campaigns.length, badge: sendingCampaigns.length > 0 ? `${sendingCampaigns.length} sending` : undefined },
            ].map(({ href, Icon, label, value, badge }) => (
              <Link key={label} href={href} className="flex items-center justify-between group">
                <span className="flex items-center gap-2 text-sm text-slate-600 group-hover:text-slate-900 transition-colors">
                  <Icon className="h-3.5 w-3.5 text-slate-400" />
                  {label}
                </span>
                <span className="flex items-center gap-1.5">
                  {badge && <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700">{badge}</span>}
                  <span className="text-sm font-semibold text-slate-800 tabular-nums">{value}</span>
                </span>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
