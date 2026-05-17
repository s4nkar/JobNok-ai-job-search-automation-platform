'use client'

import React from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import {
  JobApplication,
  ApplicationStatus,
  APPLICATION_STATUSES,
  STATUS_COLORS,
  StartupHuntSavedOpportunity,
  StartupHuntOpportunityStatus,
  OpportunityArtifact,
} from '@/lib/types'
import { isOverdue, formatDate, formatCurrency, cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useToast } from '@/components/ui/use-toast'
import {
  Plus, Pencil, Trash2, Briefcase, Loader2, AlertCircle, TrendingUp, CheckCircle,
  Clock, ExternalLink, Compass, Mail, MapPin, MoreHorizontal, FileSearch, PenLine,
  MessageSquare, ChevronDown, ChevronUp, FileText, Radar, Users, Globe, Linkedin, StopCircle,
} from 'lucide-react'
import { ScoutCompany, ScoutContact, ScoutCrawlStatus } from '@/lib/types'
import { apiFetch } from '@/lib/api'

const schema = z.object({
  company: z.string().min(1, 'Required'),
  role: z.string().min(1, 'Required'),
  applied_at: z.string().min(1, 'Required'),
  status: z.enum(APPLICATION_STATUSES as [ApplicationStatus, ...ApplicationStatus[]]),
  follow_up_date: z.string().optional(),
  salary_min: z.coerce.number().optional(),
  salary_max: z.coerce.number().optional(),
  notes: z.string().optional(),
})
type FormData = z.infer<typeof schema>

const today = new Date().toISOString().split('T')[0]

const STARTUP_STATUS_META: Record<StartupHuntOpportunityStatus, { label: string; classes: string }> = {
  saved: { label: 'Saved', classes: 'bg-slate-100 text-slate-700' },
  contacted: { label: 'Contacted', classes: 'bg-pink-100 text-pink-700' },
  applied: { label: 'Applied', classes: 'bg-emerald-100 text-emerald-700' },
  skipped: { label: 'Skipped', classes: 'bg-gray-100 text-gray-500' },
}

const LEAD_STATUS_ORDER: StartupHuntOpportunityStatus[] = ['saved', 'contacted', 'applied', 'skipped']

const ARTIFACT_META: Record<string, { label: string; icon: React.ElementType; color: string; tool: string }> = {
  resume_analysis: { label: 'Resume Analysis', icon: FileSearch, color: 'text-violet-600', tool: 'resume-tailor' },
  cover_letter: { label: 'Cover Letter', icon: PenLine, color: 'text-pink-600', tool: 'cover-letter' },
  interview_prep: { label: 'Interview Prep', icon: MessageSquare, color: 'text-teal-600', tool: 'interview-prep' },
}

const SCOUT_STATUS_META: Record<ScoutCrawlStatus, { label: string; classes: string }> = {
  pending:  { label: 'Pending',   classes: 'bg-slate-100 text-slate-600' },
  crawling: { label: 'Crawling…', classes: 'bg-yellow-100 text-yellow-700' },
  enriched: { label: 'Enriched',  classes: 'bg-emerald-100 text-emerald-700' },
  partial:  { label: 'Partial',   classes: 'bg-orange-100 text-orange-700' },
  failed:   { label: 'Failed',    classes: 'bg-red-100 text-red-600' },
}

export default function TrackerPage() {
  const router = useRouter()
  const [tab, setTab] = useState<'applications' | 'leads' | 'scout'>('applications')
  const [applications, setApplications] = useState<JobApplication[]>([])
  const [leads, setLeads] = useState<StartupHuntSavedOpportunity[]>([])
  const [scoutCompanies, setScoutCompanies] = useState<ScoutCompany[]>([])
  const [scoutLoading, setScoutLoading] = useState(false)
  const [crawlingIds, setCrawlingIds] = useState<Set<string>>(new Set())
  const [stoppingIds, setStoppingIds] = useState<Set<string>>(new Set())
  const [expandedContacts, setExpandedContacts] = useState<Record<string, boolean>>({})
  const [contactsCache, setContactsCache] = useState<Record<string, ScoutContact[]>>({})
  const [contactsLoading, setContactsLoading] = useState<Record<string, boolean>>({})
  const scoutLoadedRef = useRef(false)
  const crawlIntervalsRef = useRef<Record<string, ReturnType<typeof setInterval>>>({})
  const [appsLoading, setAppsLoading] = useState(true)
  const [leadsLoading, setLeadsLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<JobApplication | null>(null)
  const [saving, setSaving] = useState(false)
  const [updatingLeadId, setUpdatingLeadId] = useState<string | null>(null)
  const [leadStatusFilter, setLeadStatusFilter] = useState<StartupHuntOpportunityStatus | 'all'>('all')
  const [artifactCounts, setArtifactCounts] = useState<Record<string, number>>({})
  const [expandedDocs, setExpandedDocs] = useState<Record<string, boolean>>({})
  const [docsCache, setDocsCache] = useState<Record<string, OpportunityArtifact[]>>({})
  const [docsLoading, setDocsLoading] = useState<Record<string, boolean>>({})
  const { toast } = useToast()

  const { register, handleSubmit, setValue, reset, watch, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { applied_at: today, status: 'Applied' },
  })
  const watchStatus = watch('status')

  useEffect(() => {
    fetchApplications()
    fetchLeads()
    // Scout tab is lazy-loaded on first open (see tab effect below)
    return () => {
      // Clean up any running poll intervals on unmount
      Object.values(crawlIntervalsRef.current).forEach(clearInterval)
    }
  }, [])

  // Lazy-load scout companies on first switch to the scout tab
  useEffect(() => {
    if (tab === 'scout' && !scoutLoadedRef.current) {
      scoutLoadedRef.current = true
      fetchScoutCompanies()
    }
  }, [tab])

  async function fetchApplications() {
    setAppsLoading(true)
    const res = await apiFetch('/api/tracker')
    if (res.ok) setApplications(await res.json())
    setAppsLoading(false)
  }

  async function fetchLeads() {
    setLeadsLoading(true)
    const [leadsRes, countsRes] = await Promise.all([
      apiFetch('/api/startup-hunt/opportunities'),
      apiFetch('/api/startup-hunt/artifact-counts'),
    ])
    if (leadsRes.ok) setLeads(await leadsRes.json())
    if (countsRes.ok) setArtifactCounts(await countsRes.json())
    setLeadsLoading(false)
  }

  async function fetchScoutCompanies() {
    setScoutLoading(true)
    const res = await apiFetch('/api/startup-scout/companies')
    if (res.ok) setScoutCompanies(await res.json())
    setScoutLoading(false)
  }

  function _clearCrawlInterval(id: string) {
    if (crawlIntervalsRef.current[id]) {
      clearInterval(crawlIntervalsRef.current[id])
      delete crawlIntervalsRef.current[id]
    }
  }

  async function startCrawl(company: ScoutCompany) {
    setCrawlingIds((prev) => new Set([...prev, company.id]))
    setScoutCompanies((prev) =>
      prev.map((c) => c.id === company.id ? { ...c, crawl_status: 'crawling' } : c)
    )
    // Invalidate any cached contacts so the drawer re-fetches after crawl
    setContactsCache((prev) => { const n = { ...prev }; delete n[company.id]; return n })

    const res = await apiFetch(`/api/startup-scout/companies/${company.id}/crawl`, { method: 'POST' })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      toast({ title: 'Crawl failed to start', description: err.detail || 'Try again.', variant: 'destructive' })
      setScoutCompanies((prev) =>
        prev.map((c) => c.id === company.id ? { ...c, crawl_status: 'pending' } : c)
      )
      setCrawlingIds((prev) => { const n = new Set(prev); n.delete(company.id); return n })
      return
    }

    // Poll every 4s until status leaves 'crawling'
    crawlIntervalsRef.current[company.id] = setInterval(async () => {
      const r = await apiFetch(`/api/startup-scout/companies/${company.id}`)
      if (r.ok) {
        const updated: ScoutCompany = await r.json()
        setScoutCompanies((prev) => prev.map((c) => c.id === updated.id ? updated : c))
        if (updated.crawl_status !== 'crawling') {
          _clearCrawlInterval(company.id)
          setCrawlingIds((prev) => { const n = new Set(prev); n.delete(company.id); return n })
          setStoppingIds((prev) => { const n = new Set(prev); n.delete(company.id); return n })
          toast({
            title: updated.crawl_status === 'enriched' ? 'Contacts found!' : 'Crawl done',
            description: `${company.name} — ${updated.crawl_status}`,
          })
        }
      } else {
        _clearCrawlInterval(company.id)
        setCrawlingIds((prev) => { const n = new Set(prev); n.delete(company.id); return n })
        setStoppingIds((prev) => { const n = new Set(prev); n.delete(company.id); return n })
      }
    }, 4000)
  }

  async function stopCrawl(company: ScoutCompany) {
    setStoppingIds((prev) => new Set([...prev, company.id]))
    const res = await apiFetch(`/api/startup-scout/companies/${company.id}/stop`, { method: 'POST' })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      toast({ title: 'Could not stop crawl', description: err.detail || 'Try again.', variant: 'destructive' })
      setStoppingIds((prev) => { const n = new Set(prev); n.delete(company.id); return n })
    }
    // Poll continues — backend will update status once it halts naturally
  }

  async function deleteScoutCompany(id: string) {
    if (!confirm('Remove this company? This cannot be undone.')) return
    _clearCrawlInterval(id)
    const res = await apiFetch(`/api/startup-scout/companies/${id}`, { method: 'DELETE' })
    if (res.ok) {
      setScoutCompanies((prev) => prev.filter((c) => c.id !== id))
      setCrawlingIds((prev) => { const n = new Set(prev); n.delete(id); return n })
      setStoppingIds((prev) => { const n = new Set(prev); n.delete(id); return n })
      toast({ title: 'Company removed' })
    } else {
      toast({ title: 'Could not remove company', variant: 'destructive' })
    }
  }

  async function toggleContacts(companyId: string) {
    const nowOpen = !expandedContacts[companyId]
    setExpandedContacts((prev) => ({ ...prev, [companyId]: nowOpen }))
    if (nowOpen && !contactsCache[companyId]) {
      setContactsLoading((prev) => ({ ...prev, [companyId]: true }))
      const res = await apiFetch(`/api/startup-scout/companies/${companyId}/contacts`)
      if (res.ok) {
        const data = await res.json()
        setContactsCache((prev) => ({ ...prev, [companyId]: data }))
      }
      setContactsLoading((prev) => ({ ...prev, [companyId]: false }))
    }
  }

  function openCreate() {
    reset({ applied_at: today, status: 'Applied' })
    setEditing(null)
    setShowForm(true)
  }

  function openEdit(app: JobApplication) {
    reset({
      company: app.company, role: app.role, applied_at: app.applied_at, status: app.status,
      follow_up_date: app.follow_up_date || undefined,
      salary_min: app.salary_min || undefined, salary_max: app.salary_max || undefined,
      notes: app.notes || undefined,
    })
    setEditing(app)
    setShowForm(true)
  }

  async function onSubmit(data: FormData) {
    setSaving(true)
    const method = editing ? 'PUT' : 'POST'
    const url = editing ? `/api/tracker/${editing.id}` : '/api/tracker'
    const res = await apiFetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
    if (res.ok) {
      await fetchApplications()
      setShowForm(false)
      toast({ title: editing ? 'Application updated' : 'Application added' })
    } else {
      toast({ title: 'Error', description: 'Something went wrong', variant: 'destructive' })
    }
    setSaving(false)
  }

  async function deleteApp(id: string) {
    if (!confirm('Remove this application? This cannot be undone.')) return
    const res = await apiFetch(`/api/tracker/${id}`, { method: 'DELETE' })
    if (res.ok) {
      setApplications((prev) => prev.filter((a) => a.id !== id))
      toast({ title: 'Application removed' })
    } else {
      toast({ title: 'Could not remove application', variant: 'destructive' })
    }
  }

  async function updateLeadStatus(lead: StartupHuntSavedOpportunity, status: StartupHuntOpportunityStatus) {
    setUpdatingLeadId(lead.id)
    const res = await apiFetch(`/api/startup-hunt/opportunities/${lead.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ opportunity_status: status }),
    })
    if (res.ok) {
      setLeads((prev) => prev.map((l) => l.id === lead.id ? { ...l, opportunity_status: status } : l))
      toast({ title: 'Status updated' })
    } else {
      toast({ title: 'Could not update status', variant: 'destructive' })
    }
    setUpdatingLeadId(null)
  }

  async function deleteLead(id: string) {
    const res = await apiFetch(`/api/startup-hunt/opportunities/${id}`, { method: 'DELETE' })
    if (res.ok) {
      setLeads((prev) => prev.filter((l) => l.id !== id))
      setArtifactCounts((prev) => { const n = { ...prev }; delete n[id]; return n })
      toast({ title: 'Lead removed' })
    } else {
      toast({ title: 'Could not remove lead', variant: 'destructive' })
    }
  }

  async function toggleDocs(leadId: string) {
    const nowOpen = !expandedDocs[leadId]
    setExpandedDocs((prev) => ({ ...prev, [leadId]: nowOpen }))
    if (nowOpen && !docsCache[leadId]) {
      setDocsLoading((prev) => ({ ...prev, [leadId]: true }))
      const res = await apiFetch(`/api/startup-hunt/opportunities/${leadId}/artifacts`)
      if (res.ok) {
        const data: OpportunityArtifact[] = await res.json()
        setDocsCache((prev) => ({ ...prev, [leadId]: data }))
      }
      setDocsLoading((prev) => ({ ...prev, [leadId]: false }))
    }
  }

  async function deleteArtifact(leadId: string, artifactId: string) {
    const res = await apiFetch(`/api/startup-hunt/opportunities/${leadId}/artifacts/${artifactId}`, { method: 'DELETE' })
    if (res.ok) {
      setDocsCache((prev) => ({ ...prev, [leadId]: (prev[leadId] || []).filter((a) => a.id !== artifactId) }))
      setArtifactCounts((prev) => ({ ...prev, [leadId]: Math.max(0, (prev[leadId] || 1) - 1) }))
    }
  }

  const overdue = applications.filter((a) => isOverdue(a.follow_up_date) && !['Rejected', 'Withdrawn'].includes(a.status))
  const active = applications.filter((a) => !['Rejected', 'Withdrawn'].includes(a.status))
  const offers = applications.filter((a) => a.status === 'Offer')

  const filteredLeads = leadStatusFilter === 'all'
    ? leads.filter((l) => l.opportunity_status !== 'skipped')
    : leads.filter((l) => l.opportunity_status === leadStatusFilter)

  const leadCounts = LEAD_STATUS_ORDER.reduce((acc, s) => {
    acc[s] = leads.filter((l) => l.opportunity_status === s).length
    return acc
  }, {} as Record<StartupHuntOpportunityStatus, number>)

  return (
    <div className="animate-fade-in">
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-center gap-4">
          <div className="page-header-icon bg-indigo-100">
            <Briefcase className="h-5 w-5 text-indigo-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Follow-Up Tracker</h1>
            <p className="text-slate-500 text-sm mt-0.5">All your tracked applications and saved startup leads in one place</p>
          </div>
        </div>
        {tab === 'applications' && (
          <Button onClick={openCreate} className="gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90 transition-opacity rounded-xl h-10 px-5">
            <Plus className="h-4 w-4 mr-2" /> Add Application
          </Button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-100 rounded-xl p-1 w-fit mb-6">
        {([
          ['applications', Briefcase, 'Applications', applications.length, 'bg-indigo-100 text-indigo-700'],
          ['leads', Compass, 'Startup Leads', leads.length, 'bg-orange-100 text-orange-700'],
          ['scout', Radar, 'Startup Scout', scoutCompanies.length, 'bg-cyan-100 text-cyan-700'],
        ] as const).map(([id, Icon, label, count, badgeClass]) => (
          <button
            key={id}
            onClick={() => setTab(id as 'applications' | 'leads' | 'scout')}
            className={cn(
              'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-colors',
              tab === id ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
            <span className={cn('inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full text-xs font-bold',
              tab === id ? badgeClass : 'bg-slate-200 text-slate-600')}>
              {count}
            </span>
          </button>
        ))}
      </div>

      {/* ─── APPLICATIONS TAB ─── */}
      {tab === 'applications' && (
        <>
          <div className="grid grid-cols-4 gap-4 mb-6">
            {[
              { label: 'Total', value: applications.length, Icon: Briefcase, iconBg: 'bg-slate-100', iconColor: 'text-slate-600' },
              { label: 'Active', value: active.length, Icon: TrendingUp, iconBg: 'bg-blue-100', iconColor: 'text-blue-600' },
              { label: 'Overdue', value: overdue.length, Icon: AlertCircle, iconBg: 'bg-red-100', iconColor: 'text-red-600' },
              { label: 'Offers', value: offers.length, Icon: CheckCircle, iconBg: 'bg-emerald-100', iconColor: 'text-emerald-600' },
            ].map(({ label, value, Icon, iconBg, iconColor }) => (
              <div key={label} className="bg-white rounded-2xl border border-slate-100 shadow-card p-5 flex items-center gap-4">
                <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0', iconBg)}>
                  <Icon className={cn('h-5 w-5', iconColor)} />
                </div>
                <div>
                  <p className="text-2xl font-bold text-slate-900 leading-none">{value}</p>
                  <p className="text-xs text-slate-500 mt-1">{label}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="bg-white rounded-2xl border border-slate-100 shadow-card overflow-hidden">
            {appsLoading ? (
              <div className="flex items-center justify-center h-48">
                <div className="flex flex-col items-center gap-3">
                  <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
                  <p className="text-sm text-slate-400">Loading applications…</p>
                </div>
              </div>
            ) : applications.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-56">
                <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
                  <Briefcase className="h-7 w-7 text-slate-300" />
                </div>
                <p className="font-medium text-slate-600">No applications yet</p>
                <p className="text-sm text-slate-400 mt-1">Add your first one or track a lead from Startup Hunt</p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-50/50 border-b border-slate-100 hover:bg-slate-50/50">
                    {['Company', 'Role', 'Status', 'Applied', 'Follow-up', 'Salary'].map((h) => (
                      <TableHead key={h} className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</TableHead>
                    ))}
                    <TableHead className="w-20" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {applications.map((app) => {
                    const overdueRow = isOverdue(app.follow_up_date) && !['Rejected', 'Withdrawn'].includes(app.status)
                    return (
                      <TableRow key={app.id} className={cn('border-b border-slate-50 hover:bg-slate-50/50 transition-colors', overdueRow && 'bg-red-50/40 hover:bg-red-50/60')}>
                        <TableCell className="font-semibold text-slate-800">{app.company}</TableCell>
                        <TableCell className="text-slate-600">{app.role}</TableCell>
                        <TableCell>
                          <span className={cn('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium', STATUS_COLORS[app.status])}>{app.status}</span>
                        </TableCell>
                        <TableCell className="text-sm text-slate-500">{formatDate(app.applied_at)}</TableCell>
                        <TableCell>
                          {app.follow_up_date ? (
                            <span className={cn('flex items-center gap-1.5 text-sm', overdueRow ? 'text-red-600 font-medium' : 'text-slate-500')}>
                              {overdueRow && <Clock className="h-3 w-3" />}
                              {formatDate(app.follow_up_date)}
                            </span>
                          ) : <span className="text-slate-300 text-sm">—</span>}
                        </TableCell>
                        <TableCell className="text-sm text-slate-500">
                          {app.salary_min && app.salary_max
                            ? `${formatCurrency(app.salary_min)} – ${formatCurrency(app.salary_max)}`
                            : <span className="text-slate-300">—</span>}
                        </TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            <button
                              onClick={() => router.push(`/cover-letter?company=${encodeURIComponent(app.company)}&role=${encodeURIComponent(app.role)}`)}
                              title="Generate Cover Letter"
                              className="h-7 w-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-pink-600 hover:bg-pink-50 transition-colors"
                            >
                              <PenLine className="h-3.5 w-3.5" />
                            </button>
                            <button onClick={() => openEdit(app)} className="h-7 w-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors">
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                            <button onClick={() => deleteApp(app.id)} className="h-7 w-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors">
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            )}
          </div>
        </>
      )}

      {/* ─── STARTUP LEADS TAB ─── */}
      {tab === 'leads' && (
        <>
          <div className="grid grid-cols-4 gap-4 mb-6">
            {[
              { label: 'Saved', value: leadCounts.saved, classes: 'bg-slate-100 text-slate-600' },
              { label: 'Contacted', value: leadCounts.contacted, classes: 'bg-pink-100 text-pink-600' },
              { label: 'Applied', value: leadCounts.applied, classes: 'bg-emerald-100 text-emerald-600' },
              { label: 'Skipped', value: leadCounts.skipped, classes: 'bg-gray-100 text-gray-500' },
            ].map(({ label, value, classes }) => (
              <button
                key={label}
                onClick={() => setLeadStatusFilter(leadStatusFilter === label.toLowerCase() as StartupHuntOpportunityStatus ? 'all' : label.toLowerCase() as StartupHuntOpportunityStatus)}
                className={cn('bg-white rounded-2xl border shadow-card p-5 flex items-center gap-4 text-left transition-all hover:shadow-md',
                  leadStatusFilter === label.toLowerCase() ? 'border-indigo-300 ring-1 ring-indigo-200' : 'border-slate-100')}
              >
                <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 text-sm font-bold', classes)}>{value}</div>
                <div>
                  <p className="text-2xl font-bold text-slate-900 leading-none">{value}</p>
                  <p className="text-xs text-slate-500 mt-1">{label}</p>
                </div>
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2 mb-4">
            <span className="text-xs text-slate-500 font-medium">Filter:</span>
            {(['all', ...LEAD_STATUS_ORDER] as const).map((s) => (
              <button
                key={s}
                onClick={() => setLeadStatusFilter(s)}
                className={cn('px-3 py-1 rounded-full text-xs font-semibold border transition-colors',
                  leadStatusFilter === s ? 'bg-slate-900 text-white border-slate-900' : 'bg-white text-slate-600 border-slate-200 hover:border-slate-400')}
              >
                {s === 'all' ? `All (${leads.length})` : `${STARTUP_STATUS_META[s].label} (${leadCounts[s]})`}
              </button>
            ))}
          </div>

          <div className="bg-white rounded-2xl border border-slate-100 shadow-card overflow-hidden">
            {leadsLoading ? (
              <div className="flex items-center justify-center h-48">
                <div className="flex flex-col items-center gap-3">
                  <Loader2 className="h-8 w-8 animate-spin text-orange-400" />
                  <p className="text-sm text-slate-400">Loading startup leads…</p>
                </div>
              </div>
            ) : filteredLeads.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-56">
                <div className="w-14 h-14 rounded-2xl bg-orange-50 flex items-center justify-center mb-4">
                  <Compass className="h-7 w-7 text-orange-200" />
                </div>
                <p className="font-medium text-slate-600">No leads here yet</p>
                <p className="text-sm text-slate-400 mt-1">
                  {leadStatusFilter === 'all' ? 'Save opportunities from Startup Hunt to see them here' : `No ${leadStatusFilter} leads.`}
                </p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-50/50 border-b border-slate-100 hover:bg-slate-50/50">
                    {['Company', 'Role', 'Location', 'Source', 'Status', 'Score', 'Docs', 'Saved'].map((h) => (
                      <TableHead key={h} className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</TableHead>
                    ))}
                    <TableHead className="w-28" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredLeads.map((lead) => {
                    const applyUrl = lead.direct_apply_url || lead.company_careers_url || lead.portal_job_url || lead.company_website_url
                    const isUpdating = updatingLeadId === lead.id
                    const docCount = artifactCounts[lead.id] || 0
                    const docsOpen = Boolean(expandedDocs[lead.id])
                    const artifacts = docsCache[lead.id] || []
                    const docsAreLoading = docsLoading[lead.id]

                    return (
                      <React.Fragment key={lead.id}>
                        <TableRow className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors">
                          <TableCell className="font-semibold text-slate-800">
                            {lead.company_website_url ? (
                              <Link href={lead.company_website_url} target="_blank" className="hover:text-indigo-600 hover:underline transition-colors">{lead.company_name}</Link>
                            ) : lead.company_name}
                          </TableCell>
                          <TableCell className="text-slate-600 text-sm max-w-[180px] truncate">{lead.role_title}</TableCell>
                          <TableCell>
                            <span className="flex items-center gap-1 text-xs text-slate-500">
                              <MapPin className="h-3 w-3 flex-shrink-0" />{lead.location}
                            </span>
                          </TableCell>
                          <TableCell>
                            <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-semibold bg-orange-50 text-orange-700 border border-orange-100">
                              {lead.source_name}
                            </span>
                          </TableCell>
                          <TableCell>
                            <Select value={lead.opportunity_status} onValueChange={(v) => updateLeadStatus(lead, v as StartupHuntOpportunityStatus)} disabled={isUpdating}>
                              <SelectTrigger className={cn('h-7 text-xs rounded-full border-0 px-2.5 py-0.5 font-semibold w-auto gap-1', STARTUP_STATUS_META[lead.opportunity_status].classes)}>
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {LEAD_STATUS_ORDER.map((s) => (
                                  <SelectItem key={s} value={s} className="text-xs">{STARTUP_STATUS_META[s].label}</SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </TableCell>
                          <TableCell>
                            <span className="text-xs font-semibold text-indigo-600">{lead.score_total.toFixed(1)}</span>
                          </TableCell>
                          <TableCell>
                            <button
                              onClick={() => toggleDocs(lead.id)}
                              className={cn(
                                'flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold border transition-colors',
                                docCount > 0
                                  ? 'bg-violet-50 text-violet-700 border-violet-200 hover:bg-violet-100'
                                  : 'bg-slate-50 text-slate-400 border-slate-200 hover:bg-slate-100'
                              )}
                            >
                              <FileText className="h-3 w-3" />
                              {docCount}
                              {docsOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                            </button>
                          </TableCell>
                          <TableCell className="text-xs text-slate-400">{formatDate(lead.created_at)}</TableCell>
                          <TableCell>
                            <div className="flex gap-1 justify-end">
                              {applyUrl && (
                                <Link href={applyUrl} target="_blank">
                                  <button className="h-7 px-2 rounded-lg flex items-center gap-1 text-xs text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 transition-colors font-medium border border-slate-200 hover:border-indigo-200">
                                    <ExternalLink className="h-3 w-3" />
                                    {lead.direct_apply_url ? 'Apply' : lead.company_careers_url ? 'Careers' : 'Open'}
                                  </button>
                                </Link>
                              )}

                              {/* Actions dropdown */}
                              <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                  <button className="h-7 w-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors border border-slate-200">
                                    <MoreHorizontal className="h-3.5 w-3.5" />
                                  </button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end" className="w-48">
                                  <DropdownMenuLabel>Use with tools</DropdownMenuLabel>
                                  <DropdownMenuItem onClick={() => router.push(`/resume-tailor?opportunity_id=${lead.id}`)}>
                                    <FileSearch className="h-3.5 w-3.5 text-violet-500" />
                                    Resume Tailor
                                  </DropdownMenuItem>
                                  <DropdownMenuItem onClick={() => router.push(`/cover-letter?opportunity_id=${lead.id}`)}>
                                    <PenLine className="h-3.5 w-3.5 text-pink-500" />
                                    Cover Letter
                                  </DropdownMenuItem>
                                  <DropdownMenuItem onClick={() => router.push(`/interview-prep?opportunity_id=${lead.id}`)}>
                                    <MessageSquare className="h-3.5 w-3.5 text-teal-500" />
                                    Interview Prep
                                  </DropdownMenuItem>
                                  <DropdownMenuSeparator />
                                  {lead.opportunity_kind === 'outreach_lead' && (
                                    <DropdownMenuItem onClick={() => updateLeadStatus(lead, 'contacted')} disabled={lead.opportunity_status === 'contacted'}>
                                      <Mail className="h-3.5 w-3.5 text-pink-400" />
                                      Mark Contacted
                                    </DropdownMenuItem>
                                  )}
                                  <DropdownMenuItem onClick={() => deleteLead(lead.id)} className="text-red-600 focus:text-red-600 focus:bg-red-50">
                                    <Trash2 className="h-3.5 w-3.5" />
                                    Remove Lead
                                  </DropdownMenuItem>
                                </DropdownMenuContent>
                              </DropdownMenu>
                            </div>
                          </TableCell>
                        </TableRow>

                        {/* Documents panel */}
                        {docsOpen && (
                          <tr key={`${lead.id}-docs`} className="bg-slate-50/60 border-b border-slate-100">
                            <td colSpan={9} className="px-5 py-4">
                              {docsAreLoading ? (
                                <div className="flex items-center gap-2 text-sm text-slate-400">
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading documents…
                                </div>
                              ) : artifacts.length === 0 ? (
                                <div className="flex items-center gap-3">
                                  <p className="text-sm text-slate-400">No documents yet. Use the Actions menu to generate one.</p>
                                  <div className="flex gap-2">
                                    {(['resume-tailor', 'cover-letter', 'interview-prep'] as const).map((tool) => {
                                      const meta = Object.values(ARTIFACT_META).find((m) => m.tool === tool)!
                                      return (
                                        <button
                                          key={tool}
                                          onClick={() => router.push(`/${tool}?opportunity_id=${lead.id}`)}
                                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-white border border-slate-200 text-slate-600 hover:border-indigo-300 hover:text-indigo-600 transition-colors"
                                        >
                                          <meta.icon className={cn('h-3 w-3', meta.color)} />
                                          {meta.label}
                                        </button>
                                      )
                                    })}
                                  </div>
                                </div>
                              ) : (
                                <div className="space-y-2">
                                  <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Generated Documents</p>
                                  <div className="grid grid-cols-3 gap-3">
                                    {artifacts.map((artifact) => {
                                      const meta = ARTIFACT_META[artifact.artifact_type] || ARTIFACT_META.cover_letter
                                      const preview = artifact.artifact_type === 'cover_letter'
                                        ? artifact.content.slice(0, 120) + '…'
                                        : artifact.artifact_type === 'resume_analysis'
                                          ? (() => { try { const p = JSON.parse(artifact.content); return `ATS Score: ${p.match_score}% · ${p.matched_keywords?.length ?? 0} matched keywords` } catch { return artifact.content.slice(0, 80) } })()
                                          : (() => { try { const qs = JSON.parse(artifact.content); return `${qs.length} interview questions generated` } catch { return artifact.content.slice(0, 80) } })()
                                      return (
                                        <div key={artifact.id} className="bg-white rounded-xl border border-slate-200 p-3 space-y-2">
                                          <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-1.5">
                                              <meta.icon className={cn('h-3.5 w-3.5', meta.color)} />
                                              <span className="text-xs font-semibold text-slate-700">{meta.label}</span>
                                            </div>
                                            <button onClick={() => deleteArtifact(lead.id, artifact.id)} className="text-slate-300 hover:text-red-400 transition-colors">
                                              <Trash2 className="h-3 w-3" />
                                            </button>
                                          </div>
                                          <p className="text-xs text-slate-500 leading-relaxed">{preview}</p>
                                          <div className="flex items-center justify-between">
                                            <span className="text-[10px] text-slate-400">{formatDate(artifact.created_at)}</span>
                                            <button
                                              onClick={() => router.push(`/${meta.tool}?opportunity_id=${lead.id}`)}
                                              className="text-[10px] font-semibold text-indigo-600 hover:underline"
                                            >
                                              Open in {meta.label} →
                                            </button>
                                          </div>
                                        </div>
                                      )
                                    })}
                                  </div>
                                </div>
                              )}
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    )
                  })}
                </TableBody>
              </Table>
            )}
          </div>
        </>
      )}

      {/* ─── STARTUP SCOUT TAB ─── */}
      {tab === 'scout' && (
        <>
          <div className="grid grid-cols-3 gap-4 mb-6">
            {[
              { label: 'Saved', value: scoutCompanies.filter((c) => c.crawl_status === 'pending').length, classes: 'bg-slate-100 text-slate-600' },
              { label: 'Enriched', value: scoutCompanies.filter((c) => c.crawl_status === 'enriched').length, classes: 'bg-emerald-100 text-emerald-600' },
              { label: 'Partial / Failed', value: scoutCompanies.filter((c) => ['partial', 'failed'].includes(c.crawl_status)).length, classes: 'bg-orange-100 text-orange-600' },
            ].map(({ label, value, classes }) => (
              <div key={label} className="bg-white rounded-2xl border border-slate-100 shadow-card p-5 flex items-center gap-4">
                <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 text-sm font-bold', classes)}>{value}</div>
                <div>
                  <p className="text-2xl font-bold text-slate-900 leading-none">{value}</p>
                  <p className="text-xs text-slate-500 mt-1">{label}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="bg-white rounded-2xl border border-slate-100 shadow-card overflow-hidden">
            {scoutLoading ? (
              <div className="flex items-center justify-center h-48">
                <div className="flex flex-col items-center gap-3">
                  <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
                  <p className="text-sm text-slate-400">Loading scout companies…</p>
                </div>
              </div>
            ) : scoutCompanies.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-56">
                <div className="w-14 h-14 rounded-2xl bg-cyan-50 flex items-center justify-center mb-4">
                  <Radar className="h-7 w-7 text-cyan-200" />
                </div>
                <p className="font-medium text-slate-600">No companies saved yet</p>
                <p className="text-sm text-slate-400 mt-1">
                  <button onClick={() => router.push('/startup-scout')} className="text-cyan-600 hover:underline font-medium">
                    Go to Startup Scout
                  </button>
                  {' '}to discover and save startups.
                </p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-50/50 border-b border-slate-100 hover:bg-slate-50/50">
                    {['Company', 'Stage', 'Location', 'Status', 'Contacts', 'Added'].map((h) => (
                      <TableHead key={h} className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</TableHead>
                    ))}
                    <TableHead className="w-28" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {scoutCompanies.map((company) => {
                    const statusMeta = SCOUT_STATUS_META[company.crawl_status]
                    const isCrawling = company.crawl_status === 'crawling' || crawlingIds.has(company.id)
                    const isStopping = stoppingIds.has(company.id)
                    const canCrawl = ['pending', 'partial', 'failed'].includes(company.crawl_status) && !crawlingIds.has(company.id)
                    const contactsOpen = Boolean(expandedContacts[company.id])
                    const contacts = contactsCache[company.id] || []
                    const contactsAreLoading = contactsLoading[company.id]
                    const hasContacts = company.crawl_status === 'enriched' || company.crawl_status === 'partial'

                    return (
                      <React.Fragment key={company.id}>
                        <TableRow className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors">
                          <TableCell className="font-semibold text-slate-800">
                            {company.website ? (
                              <Link href={company.website} target="_blank" className="hover:text-cyan-600 hover:underline transition-colors">
                                {company.name}
                              </Link>
                            ) : company.name}
                            {company.description && (
                              <p className="text-xs text-slate-400 font-normal mt-0.5 max-w-[220px] truncate">{company.description}</p>
                            )}
                          </TableCell>
                          <TableCell>
                            {company.funding_stage ? (
                              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-100">
                                {company.funding_stage}
                              </span>
                            ) : <span className="text-slate-300 text-sm">—</span>}
                          </TableCell>
                          <TableCell>
                            {company.location ? (
                              <span className="flex items-center gap-1 text-xs text-slate-500">
                                <MapPin className="h-3 w-3 flex-shrink-0" />{company.location}
                              </span>
                            ) : <span className="text-slate-300 text-sm">—</span>}
                          </TableCell>
                          <TableCell>
                            <span className={cn('inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold', statusMeta.classes)}>
                              {isCrawling && <Loader2 className="h-2.5 w-2.5 animate-spin" />}
                              {statusMeta.label}
                            </span>
                          </TableCell>
                          <TableCell>
                            {hasContacts ? (
                              <button
                                onClick={() => toggleContacts(company.id)}
                                className={cn(
                                  'flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold border transition-colors',
                                  contactsOpen
                                    ? 'bg-cyan-50 text-cyan-700 border-cyan-200 hover:bg-cyan-100'
                                    : 'bg-slate-50 text-slate-500 border-slate-200 hover:bg-slate-100'
                                )}
                              >
                                <Users className="h-3 w-3" />
                                {contactsOpen ? 'Hide' : 'View'}
                                {contactsOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                              </button>
                            ) : (
                              <span className="text-slate-300 text-xs">—</span>
                            )}
                          </TableCell>
                          <TableCell className="text-xs text-slate-400">{formatDate(company.created_at)}</TableCell>
                          <TableCell>
                            <div className="flex gap-1 justify-end">
                              {isCrawling && (
                                <button
                                  onClick={() => stopCrawl(company)}
                                  disabled={isStopping}
                                  className="h-7 px-2.5 rounded-lg flex items-center gap-1 text-xs font-semibold text-red-700 bg-red-50 hover:bg-red-100 border border-red-200 transition-colors disabled:opacity-50"
                                >
                                  {isStopping
                                    ? <Loader2 className="h-3 w-3 animate-spin" />
                                    : <StopCircle className="h-3 w-3" />}
                                  {isStopping ? 'Stopping…' : 'Stop'}
                                </button>
                              )}
                              {canCrawl && (
                                <button
                                  onClick={() => startCrawl(company)}
                                  className="h-7 px-2.5 rounded-lg flex items-center gap-1 text-xs font-semibold text-cyan-700 bg-cyan-50 hover:bg-cyan-100 border border-cyan-200 transition-colors"
                                >
                                  <Radar className="h-3 w-3" />
                                  {company.crawl_status === 'pending' ? 'Start Crawl' : 'Re-crawl'}
                                </button>
                              )}
                              {company.website && (
                                <Link href={company.website} target="_blank">
                                  <button className="h-7 w-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors">
                                    <Globe className="h-3.5 w-3.5" />
                                  </button>
                                </Link>
                              )}
                              <button
                                onClick={() => deleteScoutCompany(company.id)}
                                className="h-7 w-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          </TableCell>
                        </TableRow>

                        {/* Contacts panel */}
                        {contactsOpen && (
                          <tr key={`${company.id}-contacts`} className="bg-slate-50/60 border-b border-slate-100">
                            <td colSpan={7} className="px-5 py-4">
                              {contactsAreLoading ? (
                                <div className="flex items-center gap-2 text-sm text-slate-400">
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading contacts…
                                </div>
                              ) : contacts.length === 0 ? (
                                <p className="text-sm text-slate-400">No contacts found. Try re-crawling.</p>
                              ) : (
                                <div className="grid grid-cols-2 gap-3">
                                  {contacts.map((contact) => (
                                    <div key={contact.id} className="bg-white rounded-xl border border-slate-200 p-3 flex items-start gap-3">
                                      <div className="w-8 h-8 rounded-full bg-cyan-100 flex items-center justify-center flex-shrink-0 text-xs font-bold text-cyan-700">
                                        {(contact.name || '?')[0].toUpperCase()}
                                      </div>
                                      <div className="min-w-0 flex-1">
                                        <p className="text-sm font-semibold text-slate-800 truncate">{contact.name}</p>
                                        {contact.title && <p className="text-xs text-slate-500 truncate">{contact.title}</p>}
                                        <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                                          {contact.email && (
                                            <a href={`mailto:${contact.email}`} className="text-xs text-indigo-600 hover:underline truncate">
                                              {contact.email}
                                            </a>
                                          )}
                                          {contact.linkedin_url && (
                                            <Link href={contact.linkedin_url} target="_blank" className="flex items-center gap-0.5 text-xs text-blue-600 hover:underline">
                                              <Linkedin className="h-3 w-3" /> LinkedIn
                                            </Link>
                                          )}
                                          <span className={cn(
                                            'inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold',
                                            contact.source === 'apollo' ? 'bg-violet-50 text-violet-700' : 'bg-slate-100 text-slate-500'
                                          )}>
                                            {contact.source}
                                          </span>
                                        </div>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    )
                  })}
                </TableBody>
              </Table>
            )}
          </div>
        </>
      )}

      {/* Add/Edit Application Dialog */}
      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-lg rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold">{editing ? 'Edit Application' : 'Add Application'}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Company</Label>
                <Input placeholder="Acme Corp" className="rounded-xl" {...register('company')} />
                {errors.company && <p className="text-xs text-destructive">{errors.company.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Role</Label>
                <Input placeholder="Software Engineer" className="rounded-xl" {...register('role')} />
                {errors.role && <p className="text-xs text-destructive">{errors.role.message}</p>}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Applied date</Label>
                <Input type="date" className="rounded-xl" {...register('applied_at')} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Status</Label>
                <Select value={watchStatus} onValueChange={(v) => setValue('status', v as ApplicationStatus)}>
                  <SelectTrigger className="rounded-xl"><SelectValue /></SelectTrigger>
                  <SelectContent>{APPLICATION_STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-sm font-medium">Follow-up date</Label>
              <Input type="date" className="rounded-xl" {...register('follow_up_date')} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Salary min ($)</Label>
                <Input type="number" placeholder="80000" className="rounded-xl" {...register('salary_min')} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Salary max ($)</Label>
                <Input type="number" placeholder="120000" className="rounded-xl" {...register('salary_max')} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-sm font-medium">Notes</Label>
              <Textarea rows={3} placeholder="Any notes about this application…" className="rounded-xl resize-none" {...register('notes')} />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowForm(false)} className="rounded-xl">Cancel</Button>
              <Button type="submit" disabled={saving} className="gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90 transition-opacity rounded-xl">
                {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {editing ? 'Save Changes' : 'Add Application'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
