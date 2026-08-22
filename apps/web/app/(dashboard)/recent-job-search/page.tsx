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
import { BonusJob, JobSearchApplication, JobSearchResponse, JobSearchResult } from '@/lib/types'
import { queryKeys } from '@/lib/queryKeys'
import {
  Bookmark,
  BriefcaseBusiness,
  Building2,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ExternalLink,
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

// Major cities per country for the location field's <datalist> autocomplete
// - not exhaustive, just enough to let someone pick a real place instead of
// free-typing (and mistyping) it. "Bangloore" vs "Bangalore" is a real bug
// report: Adzuna's own location resolver silently returns zero results for
// an unrecognized place name, with nothing to tell the user why - this
// doesn't eliminate that (still free text, still possible to mistype
// something not in the list), but picking from suggestions avoids it for
// the common case.
const CITY_SUGGESTIONS: Record<string, string[]> = {
  de: ['Berlin', 'Munich', 'Hamburg', 'Frankfurt', 'Cologne', 'Stuttgart', 'Düsseldorf', 'Remote'],
  gb: ['London', 'Manchester', 'Birmingham', 'Edinburgh', 'Bristol', 'Leeds', 'Remote'],
  at: ['Vienna', 'Graz', 'Linz', 'Salzburg', 'Remote'],
  au: ['Sydney', 'Melbourne', 'Brisbane', 'Perth', 'Adelaide', 'Remote'],
  br: ['São Paulo', 'Rio de Janeiro', 'Belo Horizonte', 'Brasília', 'Curitiba', 'Remote'],
  ca: ['Toronto', 'Vancouver', 'Montreal', 'Calgary', 'Ottawa', 'Remote'],
  fr: ['Paris', 'Lyon', 'Marseille', 'Toulouse', 'Nice', 'Remote'],
  in: ['Bangalore', 'Mumbai', 'Delhi', 'Hyderabad', 'Pune', 'Chennai', 'Kolkata', 'Gurgaon', 'Noida', 'Kochi', 'Remote'],
  it: ['Milan', 'Rome', 'Turin', 'Bologna', 'Florence', 'Remote'],
  mx: ['Mexico City', 'Guadalajara', 'Monterrey', 'Puebla', 'Remote'],
  nl: ['Amsterdam', 'Rotterdam', 'The Hague', 'Utrecht', 'Eindhoven', 'Remote'],
  nz: ['Auckland', 'Wellington', 'Christchurch', 'Remote'],
  pl: ['Warsaw', 'Kraków', 'Wrocław', 'Poznań', 'Gdańsk', 'Remote'],
  ru: ['Moscow', 'Saint Petersburg', 'Novosibirsk', 'Remote'],
  sg: ['Singapore', 'Remote'],
  us: ['New York', 'San Francisco', 'Los Angeles', 'Chicago', 'Austin', 'Seattle', 'Boston', 'Remote'],
  za: ['Johannesburg', 'Cape Town', 'Pretoria', 'Durban', 'Remote'],
}

// Adzuna returns salary_min/salary_max in the searched country's own
// currency with no currency code attached - inferred here from the country
// filter so we don't slap a "$" on a EUR or GBP figure.
const ADZUNA_CURRENCY: Record<string, string> = {
  de: 'EUR', at: 'EUR', fr: 'EUR', it: 'EUR', nl: 'EUR',
  gb: 'GBP', au: 'AUD', br: 'BRL', ca: 'CAD', in: 'INR',
  mx: 'MXN', nz: 'NZD', pl: 'PLN', ru: 'RUB', sg: 'SGD',
  us: 'USD', za: 'ZAR',
}

function formatSalaryRange(min: number | null, max: number | null, countryCode: string): string | null {
  if (min == null && max == null) return null
  const currency = ADZUNA_CURRENCY[countryCode] || 'USD'
  const fmt = (n: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 0 }).format(n)
  if (min != null && max != null && min !== max) return `${fmt(min)} - ${fmt(max)}`
  return fmt((min ?? max) as number)
}

// LinkedIn-style relative freshness ("2h", "3d") shown alongside the absolute
// date - computed client-side from posted_at, no backend change needed.
function formatRelativeTime(dateStr: string): string | null {
  const diffMs = Date.now() - new Date(dateStr).getTime()
  if (diffMs < 0) return null
  const minutes = Math.floor(diffMs / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d`
  const weeks = Math.floor(days / 7)
  if (weeks < 5) return `${weeks}w`
  return `${Math.floor(days / 30)}mo`
}

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
  location: 'Berlin',
  country: 'de',
  posted_within_hours: 24,
  result_limit: 10,
  remote_only: 'false',
  preferences_prompt: 'Mid level roles, english preferred, product-minded teams',
}

export default function RecentJobSearchPage() {
  const queryClient = useQueryClient()
  const [loading, setLoading] = useState(false)
  const [applyingId, setApplyingId] = useState<string | null>(null)
  const [results, setResults] = useState<JobSearchResult[]>([])
  const [bonusJobs, setBonusJobs] = useState<BonusJob[]>([])
  // Distinguishes "haven't searched yet" from "searched, found nothing" -
  // those need different empty-state copy, and before the backend fix that
  // let a genuine zero-match search return successfully instead of erroring,
  // this distinction didn't matter because a real search never landed here.
  const [hasSearched, setHasSearched] = useState(false)
  const [parsedPreferences, setParsedPreferences] = useState<JobSearchResponse['parsed_preferences'] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [searchesRemaining, setSearchesRemaining] = useState<number | null>(null)
  const [lastSearchedCountry, setLastSearchedCountry] = useState('de')
  // Mobile-only: filters start collapsed so results are reachable without
  // scrolling past 7 fields first. Ignored at md+ (always expanded there).
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [expandedDescriptions, setExpandedDescriptions] = useState<Set<string>>(new Set())
  const { toast } = useToast()

  function toggleDescription(key: string) {
    setExpandedDescriptions((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

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
  const watchedQuery = watch('query')
  const watchedLocation = watch('location')
  const filterSummary = [watchedQuery, watchedLocation, postedHours ? `${postedHours}h` : null]
    .filter(Boolean)
    .join(' · ')

  async function onSubmit(data: FormData) {
    setLoading(true)
    setError(null)
    setHasSearched(true)
    setLastSearchedCountry(data.country)

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
        setBonusJobs([])
        setParsedPreferences(null)
        return
      }

      const payload = json as JobSearchResponse
      setResults(payload.results)
      setBonusJobs(payload.bonus_jobs)
      setParsedPreferences(payload.parsed_preferences)
      setSearchesRemaining(payload.searches_remaining)
    } catch {
      setError('Network error. Please try again.')
      setResults([])
      setBonusJobs([])
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
          job_description: job.description_text,
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
        <div className="hidden sm:flex page-header-icon bg-indigo-100">
          <Search className="h-5 w-5 text-indigo-600" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Recent Job Search</h1>
            <Link
              href="/tracker?tab=job-search"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-100 hover:bg-indigo-100 transition-colors flex-shrink-0"
            >
              <Bookmark className="h-3.5 w-3.5" />
              {tracked.length} tracked
            </Link>
          </div>
          <p className="text-slate-500 text-sm mt-0.5">
            Search live postings across India, Germany, the UK, and more. Any company, any role, powered by Jobnok.
          </p>
        </div>
      </div>

      {/* lg:, not md: - at md (768px, iPad portrait) a fixed 320px sidebar
          would leave the results column only ~420px wide while its cards'
          internal sm: breakpoints (640px) still key off full viewport width,
          not that column's actual space, so they'd assume room they don't
          have. Staying stacked through lg: keeps the column = viewport width
          the whole time those sm: breakpoints are active. */}
      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-5 items-start">
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="bg-white rounded-2xl border border-slate-100 shadow-sm lg:sticky lg:top-6 lg:max-h-[calc(100vh-2rem)] lg:flex lg:flex-col overflow-hidden"
        >
          {/* Mobile/tablet-only collapsible header - filters start closed so
              results are reachable without scrolling past every field first. */}
          <button
            type="button"
            onClick={() => setFiltersOpen((prev) => !prev)}
            className="w-full lg:hidden flex items-center justify-between gap-3 px-5 py-3.5"
          >
            <span className="flex items-center gap-2 text-xs font-semibold text-slate-500 uppercase tracking-wider flex-shrink-0">
              <SlidersHorizontal className="h-3.5 w-3.5 text-slate-400" />
              Filters
            </span>
            <span className="flex items-center gap-1.5 text-xs text-slate-500 font-normal normal-case min-w-0">
              <span className="truncate">{filterSummary}</span>
              {filtersOpen ? <ChevronUp className="h-3.5 w-3.5 flex-shrink-0" /> : <ChevronDown className="h-3.5 w-3.5 flex-shrink-0" />}
            </span>
          </button>

          <div className={`${filtersOpen ? 'block' : 'hidden'} lg:block lg:flex-1 lg:min-h-0 lg:overflow-y-auto scrollbar-hide lg:scroll-fade-y p-5 lg:pt-5 space-y-5 ${filtersOpen ? 'border-t border-slate-100 lg:border-t-0' : ''}`}>
            <div className="hidden lg:flex items-center gap-2 pb-1 border-b border-slate-100">
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
                placeholder="e.g. Berlin, or Remote"
                list="location-suggestions"
                className="rounded-xl h-9 text-sm border-slate-200 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200"
                {...register('location')}
              />
              <datalist id="location-suggestions">
                {(CITY_SUGGESTIONS[country] || []).map((city) => (
                  <option key={city} value={city} />
                ))}
              </datalist>
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
                placeholder="Mid level roles, english preferred, product-minded teams"
                className="rounded-xl text-sm border-slate-200 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200 resize-none"
                {...register('preferences_prompt')}
              />
              {errors.preferences_prompt && <p className="text-xs text-destructive">{errors.preferences_prompt.message}</p>}
              {parsedPreferences && (parsedPreferences.keywords.length > 0 || parsedPreferences.languages.length > 0 || parsedPreferences.company_stage) && (
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {parsedPreferences.keywords.map((keyword) => (
                    <span key={keyword} className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 text-slate-700">{keyword}</span>
                  ))}
                  {parsedPreferences.languages.map((language) => (
                    <span key={language} className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-50 text-slate-600 border border-slate-200">{language}</span>
                  ))}
                  {parsedPreferences.company_stage && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 text-amber-800 border border-amber-100">{parsedPreferences.company_stage}</span>
                  )}
                </div>
              )}
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
            <p className="text-center text-[11px] text-slate-400">
              {searchesRemaining !== null
                ? `${searchesRemaining} of ${config.rateLimits.jobSearchPerDay} searches left today`
                : `Up to ${config.rateLimits.jobSearchPerDay} searches/day on the free tier`}
            </p>
          </div>
        </form>

        <div className="min-w-0 space-y-4">
          {error && (
            <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl px-4 py-3 text-sm">
              {error}
            </div>
          )}

          {loading && (
            <div className="space-y-4">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 space-y-4 animate-pulse">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 space-y-2">
                      <div className="h-4 w-48 bg-slate-100 rounded-full" />
                      <div className="h-3.5 w-32 bg-slate-100 rounded-full" />
                      <div className="h-3 w-56 bg-slate-100 rounded-full" />
                    </div>
                    <div className="flex gap-2 flex-shrink-0">
                      <div className="h-9 w-24 bg-slate-100 rounded-xl" />
                      <div className="h-9 w-28 bg-slate-100 rounded-xl" />
                    </div>
                  </div>
                  <div className="h-16 bg-slate-50 rounded-xl border border-slate-100" />
                </div>
              ))}
            </div>
          )}

          {!loading && results.length === 0 && !error && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-sm min-h-[18rem] flex items-center justify-center p-6">
              <div className="text-center space-y-1">
                {hasSearched ? (
                  <>
                    <p className="font-semibold text-slate-500">No matches for this search</p>
                    <p className="text-sm text-slate-400">Double-check the location spelling, or try a broader location, a different role, or fewer filters</p>
                  </>
                ) : (
                  <>
                    <p className="font-semibold text-slate-500">Recent matches will appear here</p>
                    <p className="text-sm text-slate-400">Use the filters to search for fresh jobs and track what you apply to</p>
                  </>
                )}
              </div>
            </div>
          )}

          {!loading && results.length > 0 && (
            <div className="space-y-4">
              {results.map((job) => (
                <div key={job.job_url_canonical} className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 space-y-4">
                  <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <h3 className="text-base font-semibold text-slate-900">{job.role}</h3>
                        {job.applied && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-100">
                            <CheckCircle2 className="h-3 w-3 mr-1" />
                            Applied tracked
                          </span>
                        )}
                      </div>
                      <p className="text-slate-700 font-semibold text-sm">{job.company}</p>
                      <div className="flex items-center gap-x-2 gap-y-1 text-xs text-slate-500 mt-1.5 flex-wrap">
                        <span className="flex items-center gap-1"><MapPin className="h-3 w-3" />{job.location}</span>
                        {/* <span className="hidden sm:inline">·</span> */}
                        {/* <span>{job.source_name}</span> */}
                        <span className="hidden sm:inline">·</span>
                        <span>{job.posted_at ? formatDate(job.posted_at) : 'Recent'}</span>
                        {job.posted_at && formatRelativeTime(job.posted_at) && (
                          <>
                            <span className="hidden sm:inline">·</span>
                            <span>{formatRelativeTime(job.posted_at)}</span>
                          </>
                        )}
                        {formatSalaryRange(job.salary_min, job.salary_max, lastSearchedCountry) && (
                          <>
                            <span className="hidden sm:inline">·</span>
                            <span className="font-medium text-emerald-600">
                              {formatSalaryRange(job.salary_min, job.salary_max, lastSearchedCountry)}
                            </span>
                          </>
                        )}
                      </div>
                    </div>

                    <div className="flex gap-2 flex-wrap sm:flex-nowrap sm:flex-shrink-0">
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

                  <div className="rounded-xl border border-slate-100 p-3.5 space-y-2">
                    <div className="flex items-center gap-2">
                      <Building2 className="h-3.5 w-3.5 text-slate-400" />
                      <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Citation</p>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {job.citation.evidence.map((line) => (
                        <span key={line} className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-white text-slate-600 border border-slate-200">{line}</span>
                      ))}
                    </div>
                  </div>

                  {job.description_text && (
                    <>
                      <div className="mt-4">
                        <button
                          type="button"
                          onClick={() => toggleDescription(job.job_url_canonical)}
                          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900"
                        >
                          {expandedDescriptions.has(job.job_url_canonical) ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                          Job Description
                        </button>
                      </div>

                      {expandedDescriptions.has(job.job_url_canonical) && (
                        <div className="space-y-4 mt-4">
                          <div className="rounded-xl border border-slate-100 bg-slate-50 p-3.5 space-y-2">
                            <div className="max-h-[28rem] overflow-y-auto scrollbar-hide">
                              <p className="text-xs text-slate-700 whitespace-pre-wrap leading-relaxed">
                                {job.description_text}
                              </p>
                            </div>
                            <p className="text-xs text-slate-400 mt-2">
                              Open the job to read the full posting.
                            </p>
                          </div>
                        </div>
                      )}
                    </>
                  )}



                </div>
              ))}
            </div>
          )}

          {!loading && bonusJobs.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-3 rounded-2xl border border-l-4 border-slate-100 border-l-indigo-400 bg-white px-4 py-3 shadow-sm">
                <div className="w-9 h-9 rounded-xl bg-indigo-50 flex items-center justify-center flex-shrink-0">
                  <Sparkles className="h-4 w-4 text-indigo-500" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-slate-800">
                    {results.length === 0 ? "Don't worry! We've got you covered" : 'Bonus finds'}
                  </p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {results.length === 0
                      ? "Worth thinking outside the box! Here are some roles that match your search title, pulled from multiple locations."
                      : 'Extra roles matching your search title, pulled from a wider net with multiple locations.'}
                  </p>
                </div>
                {/* <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-600 flex-shrink-0">
                  Top {bonusJobs.length} found
                </span> */}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {bonusJobs.map((job) => (
                  <Link
                    key={job.job_url_canonical}
                    href={job.job_url}
                    target="_blank"
                    className="block bg-white rounded-xl border border-slate-100 p-3.5 hover:border-indigo-200 transition-colors"
                  >
                    <p className="text-sm font-semibold text-slate-800 truncate">{job.role}</p>
                    <p className="text-xs text-slate-600 mt-0.5 truncate">{job.company}</p>
                    <div className="flex items-center justify-between gap-2 mt-1.5">
                      <span className="flex items-center gap-1 text-xs text-slate-400 min-w-0">
                        <MapPin className="h-3 w-3 flex-shrink-0" />
                        <span className="truncate">{job.location}</span>
                        {job.posted_at && formatRelativeTime(job.posted_at) && (
                          <span className="flex-shrink-0">· {formatRelativeTime(job.posted_at)}</span>
                        )}
                      </span>
                      <ExternalLink className="h-3.5 w-3.5 text-slate-300 flex-shrink-0" />
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div >
  )
}
