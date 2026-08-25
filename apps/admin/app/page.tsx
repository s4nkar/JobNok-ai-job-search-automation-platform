'use client'

import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, Badge } from '@jobnok/ui'
import { apiGet } from '@/lib/api'
import { ApiErrorState } from '@/components/ApiErrorState'
import { formatRelativeTime } from '@/lib/format'
import type { CrawlerOverview, CompanyStatus } from '@/lib/types'

const STATUS_LABELS: Record<CompanyStatus, string> = {
  discovered: 'Discovered',
  resolving: 'Resolving',
  resolved: 'Resolved',
  active: 'Active',
  no_careers_page: 'No careers page',
  no_jobs: 'No jobs found',
  failed: 'Failed',
  disabled: 'Disabled',
}

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

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-3xl">{value}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">{label}</p>
      </CardContent>
    </Card>
  )
}

export default function OverviewPage() {
  const { data, error, isLoading } = useQuery({
    queryKey: ['admin', 'crawler', 'overview'],
    queryFn: () => apiGet<CrawlerOverview>('/api/admin/crawler/overview'),
    refetchInterval: 30_000,
  })

  if (error) return <ApiErrorState error={error} />
  if (isLoading || !data) return <p className="text-sm text-muted-foreground">Loading...</p>

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold">Crawler overview</h1>
        <p className="text-sm text-muted-foreground">
          Discovery {data.discovery_enabled ? 'is enabled' : 'is disabled'} · last discovered{' '}
          {formatRelativeTime(data.last_discovered_at)} · last synced {formatRelativeTime(data.last_synced_at)}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Total companies" value={data.total_companies} />
        <StatCard label="Crawler-sourced jobs" value={data.total_crawler_jobs} />
        <StatCard label="Backing off (failures)" value={data.unhealthy_count} />
        <StatCard label="Overdue for sync" value={data.overdue_sync_count} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Companies by status</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-3">
            {(Object.keys(STATUS_LABELS) as CompanyStatus[]).map((status) => (
              <div key={status} className="flex items-center gap-2 rounded-lg border px-3 py-2">
                <Badge variant={STATUS_VARIANT[status]}>{STATUS_LABELS[status]}</Badge>
                <span className="text-sm font-medium">{data.status_counts[status] ?? 0}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Config</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm text-muted-foreground">
          <p>Discovery batch size: {data.discovery_batch_size} pages/run</p>
          <p>Sync batch size: {data.sync_batch_size} companies/tick</p>
        </CardContent>
      </Card>
    </div>
  )
}
