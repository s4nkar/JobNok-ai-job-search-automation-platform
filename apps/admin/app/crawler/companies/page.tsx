'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import {
  Badge, Input, Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@jobnok/ui'
import { apiGet } from '@/lib/api'
import { ApiErrorState } from '@/components/ApiErrorState'
import { Pager } from '@/components/Pager'
import { formatRelativeTime } from '@/lib/format'
import type { CompanyListResponse, CompanyStatus } from '@/lib/types'

const PAGE_SIZE = 50

const STATUS_OPTIONS: CompanyStatus[] = [
  'discovered', 'resolving', 'resolved', 'active', 'no_careers_page', 'no_jobs', 'failed', 'disabled',
]

const STATUS_VARIANT: Record<CompanyStatus, 'default' | 'secondary' | 'destructive' | 'warning' | 'success'> = {
  discovered: 'secondary',
  resolving: 'secondary',
  resolved: 'secondary',
  active: 'success',
  no_careers_page: 'warning',
  no_jobs: 'warning',
  failed: 'destructive',
  disabled: 'secondary',
}

export default function CompaniesPage() {
  const [status, setStatus] = useState<string>('all')
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)

  const params = new URLSearchParams()
  if (status !== 'all') params.set('status', status)
  if (search.trim()) params.set('search', search.trim())
  params.set('limit', String(PAGE_SIZE))
  params.set('offset', String(offset))

  const { data, error, isLoading } = useQuery({
    queryKey: ['admin', 'crawler', 'companies', status, search, offset],
    queryFn: () => apiGet<CompanyListResponse>(`/api/admin/crawler/companies?${params.toString()}`),
  })

  function handleStatusChange(value: string) {
    setStatus(value)
    setOffset(0)
  }

  function handleSearchChange(value: string) {
    setSearch(value)
    setOffset(0)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Companies</h1>
        <p className="text-sm text-muted-foreground">
          {data ? `${data.total} total` : 'Loading...'}
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Input
          placeholder="Search by name or domain"
          value={search}
          onChange={(e) => handleSearchChange(e.target.value)}
          className="max-w-xs"
        />
        <Select value={status} onValueChange={handleStatusChange}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {STATUS_OPTIONS.map((s) => (
              <SelectItem key={s} value={s}>{s}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {error && <ApiErrorState error={error} />}

      {!error && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>ATS</TableHead>
              <TableHead>Jobs</TableHead>
              <TableHead>Failures</TableHead>
              <TableHead>Last synced</TableHead>
              <TableHead>Next crawl</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-sm text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            )}
            {!isLoading && data?.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-sm text-muted-foreground">
                  No companies match these filters.
                </TableCell>
              </TableRow>
            )}
            {data?.items.map((company) => (
              <TableRow key={company.id}>
                <TableCell>
                  <Link href={`/crawler/companies/${company.id}`} className="font-medium hover:underline">
                    {company.name}
                  </Link>
                  {company.domain && (
                    <p className="text-xs text-muted-foreground">{company.domain}</p>
                  )}
                </TableCell>
                <TableCell>
                  <Badge variant={STATUS_VARIANT[company.status]}>{company.status}</Badge>
                </TableCell>
                <TableCell className="text-sm">{company.ats_provider || 'Not resolved'}</TableCell>
                <TableCell className="text-sm">
                  {company.job_count > 0 ? (
                    <Link
                      href={`/crawler/jobs?company_id=${company.id}`}
                      className="text-primary hover:underline"
                    >
                      {company.job_count} job{company.job_count === 1 ? '' : 's'}
                    </Link>
                  ) : (
                    <span className="text-muted-foreground">No jobs</span>
                  )}
                </TableCell>
                <TableCell className="text-sm">{company.consecutive_failures}</TableCell>
                <TableCell className="text-sm">{formatRelativeTime(company.last_synced_at)}</TableCell>
                <TableCell className="text-sm">{formatRelativeTime(company.next_crawl_at)}</TableCell>
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
