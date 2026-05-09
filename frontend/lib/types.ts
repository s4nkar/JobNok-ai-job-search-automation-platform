export type TemplateCategory =
  | 'Cold DM - Recruiter'
  | 'Cold DM - Hiring Manager'
  | 'Follow-Up'
  | 'Referral Ask'
  | 'Email Outreach'
  | 'Custom'

export const TEMPLATE_CATEGORIES: TemplateCategory[] = [
  'Cold DM - Recruiter',
  'Cold DM - Hiring Manager',
  'Follow-Up',
  'Referral Ask',
  'Email Outreach',
  'Custom',
]

export interface Template {
  id: string
  user_id: string
  name: string
  category: TemplateCategory
  content: string
  placeholders: string[]
  use_count: number
  created_at: string
  is_prebuilt?: boolean
}

export type ApplicationStatus =
  | 'Applied'
  | 'Phone Screen'
  | 'Interview'
  | 'Offer'
  | 'Rejected'
  | 'Withdrawn'

export const APPLICATION_STATUSES: ApplicationStatus[] = [
  'Applied',
  'Phone Screen',
  'Interview',
  'Offer',
  'Rejected',
  'Withdrawn',
]

export const STATUS_COLORS: Record<ApplicationStatus, string> = {
  Applied:       'bg-blue-100 text-blue-800',
  'Phone Screen': 'bg-yellow-100 text-yellow-800',
  Interview:     'bg-purple-100 text-purple-800',
  Offer:         'bg-green-100 text-green-800',
  Rejected:      'bg-red-100 text-red-800',
  Withdrawn:     'bg-gray-100 text-gray-800',
}

export interface JobApplication {
  id: string
  user_id: string
  company: string
  role: string
  applied_at: string
  status: ApplicationStatus
  follow_up_date: string | null
  notes: string | null
  salary_min: number | null
  salary_max: number | null
  created_at: string
  updated_at: string
}

export type CampaignStatus = 'draft' | 'queued' | 'sending' | 'completed' | 'paused' | 'failed'
export type RecipientStatus = 'queued' | 'sending' | 'sent' | 'failed'

export interface EmailCampaign {
  id: string
  user_id: string
  name: string
  subject: string
  body: string
  status: CampaignStatus
  delay_seconds: number
  created_at: string
}

export interface EmailRecipient {
  id: string
  campaign_id: string
  email: string
  name: string
  variables: Record<string, string>
  status: RecipientStatus
  sent_at: string | null
  error: string | null
}

export interface LinkedInProfile {
  name?: string
  headline?: string
  current_role?: string
  current_company?: string
  location?: string
  about?: string
  recent_experience?: string
  skills?: string[]
  education?: string
  profile_url: string
}

export interface ResumeTailorResult {
  match_score: number
  matched_keywords: string[]
  missing_keywords: Array<{ keyword: string; suggested_placement: string }>
  bullet_rewrites: Array<{ original: string; improved: string }>
  summary: string
}

export interface InterviewQuestion {
  question: string
  framework: string
  answer_framework: string
  tips: string[]
}

export interface SalaryResearchResult {
  job_title: string
  location: string
  median_salary: string
  salary_range: { min: string; max: string }
  factors: string[]
  negotiation_points: string[]
  data_sources: string[]
}

export type JobSearchApplicationStatus = 'saved' | 'applied' | 'skipped'

export interface JobCitation {
  source_name: string
  canonical_url: string
  job_url: string
  posted_at: string | null
  evidence: string[]
  extraction_note: string
}

export interface JobSearchResult {
  source_name: string
  provider_type: string
  external_job_id: string | null
  company: string
  role: string
  location: string
  job_url: string
  job_url_canonical: string
  posted_at: string | null
  applied: boolean
  application_status: JobSearchApplicationStatus | null
  tracked_application_id: string | null
  citation: JobCitation
}

export interface JobSearchResponse {
  results: JobSearchResult[]
  parsed_preferences: {
    keywords: string[]
    languages: string[]
    company_stage: string | null
    notes: string[]
  }
  configured_source_count: number
}

export interface JobSearchApplication {
  id: string
  user_id: string
  job_url: string
  job_url_canonical: string
  source_name: string
  external_job_id: string | null
  company: string
  role: string
  location: string
  posted_at: string | null
  discovered_at: string
  applied_at: string | null
  application_status: JobSearchApplicationStatus
  tracker_application_id: string | null
  citation_payload: JobCitation
  search_context: Record<string, unknown>
  created_at: string
  updated_at: string
}
