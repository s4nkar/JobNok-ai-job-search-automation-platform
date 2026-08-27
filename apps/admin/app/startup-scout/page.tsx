'use client'

import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@jobnok/ui'
import { apiGet } from '@/lib/api'
import { ApiErrorState } from '@/components/ApiErrorState'
import type { StartupScoutOverview } from '@/lib/types'

const OUTCOME_LABELS: Record<string, string> = {
  l1_hit: 'L1 - Redis cache',
  l2_full: 'L2 - company_registry',
  live: 'Live DDG scrape',
}

const OUTCOME_ORDER = ['l1_hit', 'l2_full', 'live']

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

export default function StartupScoutOverviewPage() {
  const { data, error, isLoading } = useQuery({
    queryKey: ['admin', 'startup-scout', 'overview'],
    queryFn: () => apiGet<StartupScoutOverview>('/api/admin/startup-scout/overview'),
    refetchInterval: 30_000,
  })

  if (error) return <ApiErrorState error={error} />
  if (isLoading || !data) return <p className="text-sm text-muted-foreground">Loading...</p>

  const total = data.total_searches_today
  const pct = (count: number) => (total > 0 ? Math.round((count / total) * 100) : 0)

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold">Startup Scout</h1>
        <p className="text-sm text-muted-foreground">
          Where today&apos;s searches are actually being served from - resets at midnight UTC.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Searches today" value={total} />
        {OUTCOME_ORDER.map((outcome) => (
          <StatCard
            key={outcome}
            label={OUTCOME_LABELS[outcome] || outcome}
            value={total > 0 ? `${pct(data.search_outcomes[outcome] ?? 0)}%` : '-'}
          />
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Search outcome breakdown</CardTitle>
        </CardHeader>
        <CardContent>
          {total === 0 ? (
            <p className="text-sm text-muted-foreground">No searches recorded yet today.</p>
          ) : (
            <div className="space-y-3">
              {OUTCOME_ORDER.map((outcome) => {
                const count = data.search_outcomes[outcome] ?? 0
                return (
                  <div key={outcome} className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <span>{OUTCOME_LABELS[outcome] || outcome}</span>
                      <span className="text-muted-foreground">{count} ({pct(count)}%)</span>
                    </div>
                    <div className="h-2 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full rounded-full bg-primary"
                        style={{ width: `${pct(count)}%` }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Reading this</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm text-muted-foreground">
          <p><span className="font-medium text-foreground">L1 - Redis cache</span>: identical search, still within its 6h cache window - zero cost.</p>
          <p><span className="font-medium text-foreground">L2 - company_registry</span>: a fresh search, but the location was already covered by the crawler&apos;s own company table - no DDG scrape needed.</p>
          <p><span className="font-medium text-foreground">Live DDG scrape</span>: the DB-first layers didn&apos;t cover the request, so a real scrape ran. A high share here for common locations is worth investigating.</p>
        </CardContent>
      </Card>
    </div>
  )
}
