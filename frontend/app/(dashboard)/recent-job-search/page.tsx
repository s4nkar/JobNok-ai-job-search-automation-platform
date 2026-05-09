'use client'

import Link from 'next/link'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from '@/components/ui/use-toast'
import { apiFetch } from '@/lib/api'
import { config } from '@/lib/config'
import { formatDate } from '@/lib/utils'
import { JobSearchResponse, JobSearchResult } from '@/lib/types'
import {
  BriefcaseBusiness,
  CheckCircle2,
  ExternalLink,
  Info,
  Loader2,
  MapPin,
  Search,
  Sparkles,
} from 'lucide-react'

const schema = z.object({
  query: z.string().min(2, 'Enter a role or keyword'),
  location: z.string().min(2, 'Enter a location'),
  country: z.string().optional(),
  posted_within_hours: z.coerce.number().int().min(1).max(720),
  result_limit: z.coerce.number().int().min(1).max(50),
  remote_only: z.enum(['false', 'true']).default('false'),
  preferences_prompt: z.string().optional(),
})

type FormData = z.infer<typeof schema>

const DEFAULT_VALUES: FormData = {
  query: 'Software Engineer',
  location: 'Germany',
  country: 'Germany',
  posted_within_hours: 24,
  result_limit: 10,
  remote_only: 'false',
  preferences_prompt: 'small pre seed startups, english preferred',
}

export default function RecentJobSearchPage() {
  const [loading, setLoading] = useState(false)
  const [applyingId, setApplyingId] = useState<string | null>(null)
  const [results, setResults] = useState<JobSearchResult[]>([])
  const [parsedPreferences, setParsedPreferences] = useState<JobSearchResponse['parsed_preferences'] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { toast } = useToast()

  const { register, handleSubmit, setValue, watch, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: DEFAULT_VALUES,
  })

  const postedHours = watch('posted_within_hours')
  const remoteOnly = watch('remote_only')

  async function onSubmit(data: FormData) {
    setLoading(true)
    setError(null)

    try {
      const res = await apiFetch('/api/job-search/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...data,
          country: data.country?.trim() || null,
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
      toast({ title: 'Application tracked', description: 'This job is now synced to your Follow-Up Tracker.' })
    } catch {
      toast({ title: 'Could not update tracking', description: 'Network error. Please try again.', variant: 'destructive' })
    } finally {
      setApplyingId(null)
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Recent Job Search</h1>
        <p className="text-slate-500 text-sm mt-1">
          Search fresh ATS job postings, keep citations, and sync applied roles into your tracker
        </p>
      </div>

      <Alert className="mb-6">
        <Info className="h-4 w-4" />
        <AlertDescription>
          <strong>{config.rateLimits.jobSearchPerDay} searches/day</strong> on the free tier. Sources come from configured
          Greenhouse and Lever ATS boards and each result keeps a citation trail.
        </AlertDescription>
      </Alert>

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-1">
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Search Filters</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-1">
                  <Label>Role or keywords</Label>
                  <Input placeholder="Founding Engineer" {...register('query')} />
                  {errors.query && <p className="text-xs text-destructive">{errors.query.message}</p>}
                </div>

                <div className="space-y-1">
                  <Label>Location</Label>
                  <Input placeholder="Berlin or Germany" {...register('location')} />
                  {errors.location && <p className="text-xs text-destructive">{errors.location.message}</p>}
                </div>

                <div className="space-y-1">
                  <Label>Country</Label>
                  <Input placeholder="Germany" {...register('country')} />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <Label>Posted within</Label>
                    <Select value={String(postedHours)} onValueChange={(v) => setValue('posted_within_hours', parseInt(v, 10))}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="24">24 hours</SelectItem>
                        <SelectItem value="72">72 hours</SelectItem>
                        <SelectItem value="168">7 days</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1">
                    <Label>Result limit</Label>
                    <Input type="number" min={1} max={50} {...register('result_limit')} />
                  </div>
                </div>

                <div className="space-y-1">
                  <Label>Remote only</Label>
                  <Select value={remoteOnly} onValueChange={(v) => setValue('remote_only', v as 'false' | 'true')}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="false">Include onsite and hybrid</SelectItem>
                      <SelectItem value="true">Remote only</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1">
                  <Label>Preference prompt</Label>
                  <Textarea
                    rows={4}
                    placeholder="small pre seed startups, english preferred, product-minded teams"
                    {...register('preferences_prompt')}
                  />
                </div>
              </CardContent>
            </Card>

            <Button type="submit" className="w-full" disabled={loading}>
              {loading
                ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Searching…</>
                : <><Search className="h-4 w-4 mr-2" /> Find Recent Jobs</>
              }
            </Button>
          </form>
        </div>

        <div className="col-span-2 space-y-4">
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {parsedPreferences && (
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-amber-500" />
                  <CardTitle className="text-base">Parsed Preferences</CardTitle>
                </div>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                {parsedPreferences.keywords.map((keyword) => (
                  <Badge key={keyword} variant="secondary">{keyword}</Badge>
                ))}
                {parsedPreferences.languages.map((language) => (
                  <Badge key={language} variant="outline">{language}</Badge>
                ))}
                {parsedPreferences.company_stage && (
                  <Badge className="bg-amber-100 text-amber-900 hover:bg-amber-100">{parsedPreferences.company_stage}</Badge>
                )}
                {parsedPreferences.keywords.length === 0 && parsedPreferences.languages.length === 0 && !parsedPreferences.company_stage && (
                  <p className="text-sm text-slate-500">No extra preferences detected beyond the structured filters.</p>
                )}
              </CardContent>
            </Card>
          )}

          {!loading && results.length === 0 && !error && (
            <Card className="min-h-[420px] flex items-center justify-center">
              <CardContent className="text-center text-slate-400 pt-6">
                <BriefcaseBusiness className="h-12 w-12 mx-auto mb-3 opacity-20" />
                <p>Recent ATS matches will appear here</p>
                <p className="text-sm mt-1">Use the filters to search for fresh jobs and track what you apply to</p>
              </CardContent>
            </Card>
          )}

          {results.length > 0 && (
            <div className="space-y-4">
              {results.map((job) => (
                <Card key={job.job_url_canonical}>
                  <CardContent className="pt-5 space-y-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <h2 className="text-lg font-semibold text-slate-900">{job.role}</h2>
                          {job.applied && (
                            <Badge className="bg-green-100 text-green-900 hover:bg-green-100">
                              <CheckCircle2 className="h-3.5 w-3.5 mr-1" />
                              Applied tracked
                            </Badge>
                          )}
                        </div>
                        <p className="text-slate-700 font-medium">{job.company}</p>
                        <div className="flex items-center gap-2 text-sm text-slate-500 mt-1">
                          <MapPin className="h-3.5 w-3.5" />
                          <span>{job.location}</span>
                          <span>•</span>
                          <span>{job.source_name}</span>
                          <span>•</span>
                          <span>{job.posted_at ? formatDate(job.posted_at) : 'Recent date unavailable'}</span>
                        </div>
                      </div>

                      <div className="flex gap-2">
                        <Button variant="outline" asChild>
                          <Link href={job.job_url} target="_blank">
                            <ExternalLink className="h-4 w-4 mr-2" />
                            Open Job
                          </Link>
                        </Button>
                        <Button
                          onClick={() => markApplied(job)}
                          disabled={job.applied || applyingId === job.job_url_canonical}
                        >
                          {applyingId === job.job_url_canonical && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                          {job.applied ? 'Tracked' : 'Mark Applied'}
                        </Button>
                      </div>
                    </div>

                    <div className="rounded-lg border bg-slate-50 p-3">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">Citation</p>
                      <p className="text-sm text-slate-700">
                        <span className="font-medium">Canonical URL:</span>{' '}
                        <Link href={job.citation.canonical_url} target="_blank" className="text-blue-600 hover:underline break-all">
                          {job.citation.canonical_url}
                        </Link>
                      </p>
                      <p className="text-sm text-slate-700 mt-2">{job.citation.extraction_note}</p>
                      <div className="flex flex-wrap gap-2 mt-3">
                        {job.citation.evidence.map((line) => (
                          <Badge key={line} variant="outline">{line}</Badge>
                        ))}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
