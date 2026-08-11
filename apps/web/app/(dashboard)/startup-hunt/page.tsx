'use client'

import Link from 'next/link'
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Button } from '@jobnok/ui'
import { Input } from '@jobnok/ui'
import { Label } from '@jobnok/ui'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@jobnok/ui'
import { Textarea } from '@jobnok/ui'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@jobnok/ui'
import { useToast } from '@jobnok/ui'
import { apiFetch, apiGet } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { config } from '@/lib/config'
import { formatDate } from '@jobnok/ui'
import { StartupHuntResponse, StartupHuntResult, StartupHuntSource, StartupHuntSourceType } from '@/lib/types'
import {
  Building2,
  ChevronDown,
  ChevronUp,
  Compass,
  ExternalLink,
  Info,
  ListPlus,
  Loader2,
  Mail,
  MapPin,
  Plus,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  UserRound,
} from 'lucide-react'

const schema = z.object({
  query: z.string().min(2, 'Enter a target AI/ML role'),
  location: z.string().min(2, 'Enter a target location'),
  country: z.string().optional(),
  posted_within_hours: z.coerce.number().int().min(1).max(1440),
  result_limit: z.coerce.number().int().min(1).max(50),
  include_seeded_sources: z.enum(['false', 'true']).default('false'),
  remote_only: z.enum(['false', 'true']).default('false'),
  direct_links_only: z.enum(['false', 'true']).default('false'),
  english_friendly_only: z.enum(['false', 'true']).default('false'),
  company_stage: z.string().optional(),
  strategy_prompt: z.string().optional(),
  crawler_enabled: z.enum(['false', 'true']).default('false'),
  startupmap_enabled: z.enum(['false', 'true']).default('false'),
  web_enabled: z.enum(['false', 'true']).default('false'),
  indeed_enabled: z.enum(['false', 'true']).default('false'),
  theirstack_enabled: z.enum(['false', 'true']).default('true'),
  apify_enabled: z.enum(['false', 'true']).default('false'),
  ats_enabled: z.enum(['false', 'true']).default('true'),
  seeded_limit: z.coerce.number().int().min(0).max(50),
  crawler_limit: z.coerce.number().int().min(0).max(50),
  startupmap_limit: z.coerce.number().int().min(0).max(50),
  web_limit: z.coerce.number().int().min(0).max(50),
  indeed_limit: z.coerce.number().int().min(0).max(50),
  theirstack_limit: z.coerce.number().int().min(0).max(50),
  apify_limit: z.coerce.number().int().min(0).max(50),
  ats_limit: z.coerce.number().int().min(0).max(50),
})

type FormData = z.infer<typeof schema>
type ProviderBucket = 'crawler' | 'startupmap' | 'web' | 'indeed' | 'theirstack' | 'apify' | 'ats'

const DEFAULT_VALUES: FormData = {
  query: 'AI/ML Engineer',
  location: 'Berlin, Munich, Hamburg, Frankfurt, Cologne, Remote',
  country: 'Germany',
  posted_within_hours: 168,
  result_limit: 30,
  include_seeded_sources: 'false',
  remote_only: 'false',
  direct_links_only: 'false',
  english_friendly_only: 'false',
  company_stage: '',
  strategy_prompt: 'applied ai engineer, mid-level, 3+ years experience, not senior/staff/principal, early-stage, founder-led, english friendly, relocation friendly, modern AI stack (LLMs, RAG, agents, FastAPI, MLOps), fresh hiring momentum, avoid recruiters and large enterprises.',
  crawler_enabled: 'false',
  startupmap_enabled: 'false',
  web_enabled: 'false',
  indeed_enabled: 'false',
  theirstack_enabled: 'true',
  apify_enabled: 'false',
  ats_enabled: 'true',
  seeded_limit: 0,
  crawler_limit: 0,
  startupmap_limit: 0,
  web_limit: 0,
  indeed_limit: 0,
  theirstack_limit: 15,
  apify_limit: 0,
  ats_limit: 15,
}

const labelClasses: Record<string, string> = {
  Fresh: 'bg-green-100 text-green-900 hover:bg-green-100',
  'Direct Apply': 'bg-blue-100 text-blue-900 hover:bg-blue-100',
  'Hidden Gem': 'bg-amber-100 text-amber-900 hover:bg-amber-100',
  'Outreach Friendly': 'bg-pink-100 text-pink-900 hover:bg-pink-100',
  'Germany Match': 'bg-slate-100 text-slate-900 hover:bg-slate-100',
  'AI/ML Fit': 'bg-violet-100 text-violet-900 hover:bg-violet-100',
}

const SOURCE_DIAGNOSTIC_ORDER: ProviderBucket[] = ['ats', 'theirstack']

const PROVIDER_META: Record<ProviderBucket, { label: string; enabledField: keyof FormData; limitField: keyof FormData; hint: string }> = {
  crawler: { label: 'Crawler', enabledField: 'crawler_enabled', limitField: 'crawler_limit', hint: 'Curated watchlist and seeded startup sources.' },
  startupmap: { label: 'StartupMap', enabledField: 'startupmap_enabled', limitField: 'startupmap_limit', hint: 'Directory-style startup discovery for the chosen city.' },
  web: { label: 'Web', enabledField: 'web_enabled', limitField: 'web_limit', hint: 'Search-based discovery and company-page fallback leads.' },
  indeed: { label: 'Indeed', enabledField: 'indeed_enabled', limitField: 'indeed_limit', hint: 'Apify-powered Indeed role discovery.' },
  theirstack: { label: 'TheirStack', enabledField: 'theirstack_enabled', limitField: 'theirstack_limit', hint: 'Credit-capped API search for startup hiring results.' },
  apify: { label: 'Apify', enabledField: 'apify_enabled', limitField: 'apify_limit', hint: 'Optional startup actor for extra discovery breadth.' },
  ats: { label: 'ATS', enabledField: 'ats_enabled', limitField: 'ats_limit', hint: 'Direct ATS board and careers-page discovery.' },
}

function bucketLabel(bucket: string) {
  return PROVIDER_META[bucket as ProviderBucket]?.label || bucket
}

const USER_SOURCE_TYPES: { value: StartupHuntSourceType; label: string; hint: string }[] = [
  { value: 'greenhouse', label: 'Greenhouse', hint: 'Board slug from boards.greenhouse.io/<slug>' },
  { value: 'lever', label: 'Lever', hint: 'Board slug from jobs.lever.co/<slug>' },
  { value: 'ashby', label: 'Ashby', hint: 'Board slug from jobs.ashbyhq.com/<slug>' },
  { value: 'startup_company', label: 'Company to watch', hint: 'A general company/startup lead, no ATS board' },
]

const sourceSchema = z.object({
  type: z.enum(['greenhouse', 'lever', 'ashby', 'startup_company']),
  name: z.string().min(1, 'Required'),
  company: z.string().optional(),
  slug: z.string().optional(),
  url: z.string().optional(),
})
type SourceFormData = z.infer<typeof sourceSchema>

function compactReasons(reasons: string[]) {
  return reasons.slice(0, 2)
}

export default function StartupHuntPage() {
  const [loading, setLoading] = useState(false)
  const [savingId, setSavingId] = useState<string | null>(null)
  const [results, setResults] = useState<StartupHuntResult[]>([])
  const [overflowResults, setOverflowResults] = useState<StartupHuntResult[]>([])
  const [filteredOut, setFilteredOut] = useState<StartupHuntResponse['filtered_out']>([])
  const [parsedStrategy, setParsedStrategy] = useState<StartupHuntResponse['parsed_strategy'] | null>(null)
  const [sourceCount, setSourceCount] = useState(0)
  const [sourceResultCounts, setSourceResultCounts] = useState<Record<string, number>>({})
  const [sourceDiagnostics, setSourceDiagnostics] = useState<StartupHuntResponse['source_diagnostics']>({})
  const [expandedCards, setExpandedCards] = useState<Record<string, boolean>>({})
  const [error, setError] = useState<string | null>(null)
  const { toast } = useToast()

  const { register, handleSubmit, setValue, watch, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: DEFAULT_VALUES,
  })

  // ── My Sources dialog ──────────────────────────────────────────────
  const queryClient = useQueryClient()
  const [sourcesOpen, setSourcesOpen] = useState(false)
  const { data: sources = [], isLoading: sourcesLoading } = useQuery({
    queryKey: queryKeys.startupHuntSources,
    queryFn: () => apiGet<StartupHuntSource[]>('/api/startup-hunt/sources'),
    enabled: sourcesOpen,
  })
  const [addingSource, setAddingSource] = useState(false)
  const [deletingSourceId, setDeletingSourceId] = useState<string | null>(null)

  const {
    register: registerSource,
    handleSubmit: handleSubmitSource,
    reset: resetSourceForm,
    setValue: setSourceValue,
    watch: watchSource,
    formState: { errors: sourceErrors },
  } = useForm<SourceFormData>({
    resolver: zodResolver(sourceSchema),
    defaultValues: { type: 'greenhouse', name: '', company: '', slug: '', url: '' },
  })

  function openSources() {
    setSourcesOpen(true)
  }

  async function onAddSource(data: SourceFormData) {
    setAddingSource(true)
    const res = await apiFetch('/api/startup-hunt/sources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: data.type,
        name: data.name.trim(),
        company: data.company?.trim() || undefined,
        slug: data.slug?.trim() || undefined,
        url: data.url?.trim() || undefined,
      }),
    })
    const json = await res.json()
    if (!res.ok) {
      toast({ title: 'Could not add source', description: json.detail || 'Please check the fields and try again.', variant: 'destructive' })
      setAddingSource(false)
      return
    }
    queryClient.setQueryData<StartupHuntSource[]>(queryKeys.startupHuntSources, (prev) => [json, ...(prev || [])])
    resetSourceForm({ type: data.type, name: '', company: '', slug: '', url: '' })
    toast({ title: 'Source added', description: 'It will be included in your next search.' })
    setAddingSource(false)
  }

  async function deleteSource(id: string) {
    setDeletingSourceId(id)
    const res = await apiFetch(`/api/startup-hunt/sources/${id}`, { method: 'DELETE' })
    if (res.ok) {
      queryClient.setQueryData<StartupHuntSource[]>(queryKeys.startupHuntSources, (prev) => (prev || []).filter((s) => s.id !== id))
      toast({ title: 'Source removed' })
    } else {
      toast({ title: 'Could not remove source', variant: 'destructive' })
    }
    setDeletingSourceId(null)
  }

  async function onSubmit(data: FormData) {
    setLoading(true)
    setError(null)
    try {
      const res = await apiFetch('/api/startup-hunt/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...data,
          country: data.country?.trim() || null,
          company_stage: data.company_stage?.trim() || null,
          include_seeded_sources: data.include_seeded_sources === 'true',
          remote_only: data.remote_only === 'true',
          direct_links_only: data.direct_links_only === 'true',
          english_friendly_only: data.english_friendly_only === 'true',
          strategy_prompt: data.strategy_prompt?.trim() || null,
          crawler_enabled: data.crawler_enabled === 'true',
          startupmap_enabled: data.startupmap_enabled === 'true',
          web_enabled: data.web_enabled === 'true',
          indeed_enabled: data.indeed_enabled === 'true',
          theirstack_enabled: data.theirstack_enabled === 'true',
          apify_enabled: data.apify_enabled === 'true',
          ats_enabled: data.ats_enabled === 'true',
        }),
      })
      const json = await res.json()
      if (!res.ok) {
        setError(json.detail || 'Search failed. Please try again.')
        setResults([])
        setOverflowResults([])
        setFilteredOut([])
        setParsedStrategy(null)
        setSourceCount(0)
        setSourceResultCounts({})
        setSourceDiagnostics({})
        setExpandedCards({})
        return
      }
      const payload = json as StartupHuntResponse
      const diagnostics = payload.source_diagnostics || {}
      const enabledProviders = Object.values(diagnostics).filter((diagnostic) => diagnostic?.enabled).length
      setResults(payload.results)
      setOverflowResults(payload.overflow_results || [])
      setFilteredOut(payload.filtered_out || [])
      setParsedStrategy(payload.parsed_strategy)
      setSourceCount(enabledProviders || payload.configured_source_count)
      setSourceResultCounts(payload.source_result_counts || {})
      setSourceDiagnostics(diagnostics)
      setExpandedCards({})
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  async function saveOpportunity(job: StartupHuntResult, status: 'saved' | 'applied' | 'contacted') {
    const key = job.canonical_job_url || `${job.company_name}-${job.role_title}-${job.location}`
    setSavingId(key)
    try {
      const res = await apiFetch('/api/startup-hunt/opportunities', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company_name: job.company_name,
          company_domain: job.company_domain,
          company_website_url: job.company_website_url,
          company_careers_url: job.company_careers_url,
          role_title: job.role_title,
          location: job.location,
          country: job.country,
          source_name: job.source_name,
          source_type: job.source_type,
          direct_apply_url: job.direct_apply_url,
          canonical_job_url: job.canonical_job_url,
          portal_job_url: job.portal_job_url,
          posted_at: job.posted_at,
          discovered_at: new Date().toISOString(),
          opportunity_kind: job.opportunity_kind,
          opportunity_status: status,
          score_total: job.score_total,
          score_labels: job.score_labels,
          score_reasons: job.score_reasons,
          citation_payload: job.citation,
          company_payload: job.company,
          search_context: {
            query: watch('query'),
            location: watch('location'),
            country: watch('country') || null,
            posted_within_hours: watch('posted_within_hours'),
            include_seeded_sources: watch('include_seeded_sources') === 'true',
            direct_links_only: watch('direct_links_only') === 'true',
            english_friendly_only: watch('english_friendly_only') === 'true',
            company_stage: watch('company_stage') || null,
            strategy_prompt: watch('strategy_prompt') || null,
            crawler_enabled: watch('crawler_enabled') === 'true',
            startupmap_enabled: watch('startupmap_enabled') === 'true',
            web_enabled: watch('web_enabled') === 'true',
            indeed_enabled: watch('indeed_enabled') === 'true',
            theirstack_enabled: watch('theirstack_enabled') === 'true',
            apify_enabled: watch('apify_enabled') === 'true',
            ats_enabled: watch('ats_enabled') === 'true',
            seeded_limit: watch('seeded_limit'),
            crawler_limit: watch('crawler_limit'),
            startupmap_limit: watch('startupmap_limit'),
            web_limit: watch('web_limit'),
            indeed_limit: watch('indeed_limit'),
            theirstack_limit: watch('theirstack_limit'),
            apify_limit: watch('apify_limit'),
            ats_limit: watch('ats_limit'),
          },
          contacts: job.contacts,
        }),
      })
      const json = await res.json()
      if (!res.ok) {
        toast({ title: 'Could not save opportunity', description: json.detail || 'Please try again.', variant: 'destructive' })
        return
      }
      setResults((prev) => prev.map((item) => {
        const itemKey = item.canonical_job_url || `${item.company_name}-${item.role_title}-${item.location}`
        if (itemKey !== key) return item
        return {
          ...item,
          saved: true,
          saved_status: status,
          saved_opportunity_id: json.id,
        }
      }))
      setOverflowResults((prev) => prev.map((item) => {
        const itemKey = item.canonical_job_url || `${item.company_name}-${item.role_title}-${item.location}`
        if (itemKey !== key) return item
        return {
          ...item,
          saved: true,
          saved_status: status,
          saved_opportunity_id: json.id,
        }
      }))
      toast({
        title: status === 'applied' ? 'Application tracked' : status === 'contacted' ? 'Lead marked contacted' : 'Opportunity saved',
        description: status === 'applied'
          ? 'This role is now synced to your Follow-Up Tracker.'
          : 'Saved inside Startup Hunt for follow-up.',
      })
    } catch {
      toast({ title: 'Could not save opportunity', description: 'Network error. Please try again.', variant: 'destructive' })
    } finally {
      setSavingId(null)
    }
  }

  function toggleExpanded(key: string) {
    setExpandedCards((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  const rankedResultsWithBands = results.map((result, index) => {
    const bucket = (result.source_bucket || 'crawler') as ProviderBucket
    const previousBucket = index > 0 ? ((results[index - 1].source_bucket || 'crawler') as ProviderBucket) : null
    return {
      result,
      bucket,
      showBand: index === 0 || previousBucket !== bucket,
    }
  })

  return (
    <div className="animate-fade-in">
      <div className="flex items-start justify-between gap-4 mb-6">
        <div className="flex items-center gap-4">
          <div className="page-header-icon bg-orange-100">
            <Compass className="h-5 w-5 text-orange-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Startup Hunt</h1>
            <p className="text-slate-500 text-sm mt-0.5">
              Hunt AI/ML startup roles in Germany, surface hidden gems, and save founder-friendly outreach leads
            </p>
          </div>
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={openSources}
          className="h-9 px-3.5 rounded-xl text-sm border-slate-200 text-slate-600 hover:text-slate-900 hover:border-slate-300 gap-1.5 flex-shrink-0"
        >
          <ListPlus className="h-3.5 w-3.5" /> My Sources
        </Button>
      </div>

      <div className="flex items-start gap-2.5 bg-indigo-50 border border-indigo-100 text-indigo-700 rounded-xl px-4 py-2.5 mb-6 text-sm">
        <Info className="h-4 w-4 flex-shrink-0 text-indigo-500 mt-0.5" />
        <span>
          <strong>{config.rateLimits.startupHuntPerDay} hunts/day</strong> on the free tier. This tool blends ATS roles with startup
          lead discovery and contact enrichment, then ranks them for early access and outreach potential.
        </span>
      </div>

      <div className="grid grid-cols-[320px_1fr] gap-5 items-start">
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 space-y-5 sticky top-6"
        >
          <div className="flex items-center gap-2 pb-1 border-b border-slate-100">
            <SlidersHorizontal className="h-3.5 w-3.5 text-slate-400" />
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Hunt Strategy</span>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">Target role</Label>
            <Input
              placeholder="AI Engineer"
              className="rounded-xl h-9 text-sm border-slate-200 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200"
              {...register('query')}
            />
            {errors.query && <p className="text-xs text-destructive">{errors.query.message}</p>}
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">Cities / regions</Label>
            <Textarea
              rows={2}
              placeholder="Berlin, Munich, Hamburg, Frankfurt, Cologne, Remote"
              className="rounded-xl text-sm border-slate-200 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200"
              {...register('location')}
            />
            <p className="text-[10px] text-slate-400 leading-relaxed">Comma-separated. Each city runs in parallel; add &quot;Remote&quot; to include remote roles.</p>
            {errors.location && <p className="text-xs text-destructive">{errors.location.message}</p>}
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">Country</Label>
            <Input
              placeholder="Germany"
              className="rounded-xl h-9 text-sm border-slate-200 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200"
              {...register('country')}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-slate-600">Freshness</Label>
              <Select value={String(watch('posted_within_hours'))} onValueChange={(v) => setValue('posted_within_hours', parseInt(v, 10))}>
                <SelectTrigger className="rounded-xl h-9 text-sm border-slate-200"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="24" className="text-sm">24 hours</SelectItem>
                  <SelectItem value="72" className="text-sm">72 hours</SelectItem>
                  <SelectItem value="168" className="text-sm">7 days</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-slate-600">Startup stage</Label>
              <Select value={watch('company_stage') || 'any'} onValueChange={(v) => setValue('company_stage', v === 'any' ? '' : v)}>
                <SelectTrigger className="rounded-xl h-9 text-sm border-slate-200"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="any" className="text-sm">Any stage</SelectItem>
                  <SelectItem value="pre-seed" className="text-sm">Pre-seed</SelectItem>
                  <SelectItem value="seed" className="text-sm">Seed</SelectItem>
                  <SelectItem value="series a" className="text-sm">Series A</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">Result limit</Label>
            <Input
              type="number"
              min={1}
              max={50}
              className="rounded-xl h-9 text-sm border-slate-200 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200"
              {...register('result_limit')}
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">Use curated watchlist</Label>
            <Select value={watch('include_seeded_sources')} onValueChange={(v) => setValue('include_seeded_sources', v as 'false' | 'true')}>
              <SelectTrigger className="rounded-xl h-9 text-sm border-slate-200"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="false" className="text-sm">Off</SelectItem>
                <SelectItem value="true" className="text-sm">On</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">Remote only</Label>
            <Select value={watch('remote_only')} onValueChange={(v) => setValue('remote_only', v as 'false' | 'true')}>
              <SelectTrigger className="rounded-xl h-9 text-sm border-slate-200"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="false" className="text-sm">Include onsite and hybrid</SelectItem>
                <SelectItem value="true" className="text-sm">Remote only</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">Direct links only</Label>
            <Select value={watch('direct_links_only')} onValueChange={(v) => setValue('direct_links_only', v as 'false' | 'true')}>
              <SelectTrigger className="rounded-xl h-9 text-sm border-slate-200"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="false" className="text-sm">Allow ATS and lead sources</SelectItem>
                <SelectItem value="true" className="text-sm">Only show direct company links</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">English-friendly only</Label>
            <Select value={watch('english_friendly_only')} onValueChange={(v) => setValue('english_friendly_only', v as 'false' | 'true')}>
              <SelectTrigger className="rounded-xl h-9 text-sm border-slate-200"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="true" className="text-sm">Prefer English-friendly teams</SelectItem>
                <SelectItem value="false" className="text-sm">Show all teams</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">Strategy prompt</Label>
            <Textarea
              rows={4}
              placeholder="hidden gems, small startups, founder-led teams, low-competition, english-friendly, relocation support"
              className="rounded-xl text-sm border-slate-200 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200"
              {...register('strategy_prompt')}
            />
          </div>

          <div className="space-y-2.5 pt-1 border-t border-slate-100">
            <Label className="text-xs font-medium text-slate-600">Provider controls</Label>
            <div className="space-y-2.5">
              {SOURCE_DIAGNOSTIC_ORDER.map((bucket) => {
                const meta = PROVIDER_META[bucket]
                return (
                  <div key={bucket} className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-[13px] font-semibold text-slate-700">{meta.label}</p>
                        <p className="text-[11px] text-slate-500 mt-0.5">{meta.hint}</p>
                      </div>
                      <div className="w-[104px] flex-shrink-0">
                        <Select value={watch(meta.enabledField) as string} onValueChange={(v) => setValue(meta.enabledField, v as never)}>
                          <SelectTrigger className="rounded-lg h-8 text-xs border-slate-200"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="true" className="text-sm">Enabled</SelectItem>
                            <SelectItem value="false" className="text-sm">Disabled</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2.5 mt-2.5">
                      <div className="space-y-1">
                        <Label className="text-[10px] text-slate-500">Cap</Label>
                        <Input
                          type="number"
                          min={0}
                          max={50}
                          className="rounded-lg h-8 text-xs border-slate-200 bg-white"
                          {...register(meta.limitField)}
                        />
                      </div>
                      {bucket === 'crawler' ? (
                        <div className="space-y-1">
                          <Label className="text-[10px] text-slate-500">Watchlist cap</Label>
                          <Input
                            type="number"
                            min={0}
                            max={50}
                            className="rounded-lg h-8 text-xs border-slate-200 bg-white"
                            {...register('seeded_limit')}
                            disabled={watch('include_seeded_sources') !== 'true'}
                          />
                        </div>
                      ) : (
                        <div className="space-y-1">
                          <Label className="text-[10px] text-slate-500">Status</Label>
                          <div className="h-8 rounded-lg border border-slate-200 bg-white px-2.5 flex items-center text-[11px] text-slate-500 truncate">
                            {watch(meta.enabledField) === 'true' ? 'Will run if available' : 'Skipped for this hunt'}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          <Button
            type="submit"
            disabled={loading}
            className="w-full gradient-brand text-white border-0 shadow-sm hover:opacity-90 transition-opacity rounded-xl h-9 text-sm font-semibold"
          >
            {loading
              ? <><Loader2 className="h-3.5 w-3.5 mr-2 animate-spin" />Hunting…</>
              : <><Compass className="h-3.5 w-3.5 mr-2" />Run Startup Hunt</>
            }
          </Button>
        </form>

        <div className="min-w-0 space-y-4">
          {error && (
            <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl px-4 py-3 text-sm">
              {error}
            </div>
          )}

          {parsedStrategy && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-4">
              <div className="flex items-center gap-2 mb-3">
                <Sparkles className="h-4 w-4 text-amber-500" />
                <p className="text-sm font-semibold text-slate-700">Parsed Hunt Strategy</p>
                <span className="text-xs text-slate-400 ml-auto">{sourceCount} providers enabled | {results.length} ranked results</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {parsedStrategy.keywords.map((keyword) => (
                  <span key={keyword} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700">{keyword}</span>
                ))}
                {parsedStrategy.languages.map((language) => (
                  <span key={language} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-100">{language}</span>
                ))}
                {parsedStrategy.preferred_cities.map((city) => (
                  <span key={city} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-50 text-slate-600 border border-slate-200">{city}</span>
                ))}
                {parsedStrategy.company_stage && (
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-800 border border-amber-100">{parsedStrategy.company_stage}</span>
                )}
              </div>
              {Object.keys(sourceResultCounts).length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-slate-100">
                  {SOURCE_DIAGNOSTIC_ORDER.map((bucket) => (
                    <span key={bucket} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-white text-slate-600 border border-slate-200">
                      {bucketLabel(bucket)}: {sourceResultCounts[bucket] || 0}
                    </span>
                  ))}
                </div>
              )}
              {Object.keys(sourceDiagnostics).length > 0 && (
                <div className="grid grid-cols-2 gap-3 mt-3 pt-3 border-t border-slate-100">
                  {SOURCE_DIAGNOSTIC_ORDER.map((bucket) => {
                    const info = sourceDiagnostics[bucket]
                    if (!info) return null
                    const statusClasses = !info.enabled
                      ? 'bg-slate-50 border-slate-200 text-slate-500'
                      : !info.available
                        ? 'bg-amber-50 border-amber-200 text-amber-900'
                        : info.status === 'ok'
                          ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                          : info.status === 'error'
                            ? 'bg-red-50 border-red-200 text-red-800'
                            : info.status === 'filtered'
                              ? 'bg-amber-50 border-amber-200 text-amber-800'
                              : info.status === 'empty'
                                ? 'bg-slate-50 border-slate-200 text-slate-700'
                                : 'bg-slate-50 border-slate-200 text-slate-500'
                    const stateLabel = !info.enabled ? 'Disabled' : !info.available ? 'Unavailable' : info.status
                    return (
                      <div key={bucket} className={`rounded-xl border p-3 ${statusClasses}`}>
                        <div className="flex items-center justify-between gap-2 mb-1.5">
                          <span className="text-xs font-semibold uppercase tracking-wide">{bucketLabel(bucket)}</span>
                          <span className="text-[11px] font-semibold">{stateLabel}</span>
                        </div>
                        <p className="text-[11px] opacity-80 mb-1">Cap {info.requested_limit} | Accepted {info.accepted_count} | Raw {info.raw_count}</p>
                        <p className="text-xs leading-5">{info.message}</p>
                        {info.sources.length > 0 && (
                          <p className="text-[11px] mt-1.5 opacity-80">
                            {info.sources.map((source) => source.error ? `${source.name}: ${source.error}` : `${source.name}: ${source.raw_count}`).join(' | ')}
                          </p>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}

          {loading && results.length === 0 && (
            <div className="space-y-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 animate-pulse">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1 space-y-3">
                      <div className="flex items-center gap-2">
                        <div className="h-4 bg-slate-200 rounded w-48" />
                        <div className="h-4 bg-slate-100 rounded w-16" />
                        <div className="h-4 bg-slate-100 rounded w-16" />
                      </div>
                      <div className="h-3.5 bg-slate-200 rounded w-32" />
                      <div className="flex items-center gap-2">
                        <div className="h-3 bg-slate-100 rounded w-24" />
                        <div className="h-3 bg-slate-100 rounded w-20" />
                        <div className="h-3 bg-slate-100 rounded w-16" />
                      </div>
                      <div className="flex gap-1.5 mt-2">
                        <div className="h-5 bg-slate-100 rounded-md w-16" />
                        <div className="h-5 bg-slate-100 rounded-md w-20" />
                      </div>
                    </div>
                    <div className="flex gap-2 flex-shrink-0">
                      <div className="h-9 w-20 bg-slate-100 rounded-xl" />
                      <div className="h-9 w-14 bg-slate-200 rounded-xl" />
                      <div className="h-9 w-28 bg-slate-100 rounded-xl" />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4 mt-4">
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-3.5 space-y-2">
                      <div className="h-2.5 bg-slate-200 rounded w-20" />
                      <div className="h-3 bg-slate-100 rounded w-full" />
                      <div className="h-3 bg-slate-100 rounded w-4/5" />
                    </div>
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-3.5 space-y-2">
                      <div className="h-2.5 bg-slate-200 rounded w-16" />
                      <div className="h-3 bg-slate-100 rounded w-full" />
                      <div className="h-3 bg-slate-100 rounded w-3/4" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {!loading && results.length === 0 && !error && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-sm min-h-[480px] flex items-center justify-center p-8">
              <div className="text-center space-y-2">
                <div className="w-14 h-14 rounded-2xl bg-orange-50 flex items-center justify-center mx-auto">
                  <Compass className="h-7 w-7 text-orange-200" />
                </div>
                <p className="font-semibold text-slate-500">Ranked startup opportunities will appear here</p>
                <p className="text-sm text-slate-400">Use Startup Hunt when you want deeper discovery than the standard recent jobs tool</p>
              </div>
            </div>
          )}

          {rankedResultsWithBands.length > 0 && (
            <div className="space-y-5">
              {rankedResultsWithBands.map(({ result: job, bucket, showBand }, index) => {
                const resultKey = job.canonical_job_url || `${job.company_name}-${job.role_title}-${job.location}`
                const primaryLink = job.direct_apply_url || job.company_careers_url || job.portal_job_url || job.company_website_url
                const hasApplyPath = Boolean(job.direct_apply_url)
                const primaryLinkLabel = job.direct_apply_url
                  ? 'Apply'
                  : job.company_careers_url
                    ? 'Open Careers'
                    : job.portal_job_url
                      ? 'View Source'
                      : 'Open Website'
                const expanded = Boolean(expandedCards[resultKey])
                return (
                  <div key={resultKey} className="space-y-3">
                    {showBand && (
                      <div className="flex items-center justify-between gap-3 px-4 py-2 bg-violet-100 rounded-lg">
                        <div>
                          <h2 className="text-sm font-semibold text-slate-800">{bucketLabel(bucket)}</h2>
                          <p className="text-xs text-slate-500">Provider band continues from global rank #{index + 1}</p>
                        </div>
                        <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-700">
                          Ranked stream
                        </span>
                      </div>
                    )}
                    <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap mb-1">
                            <h3 className="text-base font-bold text-slate-900">{job.role_title}</h3>
                            <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                              Rank #{index + 1}
                            </span>
                            <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-semibold bg-orange-50 text-orange-700 border border-orange-100">
                              {bucketLabel(bucket)}
                            </span>
                            {job.score_labels.map((label) => (
                              <span key={label} className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-semibold border ${labelClasses[label] || 'bg-slate-100 text-slate-700 border-slate-200'}`}>
                                {label}
                              </span>
                            ))}
                            {job.saved && (
                              <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-semibold bg-slate-100 text-slate-600 border border-slate-200">
                                {job.saved_status || 'saved'}
                              </span>
                            )}
                          </div>
                          <p className="text-slate-700 font-semibold text-sm">{job.company_name}</p>
                          <div className="flex items-center gap-2 text-xs text-slate-500 mt-1.5 flex-wrap">
                            <MapPin className="h-3 w-3" />
                            <span>{job.location}</span>
                            <span>·</span>
                            <span>{job.source_name}</span>
                            {job.posted_at && <><span>·</span><span>{formatDate(job.posted_at)}</span></>}
                            <span>·</span>
                            <span className="font-semibold text-indigo-600">Score {job.score_total}</span>
                          </div>
                          <div className="flex flex-wrap gap-1.5 mt-3">
                            {job.company.stage && <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-slate-50 text-slate-700 border border-slate-200">{job.company.stage}</span>}
                            {job.company.company_size && <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-slate-50 text-slate-700 border border-slate-200">{job.company.company_size}</span>}
                            {job.company.english_friendly && <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-100">English-friendly</span>}
                            {job.company.relocation_support && <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold bg-sky-50 text-sky-700 border border-sky-100">{job.company.relocation_support}</span>}
                            {job.contacts.length > 0 && <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold bg-pink-50 text-pink-700 border border-pink-100">{job.contacts.length} contact{job.contacts.length === 1 ? '' : 's'}</span>}
                          </div>
                        </div>

                        <div className="flex gap-2 flex-shrink-0">
                          {primaryLink && (
                            <Button variant="outline" asChild className="rounded-xl h-9 text-xs">
                              <Link href={primaryLink} target="_blank">
                                <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
                                {primaryLinkLabel}
                              </Link>
                            </Button>
                          )}
                          <Button
                            disabled={savingId === resultKey}
                            onClick={() => saveOpportunity(job, 'saved')}
                            className="gradient-brand text-white border-0 hover:opacity-90 rounded-xl h-9 text-xs"
                          >
                            {savingId === resultKey && <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />}
                            Save
                          </Button>
                          {hasApplyPath ? (
                            <Button
                              variant="secondary"
                              disabled={savingId === resultKey}
                              onClick={() => saveOpportunity(job, 'applied')}
                              className="rounded-xl h-9 text-xs"
                            >
                              Track Applied
                            </Button>
                          ) : (
                            <Button
                              variant="secondary"
                              disabled={savingId === resultKey}
                              onClick={() => saveOpportunity(job, 'contacted')}
                              className="rounded-xl h-9 text-xs"
                            >
                              Mark Contacted
                            </Button>
                          )}
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-4 mt-4">
                        <div className="rounded-xl border border-slate-100 bg-slate-50 p-3.5 space-y-2">
                          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Main signals</p>
                          {compactReasons(job.score_reasons).length > 0 ? compactReasons(job.score_reasons).map((reason) => (
                            <p key={reason} className="text-sm text-slate-700">{reason}</p>
                          )) : <p className="text-sm text-slate-400">No ranking reasons captured.</p>}
                        </div>

                        <div className="rounded-xl border border-slate-100 bg-slate-50 p-3.5 space-y-2">
                          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Quick view</p>
                          <p className="text-sm text-slate-700">
                            {job.opportunity_kind === 'job' ? 'Job result' : 'Outreach lead'} from {job.source_name}
                          </p>
                          <p className="text-sm text-slate-700">
                            {job.direct_apply_url ? 'Direct apply path available.' : job.company_careers_url ? 'Company careers page available.' : 'Lead source for follow-up and outreach.'}
                          </p>
                        </div>
                      </div>

                      <div className="mt-4">
                        <button
                          type="button"
                          onClick={() => toggleExpanded(resultKey)}
                          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900"
                        >
                          {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                          {expanded ? 'Show fewer details' : 'Show more details'}
                        </button>
                      </div>

                      {expanded && (
                        <div className="space-y-4 mt-4">
                          <div className="rounded-xl border border-slate-100 bg-slate-50 p-3.5 space-y-2">
                            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Full ranking details</p>
                            {job.score_reasons.length > 0 ? job.score_reasons.map((reason) => (
                              <p key={reason} className="text-sm text-slate-700">{reason}</p>
                            )) : <p className="text-sm text-slate-400">No extra ranking reasons captured.</p>}
                          </div>

                          <div className="rounded-xl border border-slate-100 bg-slate-50 p-3.5 space-y-2">
                            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Startup profile</p>
                            {(job.company_website_url || job.company_careers_url || job.portal_job_url) && (
                              <div className="text-xs text-slate-600 space-y-1">
                                {job.company_website_url && <p><span className="font-medium">Website:</span> {job.company_website_url}</p>}
                                {job.company_careers_url && <p><span className="font-medium">Careers:</span> {job.company_careers_url}</p>}
                                {job.portal_job_url && <p><span className="font-medium">Source:</span> {job.portal_job_url}</p>}
                              </div>
                            )}
                            {job.company.ai_relevance && (
                              <p className="text-xs text-slate-600"><span className="font-medium">Company signal:</span> {job.company.ai_relevance}</p>
                            )}
                          </div>

                          <div className="rounded-xl border border-slate-100 p-3.5 space-y-3">
                            <div className="flex items-center gap-2">
                              <UserRound className="h-3.5 w-3.5 text-slate-400" />
                              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Contacts</p>
                            </div>
                            {job.contacts.length === 0 ? (
                              <p className="text-sm text-slate-400">No contact surfaced yet from the configured source.</p>
                            ) : (
                              <div className="grid grid-cols-2 gap-3">
                                {job.contacts.map((contact) => (
                                  <div key={`${contact.name}-${contact.linkedin_url || contact.email || contact.title}`} className="rounded-xl bg-slate-50 border border-slate-100 p-3">
                                    <p className="text-sm font-semibold text-slate-900">{contact.name}</p>
                                    <p className="text-xs text-slate-600 mt-0.5">{contact.title}</p>
                                    <p className="text-[10px] text-slate-400 mt-0.5">{contact.contact_type}</p>
                                    {contact.email && (
                                      <p className="text-xs text-slate-700 mt-2 flex items-center gap-1">
                                        <Mail className="h-3 w-3 text-slate-400" />
                                        {contact.email}
                                      </p>
                                    )}
                                    <div className="flex flex-wrap gap-1 mt-2">
                                      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-white text-slate-600 border border-slate-200">{contact.source}</span>
                                      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-white text-slate-600 border border-slate-200">email {contact.email_confidence}</span>
                                    </div>
                                    {contact.linkedin_url && (
                                      <Link href={contact.linkedin_url} target="_blank" className="text-xs text-indigo-600 hover:underline mt-2 inline-flex">
                                        LinkedIn profile
                                      </Link>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>

                          <div className="rounded-xl border border-slate-100 p-3.5 space-y-2">
                            <div className="flex items-center gap-2">
                              <Building2 className="h-3.5 w-3.5 text-slate-400" />
                              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Citation</p>
                            </div>
                            <p className="text-xs text-slate-600">{job.citation.extraction_note}</p>
                            {(job.citation.canonical_url || job.citation.job_url) && (
                              <Link
                                href={job.citation.canonical_url || job.citation.job_url}
                                target="_blank"
                                className="text-xs text-indigo-600 hover:underline break-all block"
                              >
                                {job.citation.canonical_url || job.citation.job_url}
                              </Link>
                            )}
                            <div className="flex flex-wrap gap-1.5">
                              {job.citation.evidence.map((line) => (
                                <span key={line} className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-white text-slate-600 border border-slate-200">{line}</span>
                              ))}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {overflowResults.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-4 space-y-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold text-slate-800">Unfiltered / More Results</h2>
                  <p className="text-xs text-slate-500">Additional deduped matches that did not make the main ranked cutoff.</p>
                </div>
                <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-700">
                  {overflowResults.length} more
                </span>
              </div>

              <div className="space-y-3">
                {overflowResults.map((job, index) => {
                  const resultKey = job.canonical_job_url || `${job.company_name}-${job.role_title}-${job.location}`
                  const primaryLink = job.direct_apply_url || job.company_careers_url || job.portal_job_url || job.company_website_url
                  const primaryLinkLabel = job.direct_apply_url
                    ? 'Apply'
                    : job.company_careers_url
                      ? 'Open Careers'
                      : job.portal_job_url
                        ? 'View Source'
                        : 'Open Website'
                  return (
                    <div key={resultKey} className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap mb-1">
                            <p className="text-sm font-semibold text-slate-900">{job.role_title}</p>
                            <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                              Extra #{index + 1}
                            </span>
                            <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-semibold bg-orange-50 text-orange-700 border border-orange-100">
                              {bucketLabel(job.source_bucket || 'crawler')}
                            </span>
                          </div>
                          <p className="text-xs text-slate-700">{job.company_name}</p>
                          <div className="flex items-center gap-2 text-[11px] text-slate-500 mt-1 flex-wrap">
                            <span>{job.location}</span>
                            <span>·</span>
                            <span>{job.source_name}</span>
                            <span>·</span>
                            <span className="font-semibold text-indigo-600">Score {job.score_total}</span>
                          </div>
                        </div>

                        {primaryLink && (
                          <Button variant="outline" asChild className="rounded-xl h-8 text-xs">
                            <Link href={primaryLink} target="_blank">
                              <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
                              {primaryLinkLabel}
                            </Link>
                          </Button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {filteredOut.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-4 space-y-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold text-slate-800">Filtered Out</h2>
                  <p className="text-xs text-slate-500">Results rejected by role, location, freshness, direct-link, or other filters.</p>
                </div>
                <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-700">
                  {filteredOut.length} filtered
                </span>
              </div>

              <div className="space-y-3">
                {filteredOut.map((item, index) => (
                  <div key={`${item.company_name}-${item.role_title}-${item.source_name}-${index}`} className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <p className="text-sm font-semibold text-slate-900">{item.role_title}</p>
                      <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-semibold bg-orange-50 text-orange-700 border border-orange-100">
                        {bucketLabel(item.source_bucket || 'crawler')}
                      </span>
                    </div>
                    <p className="text-xs text-slate-700">{item.company_name} · {item.source_name}</p>
                    <p className="text-xs text-slate-500 mt-1">Reason: {item.reason}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* My Sources dialog */}
      <Dialog open={sourcesOpen} onOpenChange={setSourcesOpen}>
        <DialogContent className="max-w-lg rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold">My Sources</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground -mt-2">
            ATS boards or companies you want searched every time — always included, independent of the seeded-sources toggle.
          </p>

          <form onSubmit={handleSubmitSource(onAddSource)} className="space-y-3 border-b border-slate-100 pb-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium">Type</Label>
                <Select value={watchSource('type')} onValueChange={(v) => setSourceValue('type', v as SourceFormData['type'])}>
                  <SelectTrigger className="rounded-xl h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {USER_SOURCE_TYPES.map((t) => (
                      <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium">Name</Label>
                <Input placeholder="Acme Corp" className="rounded-xl h-9" {...registerSource('name')} />
                {sourceErrors.name && <p className="text-xs text-destructive">{sourceErrors.name.message}</p>}
              </div>
            </div>
            <p className="text-[11px] text-muted-foreground">
              {USER_SOURCE_TYPES.find((t) => t.value === watchSource('type'))?.hint}
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium">Board slug</Label>
                <Input placeholder="acme" className="rounded-xl h-9" {...registerSource('slug')} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium">Careers/company URL</Label>
                <Input placeholder="https://acme.com/careers" className="rounded-xl h-9" {...registerSource('url')} />
              </div>
            </div>
            <Button type="submit" disabled={addingSource} className="w-full rounded-xl h-9 gradient-brand text-white border-0">
              {addingSource ? <Loader2 className="h-3.5 w-3.5 mr-2 animate-spin" /> : <Plus className="h-3.5 w-3.5 mr-2" />}
              Add source
            </Button>
          </form>

          <div className="space-y-2 max-h-64 overflow-y-auto">
            {sourcesLoading ? (
              <div className="flex items-center gap-2 text-sm text-slate-400 py-4 justify-center">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading…
              </div>
            ) : sources.length === 0 ? (
              <p className="text-sm text-slate-400 text-center py-4">No sources added yet.</p>
            ) : (
              sources.map((s) => (
                <div key={s.id} className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 px-3 py-2">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-800 truncate">{s.name}</p>
                    <p className="text-xs text-slate-500 truncate">
                      {USER_SOURCE_TYPES.find((t) => t.value === s.type)?.label || s.type}
                      {s.slug ? ` · ${s.slug}` : ''}
                    </p>
                  </div>
                  <button
                    onClick={() => deleteSource(s.id)}
                    disabled={deletingSourceId === s.id}
                    className="h-7 w-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors flex-shrink-0"
                  >
                    {deletingSourceId === s.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                  </button>
                </div>
              ))
            )}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setSourcesOpen(false)} className="rounded-xl">Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
