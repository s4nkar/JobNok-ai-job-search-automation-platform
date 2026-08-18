import {
  FileText, Linkedin, FileSearch, PenLine, MessageSquare,
  Briefcase, Compass, DollarSign, Mail, Radar, Search, type LucideIcon,
} from 'lucide-react'

// Every tool shares one brand accent — tools are told apart by icon shape
// and label, not by hue. (Previously an 11-color rainbow, one hue per tool;
// consolidated for a single, restrained enterprise palette.)
export type ToolColor = 'indigo'

// Light-mode badge treatment — shared by the marketing bento grid, footer,
// and the (auth) branded panel, all of which now sit on a light background.
export const toolBadgeColors: Record<ToolColor, string> = {
  indigo: 'bg-indigo-50 text-indigo-600 border-indigo-100',
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
    color: 'indigo',
  },
  {
    slug: 'templates',
    href: '/templates',
    label: 'Smart Templates',
    description: 'Reusable resume, cover letter, and outreach templates with fill-in placeholders.',
    icon: FileText,
    color: 'indigo',
  },
  {
    slug: 'linkedin-fill',
    href: '/linkedin-fill',
    label: 'LinkedIn Auto-Fill',
    description: 'Scrapes a job posting and auto-fills the LinkedIn Easy Apply form for you.',
    icon: Linkedin,
    color: 'indigo',
  },
  {
    slug: 'cover-letter',
    href: '/cover-letter',
    label: 'Cover Letter',
    description: 'Generates a tailored cover letter from your resume and the job description.',
    icon: PenLine,
    color: 'indigo',
  },
  {
    slug: 'interview-prep',
    href: '/interview-prep',
    label: 'Interview Prep',
    description: 'Likely interview questions and talking points based on the role and your background.',
    icon: MessageSquare,
    color: 'indigo',
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
    color: 'indigo',
  },
  {
    slug: 'salary',
    href: '/salary',
    label: 'Salary Research',
    description: 'Pulls comparable salary ranges for a role, level, and location.',
    icon: DollarSign,
    color: 'indigo',
  },
  {
    slug: 'startup-hunt',
    href: '/startup-hunt',
    label: 'Startup Hunt',
    description: 'Tracks outreach to startups and the artifacts (notes, messages) tied to each one.',
    icon: Compass,
    color: 'indigo',
  },
  {
    slug: 'bulk-email',
    href: '/bulk-email',
    label: 'Bulk Email',
    description: 'Sends personalized outreach emails to a recipient list, queued and rate-limited.',
    icon: Mail,
    color: 'indigo',
  },
  {
    slug: 'recent-job-search',
    href: '/recent-job-search',
    label: 'Recent Job Search',
    description: 'General-market job search across Germany, the UK, and more — any company, any role, powered by Adzuna.',
    icon: Search,
    color: 'indigo',
  },
]
