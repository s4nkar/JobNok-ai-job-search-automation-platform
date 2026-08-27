'use client'

import { useParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import {
  Badge, Card, CardContent, CardHeader, CardTitle,
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@jobnok/ui'
import { apiGet } from '@/lib/api'
import { ApiErrorState } from '@/components/ApiErrorState'
import { formatDateTime, formatRelativeTime } from '@/lib/format'
import type { CompanyDetailResponse } from '@/lib/types'

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-sm">{value ?? 'Not set'}</p>
    </div>
  )
}

export default function CompanyDetailPage() {
  const params = useParams<{ id: string }>()

  const { data, error, isLoading } = useQuery({
    queryKey: ['admin', 'crawler', 'company', params.id],
    queryFn: () => apiGet<CompanyDetailResponse>(`/api/admin/crawler/companies/${params.id}`),
  })

  if (error) return <ApiErrorState error={error} />
  if (isLoading || !data) return <p className="text-sm text-muted-foreground">Loading...</p>

  const { company, jobs, job_count } = data

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold">{company.name}</h1>
          <Badge>{company.status}</Badge>
        </div>
        {company.domain && <p className="text-sm text-muted-foreground">{company.domain}</p>}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Details</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Field label="Website" value={company.website_url} />
          <Field label="Career URL" value={company.career_url} />
          <Field label="ATS provider" value={company.ats_provider} />
          <Field label="ATS identifier" value={company.ats_identifier} />
          <Field label="Country" value={company.country} />
          <Field label="City" value={company.city} />
          <Field label="Discovery source" value={company.discovery_source} />
          <Field label="Crawl priority" value={company.crawl_priority} />
          <Field label="Crawl frequency" value={`${company.crawl_frequency_hours}h`} />
          <Field label="Consecutive failures" value={company.consecutive_failures} />
          <Field label="Last discovered" value={formatDateTime(company.last_discovered_at)} />
          <Field label="Last resolved" value={formatDateTime(company.last_resolved_at)} />
          <Field label="Last synced" value={formatDateTime(company.last_synced_at)} />
          <Field label="Next crawl" value={formatRelativeTime(company.next_crawl_at)} />
          <Field label="Last job found" value={formatDateTime(company.last_job_found_at)} />
        </CardContent>
      </Card>

      {company.last_error && (
        <Card className="border-destructive/50">
          <CardHeader>
            <CardTitle className="text-base text-destructive">Last error</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm">{company.last_error}</p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Jobs ({job_count})</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Title</TableHead>
                <TableHead>Location</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Posted</TableHead>
                <TableHead>Last seen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-sm text-muted-foreground">
                    No jobs synced for this company yet.
                  </TableCell>
                </TableRow>
              )}
              {jobs.map((job) => (
                <TableRow key={job.id}>
                  <TableCell>
                    <a href={job.canonical_url} target="_blank" rel="noreferrer" className="hover:underline">
                      {job.title}
                    </a>
                  </TableCell>
                  <TableCell className="text-sm">{job.location}</TableCell>
                  <TableCell className="text-sm">{job.source}</TableCell>
                  <TableCell className="text-sm">
                    {job.posted_at ? formatDateTime(job.posted_at) : 'Not provided by source'}
                  </TableCell>
                  <TableCell className="text-sm">{formatRelativeTime(job.last_seen_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
