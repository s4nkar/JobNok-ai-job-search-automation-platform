import {
  FileText, Linkedin, FileSearch, PenLine, MessageSquare,
  Briefcase, Compass, DollarSign, Mail, Radar, Search, type LucideIcon,
} from 'lucide-react'

export type ToolColor =
  | 'rose' | 'blue' | 'violet' | 'pink' | 'teal'
  | 'indigo' | 'orange' | 'cyan' | 'emerald' | 'amber' | 'sky'

// Light-mode badge treatment — shared by the marketing bento grid, footer,
// and the (auth) branded panel, all of which now sit on a light background.
export const toolBadgeColors: Record<ToolColor, string> = {
  rose: 'bg-rose-50 text-rose-600 border-rose-100',
  blue: 'bg-blue-50 text-blue-600 border-blue-100',
  violet: 'bg-violet-50 text-violet-600 border-violet-100',
  pink: 'bg-pink-50 text-pink-600 border-pink-100',
  teal: 'bg-teal-50 text-teal-600 border-teal-100',
  indigo: 'bg-indigo-50 text-indigo-600 border-indigo-100',
  orange: 'bg-orange-50 text-orange-600 border-orange-100',
  cyan: 'bg-cyan-50 text-cyan-600 border-cyan-100',
  emerald: 'bg-emerald-50 text-emerald-600 border-emerald-100',
  amber: 'bg-amber-50 text-amber-600 border-amber-100',
  sky: 'bg-sky-50 text-sky-600 border-sky-100',
}

export interface Tool {
  slug: string
  href: string
  label: string
  description: string
  icon: LucideIcon
  color: ToolColor
}

export const tools: Tool[] = [
  {
    slug: 'resume-tailor',
    href: '/resume-tailor',
    label: 'Resume Tailor',
    description: 'Deterministic match score against a real job description, plus AI-rewritten bullets and summary.',
    icon: FileSearch,
    color: 'violet',
  },
  {
    slug: 'templates',
    href: '/templates',
    label: 'Smart Templates',
    description: 'Reusable resume, cover letter, and outreach templates with fill-in placeholders.',
    icon: FileText,
    color: 'rose',
  },
  {
    slug: 'linkedin-fill',
    href: '/linkedin-fill',
    label: 'LinkedIn Auto-Fill',
    description: 'Scrapes a job posting and auto-fills the LinkedIn Easy Apply form for you.',
    icon: Linkedin,
    color: 'blue',
  },
  {
    slug: 'cover-letter',
    href: '/cover-letter',
    label: 'Cover Letter',
    description: 'Generates a tailored cover letter from your resume and the job description.',
    icon: PenLine,
    color: 'pink',
  },
  {
    slug: 'interview-prep',
    href: '/interview-prep',
    label: 'Interview Prep',
    description: 'Likely interview questions and talking points based on the role and your background.',
    icon: MessageSquare,
    color: 'teal',
  },
  {
    slug: 'tracker',
    href: '/tracker',
    label: 'Follow-Up Tracker',
    description: 'Tracks every application by stage and reminds you when a follow-up is overdue.',
    icon: Briefcase,
    color: 'indigo',
  },
  {
    slug: 'startup-scout',
    href: '/startup-scout',
    label: 'Startup Scout',
    description: 'Finds early-stage companies and the contacts worth reaching out to.',
    icon: Radar,
    color: 'cyan',
  },
  {
    slug: 'salary',
    href: '/salary',
    label: 'Salary Research',
    description: 'Pulls comparable salary ranges for a role, level, and location.',
    icon: DollarSign,
    color: 'emerald',
  },
  {
    slug: 'startup-hunt',
    href: '/startup-hunt',
    label: 'Startup Hunt',
    description: 'Tracks outreach to startups and the artifacts (notes, messages) tied to each one.',
    icon: Compass,
    color: 'orange',
  },
  {
    slug: 'bulk-email',
    href: '/bulk-email',
    label: 'Bulk Email',
    description: 'Sends personalized outreach emails to a recipient list, queued and rate-limited.',
    icon: Mail,
    color: 'amber',
  },
  {
    slug: 'recent-job-search',
    href: '/recent-job-search',
    label: 'Recent Job Search',
    description: 'Searches fresh ATS job postings by role, location, and recency, with tracker sync.',
    icon: Search,
    color: 'sky',
  },
]
