'use client'

import Link from 'next/link'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from '@/components/ui/use-toast'
import { apiFetch } from '@/lib/api'
import { config } from '@/lib/config'
import { formatDate } from '@/lib/utils'
import { StartupHuntResponse, StartupHuntResult } from '@/lib/types'
import {
  Building2,
  Compass,
  ExternalLink,
  Info,
  Loader2,
  Mail,
  MapPin,
  Sparkles,
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
  seeded_limit: z.coerce.number().int().min(0).max(50),
  crawler_limit: z.coerce.number().int().min(0).max(50),
  startupmap_limit: z.coerce.number().int().min(0).max(50),
  web_limit: z.coerce.number().int().min(0).max(50),
  indeed_limit: z.coerce.number().int().min(0).max(50),
  apify_limit: z.coerce.number().int().min(0).max(50),
  ats_limit: z.coerce.number().int().min(0).max(50),
})

type FormData = z.infer<typeof schema>

const DEFAULT_VALUES: FormData = {
  query: 'AI/ML Engineer',
  location: 'Berlin',
  country: 'Germany',
  posted_within_hours: 168,
  result_limit: 15,
  include_seeded_sources: 'false',
  remote_only: 'false',
  direct_links_only: 'false',
  english_friendly_only: 'false',
  company_stage: '',
  strategy_prompt: 'small startups, hidden gems, early access, founder-led teams, english friendly, relocation friendly',
  seeded_limit: 8,
  crawler_limit: 5,
  startupmap_limit: 5,
  web_limit: 5,
  indeed_limit: 5,
  apify_limit: 5,
  ats_limit: 5,
}

const labelClasses: Record<string, string> = {
  Fresh: 'bg-green-100 text-green-900 hover:bg-green-100',
  'Direct Apply': 'bg-blue-100 text-blue-900 hover:bg-blue-100',
  'Hidden Gem': 'bg-amber-100 text-amber-900 hover:bg-amber-100',
  'Outreach Friendly': 'bg-pink-100 text-pink-900 hover:bg-pink-100',
  'Germany Match': 'bg-slate-100 text-slate-900 hover:bg-slate-100',
  'AI/ML Fit': 'bg-violet-100 text-violet-900 hover:bg-violet-100',
}

const SOURCE_DIAGNOSTIC_ORDER = ['crawler', 'startupmap', 'web', 'indeed', 'apify', 'ats'] as const

export default function StartupHuntPage() {
  const [loading, setLoading] = useState(false)
  const [savingId, setSavingId] = useState<string | null>(null)
  const [results, setResults] = useState<StartupHuntResult[]>([])
  const [parsedStrategy, setParsedStrategy] = useState<StartupHuntResponse['parsed_strategy'] | null>(null)
  const [sourceCount, setSourceCount] = useState(0)
  const [sourceResultCounts, setSourceResultCounts] = useState<Record<string, number>>({})
  const [sourceDiagnostics, setSourceDiagnostics] = useState<StartupHuntResponse['source_diagnostics']>({})
  const [error, setError] = useState<string | null>(null)
  const { toast } = useToast()

  const { register, handleSubmit, setValue, watch, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: DEFAULT_VALUES,
  })

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
        }),
      })
      const json = await res.json()
      if (!res.ok) {
        setError(json.detail || 'Search failed. Please try again.')
        setResults([])
        setParsedStrategy(null)
        setSourceCount(0)
        setSourceResultCounts({})
        setSourceDiagnostics({})
        return
      }
      const payload = json as StartupHuntResponse
      setResults(payload.results)
      setParsedStrategy(payload.parsed_strategy)
      setSourceCount(payload.configured_source_count)
      setSourceResultCounts(payload.source_result_counts || {})
      setSourceDiagnostics(payload.source_diagnostics || {})
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
            seeded_limit: watch('seeded_limit'),
            crawler_limit: watch('crawler_limit'),
            startupmap_limit: watch('startupmap_limit'),
            web_limit: watch('web_limit'),
            indeed_limit: watch('indeed_limit'),
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

  return (
    <div className="animate-fade-in">
      {/* Page Header */}
      <div className="flex items-center gap-4 mb-6">
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

      {/* Rate limit notice */}
      <div className="flex items-start gap-2.5 bg-indigo-50 border border-indigo-100 text-indigo-700 rounded-xl px-4 py-3 mb-6 text-sm">
        <Info className="h-4 w-4 flex-shrink-0 text-indigo-500 mt-0.5" />
        <span>
          <strong>{config.rateLimits.startupHuntPerDay} hunts/day</strong> on the free tier. This tool blends ATS roles with startup
          lead discovery and contact enrichment, then ranks them for early access and outreach potential.
        </span>
      </div>

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-1">
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
              <p className="text-sm font-semibold text-slate-700 mb-4">Hunt Strategy</p>
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <Label className="text-sm font-medium">Target role</Label>
                  <Input placeholder="AI Engineer" className="rounded-xl border-slate-200" {...register('query')} />
                  {errors.query && <p className="text-xs text-destructive">{errors.query.message}</p>}
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label className="text-sm font-medium">City / region</Label>
                    <Input placeholder="Berlin" className="rounded-xl border-slate-200" {...register('location')} />
                    {errors.location && <p className="text-xs text-destructive">{errors.location.message}</p>}
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-sm font-medium">Country</Label>
                    <Input placeholder="Germany" className="rounded-xl border-slate-200" {...register('country')} />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <Label>Freshness</Label>
                    <Select value={String(watch('posted_within_hours'))} onValueChange={(v) => setValue('posted_within_hours', parseInt(v, 10))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="24">24 hours</SelectItem>
                        <SelectItem value="72">72 hours</SelectItem>
                        <SelectItem value="168">7 days</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label>Startup stage</Label>
                    <Select value={watch('company_stage') || 'any'} onValueChange={(v) => setValue('company_stage', v === 'any' ? '' : v)}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="any">Any stage</SelectItem>
                        <SelectItem value="pre-seed">Pre-seed</SelectItem>
                        <SelectItem value="seed">Seed</SelectItem>
                        <SelectItem value="series a">Series A</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="space-y-1">
                  <Label>Result limit</Label>
                  <Input type="number" min={1} max={50} {...register('result_limit')} />
                </div>

                <div className="space-y-1">
                  <Label>Use curated watchlist</Label>
                  <Select value={watch('include_seeded_sources')} onValueChange={(v) => setValue('include_seeded_sources', v as 'false' | 'true')}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="false">Off</SelectItem>
                      <SelectItem value="true">On</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1">
                  <Label>Remote only</Label>
                  <Select value={watch('remote_only')} onValueChange={(v) => setValue('remote_only', v as 'false' | 'true')}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="false">Include onsite and hybrid</SelectItem>
                      <SelectItem value="true">Remote only</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1">
                  <Label>Direct links only</Label>
                  <Select value={watch('direct_links_only')} onValueChange={(v) => setValue('direct_links_only', v as 'false' | 'true')}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="false">Allow ATS and lead sources</SelectItem>
                      <SelectItem value="true">Only show direct company links</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1">
                  <Label>English-friendly only</Label>
                  <Select value={watch('english_friendly_only')} onValueChange={(v) => setValue('english_friendly_only', v as 'false' | 'true')}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="true">Prefer English-friendly teams</SelectItem>
                      <SelectItem value="false">Show all teams</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1">
                  <Label>Strategy prompt</Label>
                  <Textarea
                    rows={5}
                    placeholder="hidden gems, small startups, founder-led teams, low-competition, english-friendly, relocation support"
                    {...register('strategy_prompt')}
                  />
                </div>

                <div className="space-y-3 pt-2 border-t border-slate-100">
                  <Label>Source caps</Label>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <Label className="text-xs text-slate-500">Crawler</Label>
                      <Input type="number" min={0} max={50} {...register('crawler_limit')} />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs text-slate-500">StartupMap</Label>
                      <Input type="number" min={0} max={50} {...register('startupmap_limit')} />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs text-slate-500">Web</Label>
                      <Input type="number" min={0} max={50} {...register('web_limit')} />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs text-slate-500">Indeed</Label>
                      <Input type="number" min={0} max={50} {...register('indeed_limit')} />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs text-slate-500">Apify</Label>
                      <Input type="number" min={0} max={50} {...register('apify_limit')} />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs text-slate-500">ATS</Label>
                      <Input type="number" min={0} max={50} {...register('ats_limit')} />
                    </div>
                    {watch('include_seeded_sources') === 'true' && (
                      <div className="space-y-1 col-span-2">
                        <Label className="text-xs text-slate-500">Watchlist</Label>
                        <Input type="number" min={0} max={50} {...register('seeded_limit')} />
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <Button
              type="submit"
              className="w-full h-11 gradient-brand text-white border-0 shadow-brand-sm hover:opacity-90 transition-opacity rounded-xl font-semibold"
              disabled={loading}
            >
              {loading
                ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Hunting…</>
                : <><Compass className="h-4 w-4 mr-2" /> Run Startup Hunt</>
              }
            </Button>
          </form>
        </div>

        <div className="col-span-2 space-y-4">
          {error && (
            <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl px-4 py-3 text-sm">
              {error}
            </div>
          )}

          {parsedStrategy && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-4">
              <div className="flex items-center gap-2 mb-3">
                <Sparkles className="h-4 w-4 text-amber-500" />
                <p className="text-sm font-semibold text-slate-700">Parsed Hunt Strategy</p>
                <span className="text-xs text-slate-400 ml-auto">{sourceCount} sources active | {results.length} ranked results</span>
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
                  {Object.entries(sourceResultCounts).map(([source, count]) => (
                    <span key={source} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-white text-slate-600 border border-slate-200">
                      {source}: {count}
                    </span>
                  ))}
                </div>
              )}
              {Object.keys(sourceDiagnostics).length > 0 && (
                <div className="grid grid-cols-2 gap-3 mt-3 pt-3 border-t border-slate-100">
                  {SOURCE_DIAGNOSTIC_ORDER.filter((bucket) => sourceDiagnostics[bucket]).map((bucket) => {
                    const info = sourceDiagnostics[bucket]
                    const statusClasses = info.status === 'ok'
                      ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                      : info.status === 'error'
                        ? 'bg-red-50 border-red-200 text-red-800'
                        : info.status === 'filtered'
                          ? 'bg-amber-50 border-amber-200 text-amber-800'
                          : info.status === 'empty'
                            ? 'bg-slate-50 border-slate-200 text-slate-700'
                            : 'bg-slate-50 border-slate-200 text-slate-500'
                    return (
                      <div key={bucket} className={`rounded-xl border p-3 ${statusClasses}`}>
                        <div className="flex items-center justify-between gap-2 mb-1.5">
                          <span className="text-xs font-semibold uppercase tracking-wide">{bucket}</span>
                          <span className="text-[11px]">
                            {info.accepted_count}/{info.requested_limit}
                          </span>
                        </div>
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

          {!loading && results.length === 0 && !error && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card min-h-[480px] flex items-center justify-center p-8">
              <div className="text-center space-y-2">
                <div className="w-14 h-14 rounded-2xl bg-orange-50 flex items-center justify-center mx-auto">
                  <Compass className="h-7 w-7 text-orange-200" />
                </div>
                <p className="font-semibold text-slate-500">Ranked startup opportunities will appear here</p>
                <p className="text-sm text-slate-400">Use Startup Hunt when you want deeper discovery than the standard recent jobs tool</p>
              </div>
            </div>
          )}

          {results.length > 0 && (
            <div className="space-y-4">
              {results.map((job) => {
                const resultKey = job.canonical_job_url || `${job.company_name}-${job.role_title}-${job.location}`
                const primaryLink = job.direct_apply_url || job.company_careers_url || job.portal_job_url || job.company_website_url
                const hasApplyPath = Boolean(job.direct_apply_url || job.company_careers_url)
                const primaryLinkLabel = job.direct_apply_url
                  ? 'Apply'
                  : job.company_careers_url
                    ? 'Open Careers'
                    : job.portal_job_url
                      ? 'View Source'
                      : 'Open Website'
                return (
                  <div key={resultKey} className="bg-white rounded-2xl border border-slate-100 shadow-card p-5 space-y-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-1">
                          <h2 className="text-base font-bold text-slate-900">{job.role_title}</h2>
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

                    <div className="grid grid-cols-2 gap-4">
                      <div className="rounded-xl border border-slate-100 bg-slate-50 p-3.5 space-y-2">
                        <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Why it ranked</p>
                        {job.score_reasons.length > 0 ? job.score_reasons.map((reason) => (
                          <p key={reason} className="text-sm text-slate-700">{reason}</p>
                        )) : <p className="text-sm text-slate-400">No extra ranking reasons captured.</p>}
                      </div>

                      <div className="rounded-xl border border-slate-100 bg-slate-50 p-3.5 space-y-2">
                        <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Startup profile</p>
                        <div className="flex flex-wrap gap-1.5">
                          {job.company.stage && <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-white text-slate-700 border border-slate-200">{job.company.stage}</span>}
                          {job.company.company_size && <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-white text-slate-700 border border-slate-200">{job.company.company_size}</span>}
                          {job.company.english_friendly && <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-100">English-friendly</span>}
                          {job.company.relocation_support && <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold bg-sky-50 text-sky-700 border border-sky-100">{job.company.relocation_support}</span>}
                        </div>
                        {(job.company_website_url || job.company_careers_url || job.portal_job_url) && (
                          <div className="text-xs text-slate-600 space-y-0.5 mt-1">
                            {job.company_website_url && <p><span className="font-medium">Website:</span> {job.company_website_url}</p>}
                            {job.company_careers_url && <p><span className="font-medium">Careers:</span> {job.company_careers_url}</p>}
                            {job.portal_job_url && <p><span className="font-medium">Source:</span> {job.portal_job_url}</p>}
                          </div>
                        )}
                      </div>
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
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
