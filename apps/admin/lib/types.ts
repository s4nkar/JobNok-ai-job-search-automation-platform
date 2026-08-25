// Mirrors apps/api/app/modules/admin/service.py's response shapes.

export type CompanyStatus =
  | 'discovered'
  | 'resolving'
  | 'resolved'
  | 'active'
  | 'no_careers_page'
  | 'no_jobs'
  | 'failed'
  | 'disabled'

export interface CrawlerOverview {
  status_counts: Partial<Record<CompanyStatus, number>>
  total_companies: number
  unhealthy_count: number
  overdue_sync_count: number
  total_crawler_jobs: number
  last_discovered_at: string | null
  last_synced_at: string | null
  discovery_enabled: boolean
  discovery_batch_size: number
  sync_batch_size: number
}

export interface CompanyRegistryRow {
  id: string
  name: string
  normalized_name: string
  domain: string | null
  website_url: string | null
  country: string | null
  city: string | null
  discovery_source: string
  discovery_source_url: string | null
  discovery_source_id: string | null
  career_url: string | null
  ats_provider: string | null
  ats_identifier: string | null
  status: CompanyStatus
  crawl_frequency_hours: number
  crawl_priority: 'high' | 'normal' | 'low'
  last_discovered_at: string
  last_resolved_at: string | null
  last_synced_at: string | null
  next_crawl_at: string | null
  last_job_found_at: string | null
  last_job_change_at: string | null
  consecutive_failures: number
  last_error: string | null
  created_at: string
  updated_at: string
}

export interface CompanyListResponse {
  total: number
  items: CompanyRegistryRow[]
}

export interface JobRow {
  id: string
  source: string
  source_job_id: string
  origin_tool: string
  company_id: string | null
  title: string
  company: string
  location: string
  country: string | null
  description: string | null
  apply_url: string
  canonical_url: string
  posted_at: string | null
  fetched_at: string
  last_seen_at: string
  expires_at: string
}

export interface CompanyDetailResponse {
  company: CompanyRegistryRow
  jobs: JobRow[]
  job_count: number
}
