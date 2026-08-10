'use client'

import {
  Radar,
  Compass,
  FileText,
  Mail,
  DollarSign,
  Sparkles,
  Users,
  MessageSquare,
  CheckCircle2,
  type LucideIcon,
} from 'lucide-react'

// Canvas dimensions spanning full vertical height of Hero
const W = 1200
const H = 680

type Node = {
  id: string
  label: string
  desc: string
  x: number
  y: number
  kind: 'user' | 'tool'
  icon?: LucideIcon
  color: 'amber' | 'cyan' | 'violet' | 'indigo' | 'emerald' | 'sky'
  hub?: boolean
  subtitle?: string
}

const nodes: Node[] = [
  // User Personas at top y = 40
  {
    id: 'userA',
    label: 'User A',
    subtitle: 'Startup Hunter',
    desc: 'Targets startups & founders',
    x: 100,
    y: 40,
    kind: 'user',
    color: 'amber',
  },
  {
    id: 'userB',
    label: 'User B',
    subtitle: 'Job Seeker',
    desc: 'Searches tech roles & emails',
    x: 1100,
    y: 40,
    kind: 'user',
    color: 'cyan',
  },

  // User A Branch — Left Margin Flow
  {
    id: 'scout',
    label: 'Search Startups',
    desc: 'Filter by sector, stage & stack',
    x: 100,
    y: 135,
    kind: 'tool',
    icon: Radar,
    color: 'amber',
  },
  {
    id: 'leads',
    label: 'Founder Lead Finder',
    desc: 'Scrape founder emails & contacts',
    x: 80,
    y: 235,
    kind: 'tool',
    icon: Users,
    color: 'amber',
  },
  {
    id: 'coldmsg',
    label: 'Cold Message AI',
    desc: 'Automated pitch DMs & sequences',
    x: 120,
    y: 335,
    kind: 'tool',
    icon: Sparkles,
    color: 'amber',
  },

  // User B Branch — Right Margin Flow
  {
    id: 'jobhunt',
    label: 'Search Jobs',
    desc: 'Scrape live listings matched to skills',
    x: 1100,
    y: 135,
    kind: 'tool',
    icon: Compass,
    color: 'cyan',
  },
  {
    id: 'bulk',
    label: 'Bulk Email Outreach',
    desc: 'Automated email campaigns',
    x: 1120,
    y: 235,
    kind: 'tool',
    icon: Mail,
    color: 'sky',
  },
  {
    id: 'salary',
    label: 'Salary Benchmark',
    desc: 'Compensation & negotiation data',
    x: 1080,
    y: 335,
    kind: 'tool',
    icon: DollarSign,
    color: 'emerald',
  },

  // Central Shared Core Hubs — Positioned Below CTAs (y = 425 to 590)
  {
    id: 'shared_resume',
    label: 'AI Resume & Cover Letter',
    desc: 'Auto-adapted CV & cover letter per role',
    x: 600,
    y: 425,
    kind: 'tool',
    icon: FileText,
    color: 'violet',
    hub: true,
  },
  {
    id: 'tracker',
    label: 'Progress Tracker Board',
    desc: 'Unified Kanban for leads & applications',
    x: 600,
    y: 510,
    kind: 'tool',
    icon: CheckCircle2,
    color: 'indigo',
    hub: true,
  },
  {
    id: 'interview',
    label: 'AI Interview Prep',
    desc: 'Role-specific Q&A drills & STAR practice',
    x: 600,
    y: 590,
    kind: 'tool',
    icon: MessageSquare,
    color: 'indigo',
  },
]

const nodeMap = Object.fromEntries(nodes.map((n) => [n.id, n]))

const edges: { from: string; to: string; dot: string }[] = [
  // User A flows
  { from: 'userA', to: 'scout', dot: '#f59e0b' },
  { from: 'scout', to: 'leads', dot: '#f59e0b' },
  { from: 'leads', to: 'coldmsg', dot: '#f59e0b' },
  { from: 'coldmsg', to: 'tracker', dot: '#f59e0b' },
  { from: 'scout', to: 'shared_resume', dot: '#8b5cf6' },

  // User B flows
  { from: 'userB', to: 'jobhunt', dot: '#06b6d4' },
  { from: 'userB', to: 'bulk', dot: '#0284c7' },
  { from: 'jobhunt', to: 'shared_resume', dot: '#8b5cf6' },
  { from: 'shared_resume', to: 'salary', dot: '#10b981' },
  { from: 'salary', to: 'tracker', dot: '#10b981' },
  { from: 'bulk', to: 'tracker', dot: '#0284c7' },

  // Central shared flows
  { from: 'shared_resume', to: 'tracker', dot: '#8b5cf6' },
  { from: 'tracker', to: 'interview', dot: '#4f46e5' },
]

function curve(x1: number, y1: number, x2: number, y2: number) {
  const midY = (y1 + y2) / 2
  return `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`
}

const iconBg: Record<string, string> = {
  amber: 'bg-amber-500/10 text-amber-600',
  cyan: 'bg-cyan-500/10 text-cyan-600',
  violet: 'bg-violet-500/10 text-violet-600',
  indigo: 'bg-indigo-500/10 text-indigo-600',
  emerald: 'bg-emerald-500/10 text-emerald-600',
  sky: 'bg-sky-500/10 text-sky-600',
}

const accentDots: Record<string, string> = {
  amber: 'bg-amber-500',
  cyan: 'bg-cyan-500',
  violet: 'bg-violet-600',
  indigo: 'bg-indigo-600',
  emerald: 'bg-emerald-500',
  sky: 'bg-sky-500',
}

export function FlowDiagram() {
  return (
    <div className="relative w-full h-full overflow-x-auto sm:overflow-visible">
      <div className="relative w-full top-20 h-full min-w-[720px] sm:min-w-0" style={{ aspectRatio: `${W} / ${H}` }}>
        {/* SVG Flow Lines */}
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="absolute inset-0 w-full h-full pointer-events-none"
          aria-hidden
        >
          {edges.map((e, i) => {
            const a = nodeMap[e.from]
            const b = nodeMap[e.to]
            if (!a || !b) return null
            const pathD = curve(a.x, a.y, b.x, b.y)

            return (
              <g key={i}>
                {/* Clear light-medium grey flow path line */}
                <path
                  d={pathD}
                  stroke="#e6e6e6ff"
                  strokeWidth={1.5}
                  strokeOpacity={0.75}
                  fill="none"
                />
                {/* Motion pulse dot */}
                <circle r={3} fill={e.dot} opacity={0.85}>
                  <animateMotion
                    dur={`${2.4 + (i % 3) * 0.4}s`}
                    begin={`${i * 0.2}s`}
                    repeatCount="indefinite"
                    path={pathD}
                  />
                </circle>
              </g>
            )
          })}
        </svg>

        {/* Subtle, Soft Home-Matching Service Cards */}
        {nodes.map((n) => {
          const isUser = n.kind === 'user'
          return (
            <div
              key={n.id}
              className="absolute -translate-x-1/2 -translate-y-1/2 pointer-events-auto"
              style={{
                left: `${(n.x / W) * 100}%`,
                top: `${(n.y / H) * 100}%`,
              }}
            >
              {/* User Persona Node */}
              {isUser ? (
                <div className="px-4 py-2 rounded-2xl border border-slate-200/50 bg-white/50 backdrop-blur-md shadow-2xs flex items-center gap-2.5 whitespace-nowrap">
                  <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${accentDots[n.color]}`} />
                  <div className="text-left">
                    <div className="text-xs font-bold text-slate-900 leading-tight">{n.label}</div>
                    <div className="text-[10px] text-slate-500 font-medium leading-tight mt-0.5">
                      {n.subtitle}
                    </div>
                  </div>
                </div>
              ) : (
                /* Light Translucent Card matching Home Background */
                <div
                  className={`relative pl-3.5 pr-4 py-2.5 rounded-2xl border backdrop-blur-md shadow-2xs flex items-center gap-3 overflow-hidden ${n.hub
                    ? 'bg-white/70 border-violet-200/50 shadow-xs'
                    : 'bg-white/50 border-slate-200/40'
                    } ${n.hub ? 'w-[215px] sm:w-[230px]' : 'w-[185px] sm:w-[200px]'}`}
                >
                  {/* Soft Accent Dot */}
                  {/* <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${accentDots[n.color]}`} /> */}

                  {/* Soft Icon Badge */}
                  <div
                    className={`w-8 h-8 rounded-xl flex items-center justify-center shrink-0 ${iconBg[n.color]}`}
                  >
                    {n.icon && <n.icon className="h-4 w-4" />}
                  </div>

                  {/* Title & Integrated Description */}
                  <div className="text-left min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-1">
                      <span className="text-[11.5px] font-bold text-slate-900 leading-tight whitespace-nowrap">
                        {n.label}
                      </span>
                    </div>
                    <span className="text-[9.5px] font-normal text-slate-500 leading-tight block truncate mt-0.5">
                      {n.desc}
                    </span>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
