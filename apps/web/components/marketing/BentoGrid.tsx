import Link from 'next/link'
import { ArrowUpRight } from 'lucide-react'
import { tools, toolBadgeColors } from '@/lib/tools'

// Explicit placement on a 4x4 desktop grid — Resume Tailor is the flagship
// tile (2x2), Tracker/Startup Scout/Salary get extra room, the rest are
// single cells. Mobile ignores all of this and just stacks in array order.
const layout: Record<string, string> = {
  'resume-tailor': 'lg:col-start-1 lg:col-span-2 lg:row-start-1 lg:row-span-2',
  'templates': 'lg:col-start-3 lg:col-span-1 lg:row-start-1 lg:row-span-1',
  'linkedin-fill': 'lg:col-start-4 lg:col-span-1 lg:row-start-1 lg:row-span-1',
  'cover-letter': 'lg:col-start-3 lg:col-span-1 lg:row-start-2 lg:row-span-1',
  'interview-prep': 'lg:col-start-4 lg:col-span-1 lg:row-start-2 lg:row-span-1',
  'tracker': 'lg:col-start-1 lg:col-span-2 lg:row-start-3 lg:row-span-1',
  'startup-scout': 'lg:col-start-3 lg:col-span-1 lg:row-start-3 lg:row-span-2',
  'salary': 'lg:col-start-4 lg:col-span-1 lg:row-start-3 lg:row-span-2',
  'startup-hunt': 'lg:col-start-1 lg:col-span-1 lg:row-start-4 lg:row-span-1',
  'bulk-email': 'lg:col-start-2 lg:col-span-1 lg:row-start-4 lg:row-span-1',
}

const large = new Set(['resume-tailor'])

export function BentoGrid() {
  return (
    <section id="tools" className="container py-20 sm:py-28">
      <div className="max-w-2xl mb-12">
        <p className="text-[11px] font-semibold text-indigo-600 uppercase tracking-widest mb-3">The toolkit</p>
        <h2 className="text-3xl sm:text-4xl font-bold text-slate-900 tracking-tight mb-4">
          Ten tools. One account. Nothing to configure.
        </h2>
        <p className="text-slate-500 text-base leading-relaxed">
          Every step of a job search, from finding the role to following up after the interview.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 lg:grid-rows-4 gap-4">
        {tools.map((tool, i) => {
          const Icon = tool.icon
          const isLarge = large.has(tool.slug)
          return (
            <Link
              key={tool.slug}
              href={tool.href}
              style={{ animationDelay: `${i * 40}ms` }}
              className={`animate-fade-in group relative flex flex-col justify-between rounded-2xl border border-slate-100 bg-white shadow-card p-5 hover:shadow-card-md hover:-translate-y-0.5 transition-all ${layout[tool.slug] ?? ''} ${isLarge ? 'sm:col-span-2' : ''}`}
            >
              <div className="flex items-start justify-between">
                <div className={`rounded-2xl border flex items-center justify-center shrink-0 ${toolBadgeColors[tool.color]} ${isLarge ? 'w-12 h-12' : 'w-10 h-10'}`}>
                  <Icon className={isLarge ? 'h-5 w-5' : 'h-[18px] w-[18px]'} />
                </div>
                <ArrowUpRight className="h-4 w-4 text-slate-300 group-hover:text-slate-500 transition-colors" />
              </div>

              <div className="mt-4">
                <h3 className={`font-semibold text-slate-900 ${isLarge ? 'text-xl mb-2' : 'text-sm mb-1'}`}>
                  {tool.label}
                </h3>
                <p className={`text-slate-500 leading-relaxed ${isLarge ? 'text-sm' : 'text-xs'}`}>
                  {tool.description}
                </p>
              </div>
            </Link>
          )
        })}
      </div>
    </section>
  )
}
