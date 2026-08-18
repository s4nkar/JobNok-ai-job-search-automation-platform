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
import { useToast } from '@jobnok/ui'
import { apiFetch, apiGet } from '@/lib/api'
import { config } from '@/lib/config'
import { formatDate } from '@jobnok/ui'
import { JobSearchApplication, JobSearchResponse, JobSearchResult } from '@/lib/types'
import { queryKeys } from '@/lib/queryKeys'
import {
  Bookmark,
  BriefcaseBusiness,
  CheckCircle2,
  ExternalLink,
  Info,
  Loader2,
  MapPin,
  Search,
  SlidersHorizontal,
  Sparkles,
} from 'lucide-react'

// Adzuna's supported country path segments - https://developer.adzuna.com/
// Keep in sync with apps/api/app/modules/job_search/sources.py _ADZUNA_COUNTRY_ALIASES
const ADZUNA_COUNTRIES: { value: string; label: string }[] = [
  { value: 'de', label: 'Germany' },
  { value: 'gb', label: 'United Kingdom' },
  { value: 'at', label: 'Austria' },
  { value: 'au', label: 'Australia' },
  { value: 'br', label: 'Brazil' },
  { value: 'ca', label: 'Canada' },
  { value: 'fr', label: 'France' },
  { value: 'in', label: 'India' },
  { value: 'it', label: 'Italy' },
  { value: 'mx', label: 'Mexico' },
  { value: 'nl', label: 'Netherlands' },
  { value: 'nz', label: 'New Zealand' },
  { value: 'pl', label: 'Poland' },
  { value: 'ru', label: 'Russia' },
  { value: 'sg', label: 'Singapore' },
  { value: 'us', label: 'United States' },
  { value: 'za', label: 'South Africa' },
]

const schema = z.object({
  query: z.string().min(2, 'Enter a role or keyword').max(200, 'Keep it under 200 characters'),
  location: z.string().min(2, 'Enter a location').max(200, 'Keep it under 200 characters'),
  country: z.string().min(2, 'Select a country'),
  posted_within_hours: z.coerce.number().int().min(1).max(720),
  result_limit: z.coerce.number().int().min(1).max(50),
  remote_only: z.enum(['false', 'true']).default('false'),
  preferences_prompt: z.string().max(500, 'Keep it under 500 characters').optional(),
})

type FormData = z.infer<typeof schema>

const DEFAULT_VALUES: FormData = {
  query: 'Software Engineer',
  location: 'Germany',
  country: 'de',
  posted_within_hours: 24,
  result_limit: 10,
  remote_only: 'false',
  preferences_prompt: 'small pre seed startups, english preferred',
}

export default function RecentJobSearchPage() {
  const queryClient = useQueryClient()
  const [loading, setLoading] = useState(false)
  const [applyingId, setApplyingId] = useState<string | null>(null)
  const [results, setResults] = useState<JobSearchResult[]>([])
  const [parsedPreferences, setParsedPreferences] = useState<JobSearchResponse['parsed_preferences'] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { toast } = useToast()

  // Shares its cache key with the Tracker page's "Job Search" tab, which owns
  // the actual list UI and status editing - this page only needs the count.
  const { data: tracked = [] } = useQuery({
    queryKey: queryKeys.jobSearchApplications,
    queryFn: () => apiGet<JobSearchApplication[]>('/api/job-search/applications?limit=200'),
  })

  function setTracked(updater: (prev: JobSearchApplication[]) => JobSearchApplication[]) {
    queryClient.setQueryData<JobSearchApplication[]>(queryKeys.jobSearchApplications, (prev) => updater(prev || []))
  }

  function upsertTracked(row: JobSearchApplication) {
    setTracked((prev) => {
      const withoutRow = prev.filter((a) => a.id !== row.id)
      return [row, ...withoutRow]
    })
  }

  const { register, handleSubmit, setValue, watch, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: DEFAULT_VALUES,
  })

  const postedHours = watch('posted_within_hours')
  const remoteOnly = watch('remote_only')
  const country = watch('country')

  async function onSubmit(data: FormData) {
    setLoading(true)
    setError(null)

    try {
      const res = await apiFetch('/api/job-search/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...data,
          remote_only: data.remote_only === 'true',
          preferences_prompt: data.preferences_prompt?.trim() || null,
        }),
      })

      const json = await res.json()
      if (!res.ok) {
        setError(json.detail || 'Search failed. Please try again.')
        setResults([])
        setParsedPreferences(null)
        return
      }

      const payload = json as JobSearchResponse
      setResults(payload.results)
      setParsedPreferences(payload.parsed_preferences)
    } catch {
      setError('Network error. Please try again.')
      setResults([])
      setParsedPreferences(null)
    } finally {
      setLoading(false)
    }
  }

  async function markApplied(job: JobSearchResult) {
    setApplyingId(job.job_url_canonical)
    try {
      const res = await apiFetch('/api/job-search/applications', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job_url: job.job_url,
          job_url_canonical: job.job_url_canonical,
          source_name: job.source_name,
          external_job_id: job.external_job_id,
          company: job.company,
          role: job.role,
          location: job.location,
          posted_at: job.posted_at,
          applied_at: new Date().toISOString(),
          application_status: 'applied',
          citation_payload: job.citation,
          search_context: {
            query: watch('query'),
            location: watch('location'),
            country: watch('country') || null,
            posted_within_hours: watch('posted_within_hours'),
            result_limit: watch('result_limit'),
            remote_only: watch('remote_only') === 'true',
            preferences_prompt: watch('preferences_prompt') || null,
          },
        }),
      })

      const json = await res.json()
      if (!res.ok) {
        toast({ title: 'Could not update tracking', description: json.detail || 'Please try again.', variant: 'destructive' })
        return
      }

      setResults((prev) => prev.map((item) => item.job_url_canonical === job.job_url_canonical
        ? {
          ...item,
          applied: true,
          application_status: 'applied',
          tracked_application_id: json.id,
        }
        : item
      ))
      upsertTracked(json as JobSearchApplication)
      toast({ title: 'Application tracked', description: 'This job is now synced to your Follow-Up Tracker.' })
    } catch {
      toast({ title: 'Could not update tracking', description: 'Network error. Please try again.', variant: 'destructive' })
    } finally {
      setApplyingId(null)
    }
  }

  return (
    <div className="animate-fade-in">
      {/* Page Header */}
      <div className="flex items-center gap-4 mb-6">
        <div className="page-header-icon bg-indigo-100">
          <Search className="h-5 w-5 text-indigo-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Recent Job Search</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Search live postings across Germany, the UK, and more. Any company, any role, powered by Jobnok.
          </p>
        </div>
      </div>

      {/* Rate limit notice */}
      <div className="flex items-start gap-2.5 bg-indigo-50 border border-indigo-100 text-indigo-700 rounded-xl px-4 py-3 mb-6 text-sm">
        <Info className="h-4 w-4 flex-shrink-0 text-indigo-500 mt-0.5" />
        <span>
          <strong>{config.rateLimits.jobSearchPerDay} searches/day</strong> on the free tier. General-market search, not limited to startups or curated ATS boards. Each result keeps a citation trail.
        </span>
      </div>

      {/* Tracked count - the actual list and status editing live in the Follow-Up
          Tracker's "Job Search" tab, not duplicated here. */}
      <Link
        href="/tracker?tab=job-search"
        className="inline-flex items-center gap-2 mb-6 px-3.5 py-2 rounded-xl border border-slate-100 bg-white shadow-sm text-sm text-slate-600 hover:border-indigo-200 hover:text-indigo-700 transition-colors"
      >
        <Bookmark className="h-3.5 w-3.5 text-indigo-500" />
        <span className="font-semibold">{tracked.length}</span> tracked from this tool
        <span className="text-indigo-600">- view in Tracker</span>
      </Link>

      <div className="grid grid-cols-[320px_1fr] gap-5 items-start">
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 space-y-5 sticky top-6"
        >
          <div className="flex items-center gap-2 pb-1 border-b border-slate-100">
            <SlidersHorizontal className="h-3.5 w-3.5 text-slate-400" />
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Filters</span>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">Role or keywords</Label>
            <Input
              placeholder="Founding Engineer"
              className="rounded-xl h-9 text-sm border-slate-200 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200"
              {...register('query')}
            />
            {errors.query && <p className="text-xs text-destructive">{errors.query.message}</p>}
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">Location</Label>
            <Input
              placeholder="Berlin or Germany"
              className="rounded-xl h-9 text-sm border-slate-200 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200"
              {...register('location')}
            />
            {errors.location && <p className="text-xs text-destructive">{errors.location.message}</p>}
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">Country</Label>
            <Select value={country} onValueChange={(v) => setValue('country', v)}>
              <SelectTrigger className="rounded-xl h-9 text-sm border-slate-200"><SelectValue /></SelectTrigger>
              <SelectContent>
                {ADZUNA_COUNTRIES.map(({ value, label }) => (
                  <SelectItem key={value} value={value} className="text-sm">{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.country && <p className="text-xs text-destructive">{errors.country.message}</p>}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-slate-600">Posted within</Label>
              <Select value={String(postedHours)} onValueChange={(v) => setValue('posted_within_hours', parseInt(v, 10))}>
                <SelectTrigger className="rounded-xl h-9 text-sm border-slate-200"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="24" className="text-sm">24 hours</SelectItem>
                  <SelectItem value="72" className="text-sm">72 hours</SelectItem>
                  <SelectItem value="168" className="text-sm">7 days</SelectItem>
                </SelectContent>
              </Select>
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
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">Remote only</Label>
            <Select value={remoteOnly} onValueChange={(v) => setValue('remote_only', v as 'false' | 'true')}>
              <SelectTrigger className="rounded-xl h-9 text-sm border-slate-200"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="false" className="text-sm">Include onsite and hybrid</SelectItem>
                <SelectItem value="true" className="text-sm">Remote only</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">Preference prompt</Label>
            <Textarea
              rows={4}
              placeholder="small pre seed startups, english preferred, product-minded teams"
              className="rounded-xl text-sm border-slate-200 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200 resize-none"
              {...register('preferences_prompt')}
            />
            {errors.preferences_prompt && <p className="text-xs text-destructive">{errors.preferences_prompt.message}</p>}
          </div>

          <Button
            type="submit"
            disabled={loading}
            className="w-full gradient-brand text-white border-0 shadow-sm hover:opacity-90 transition-opacity rounded-xl h-9 text-sm font-semibold"
          >
            {loading
              ? <><Loader2 className="h-3.5 w-3.5 mr-2 animate-spin" />Searching…</>
              : <><Search className="h-3.5 w-3.5 mr-2" />Find Recent Jobs</>
            }
          </Button>
        </form>

        <div className="min-w-0 space-y-4">
          {error && (
            <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl px-4 py-3 text-sm">
              {error}
            </div>
          )}

          {parsedPreferences && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-4">
              <div className="flex items-center gap-2 mb-3">
                <Sparkles className="h-4 w-4 text-amber-500" />
                <p className="text-sm font-semibold text-slate-700">Parsed Preferences</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {parsedPreferences.keywords.map((keyword) => (
                  <span key={keyword} className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-700">{keyword}</span>
                ))}
                {parsedPreferences.languages.map((language) => (
                  <span key={language} className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-slate-50 text-slate-600 border border-slate-200">{language}</span>
                ))}
                {parsedPreferences.company_stage && (
                  <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-800 border border-amber-100">{parsedPreferences.company_stage}</span>
                )}
                {parsedPreferences.keywords.length === 0 && parsedPreferences.languages.length === 0 && !parsedPreferences.company_stage && (
                  <p className="text-sm text-slate-500">No extra preferences detected beyond the structured filters.</p>
                )}
              </div>
            </div>
          )}

          {!loading && results.length === 0 && !error && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-sm min-h-[420px] flex items-center justify-center p-8">
              <div className="text-center space-y-2">
                <div className="w-14 h-14 rounded-2xl bg-indigo-50 flex items-center justify-center mx-auto">
                  <BriefcaseBusiness className="h-7 w-7 text-indigo-200" />
                </div>
                <p className="font-semibold text-slate-500">Recent matches will appear here</p>
                <p className="text-sm text-slate-400">Use the filters to search for fresh jobs and track what you apply to</p>
              </div>
            </div>
          )}

          {results.length > 0 && (
            <div className="space-y-4">
              {results.map((job) => (
                <div key={job.job_url_canonical} className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 space-y-4">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <h2 className="text-sm font-semibold text-slate-900">{job.role}</h2>
                        {job.applied && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-100">
                            <CheckCircle2 className="h-3 w-3 mr-1" />
                            Applied tracked
                          </span>
                        )}
                      </div>
                      <p className="text-slate-700 font-semibold text-sm">{job.company}</p>
                      <div className="flex items-center gap-2 text-xs text-slate-500 mt-1.5">
                        <MapPin className="h-3 w-3" />
                        <span>{job.location}</span>
                        <span>·</span>
                        <span>{job.source_name}</span>
                        <span>·</span>
                        <span>{job.posted_at ? formatDate(job.posted_at) : 'Recent'}</span>
                      </div>
                    </div>

                    <div className="flex gap-2 flex-shrink-0">
                      <Button variant="outline" asChild className="rounded-xl h-9 text-xs">
                        <Link href={job.job_url} target="_blank">
                          <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
                          Open Job
                        </Link>
                      </Button>
                      <Button
                        onClick={() => markApplied(job)}
                        disabled={job.applied || applyingId === job.job_url_canonical}
                        className={`rounded-xl h-9 text-xs ${job.applied ? 'bg-emerald-500 text-white hover:bg-emerald-600' : 'gradient-brand text-white border-0 hover:opacity-90'}`}
                      >
                        {applyingId === job.job_url_canonical && <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />}
                        {job.applied ? 'Tracked' : 'Mark Applied'}
                      </Button>
                    </div>
                  </div>

                  <div className="rounded-xl border border-slate-100 bg-slate-50 p-3.5">
                    <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Citation</p>
                    <p className="text-sm text-slate-700">
                      <span className="font-medium">Canonical URL:</span>{' '}
                      <Link href={job.citation.canonical_url} target="_blank" className="text-indigo-600 hover:underline break-all text-xs">
                        {job.citation.canonical_url}
                      </Link>
                    </p>
                    <p className="text-sm text-slate-600 mt-1.5">{job.citation.extraction_note}</p>
                    <div className="flex flex-wrap gap-1.5 mt-2.5">
                      {job.citation.evidence.map((line) => (
                        <span key={line} className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-medium bg-white text-slate-600 border border-slate-200">
                          {line}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
