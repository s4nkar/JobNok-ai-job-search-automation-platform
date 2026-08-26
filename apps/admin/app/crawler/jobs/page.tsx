'use client'

import { Suspense, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import {
  Button, Input,
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@jobnok/ui'
import { apiGet } from '@/lib/api'
import { ApiErrorState } from '@/components/ApiErrorState'
import { Pager } from '@/components/Pager'
import { formatDateTime, formatRelativeTime } from '@/lib/format'
import type { JobListResponse } from '@/lib/types'

const PAGE_SIZE = 50

function JobsPageContent() {
  const searchParams = useSearchParams()
  const [search, setSearch] = useState('')
  const [companyId, setCompanyId] = useState(searchParams.get('company_id'))
  const [offset, setOffset] = useState(0)

  const params = new URLSearchParams()
  if (search.trim()) params.set('search', search.trim())
  if (companyId) params.set('company_id', companyId)
  params.set('limit', String(PAGE_SIZE))
  params.set('offset', String(offset))

  const { data, error, isLoading } = useQuery({
    queryKey: ['admin', 'crawler', 'jobs', search, companyId, offset],
    queryFn: () => apiGet<JobListResponse>(`/api/admin/crawler/jobs?${params.toString()}`),
  })

  function handleSearchChange(value: string) {
    setSearch(value)
    setOffset(0)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Jobs</h1>
        <p className="text-sm text-muted-foreground">
          {data ? `${data.total} total` : 'Loading...'}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="Search by title, company, or location"
          value={search}
          onChange={(e) => handleSearchChange(e.target.value)}
          className="max-w-xs"
        />
        {companyId && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setCompanyId(null)
              setOffset(0)
            }}
          >
            Clear company filter
          </Button>
        )}
      </div>

      {error && <ApiErrorState error={error} />}

      {!error && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Company</TableHead>
              <TableHead>Location</TableHead>
              <TableHead>Source</TableHead>
              <TableHead>Posted</TableHead>
              <TableHead>Last seen</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-sm text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            )}
            {!isLoading && data?.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-sm text-muted-foreground">
                  No jobs match these filters.
                </TableCell>
              </TableRow>
            )}
            {data?.items.map((job) => (
              <TableRow key={job.id}>
                <TableCell>
                  <a href={job.canonical_url} target="_blank" rel="noreferrer" className="font-medium hover:underline">
                    {job.title}
                  </a>
                </TableCell>
                <TableCell className="text-sm">{job.company}</TableCell>
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
      )}

      {data && (
        <Pager offset={offset} pageSize={PAGE_SIZE} total={data.total} onOffsetChange={setOffset} />
      )}
    </div>
  )
}

export default function JobsPage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Loading...</p>}>
      <JobsPageContent />
    </Suspense>
  )
}
