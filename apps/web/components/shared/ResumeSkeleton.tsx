import { cn } from '@jobnok/ui'

// A resume-shaped loading placeholder (header + section bars + bullets)
// instead of a flat pulsing rectangle — used anywhere a real resume preview
// is still being fetched/rendered: the editor's main preview canvas
// (`compact={false}`) and ScaledResumeThumb's loading fallback, which covers
// the Layouts rail, the mobile template picker, and My Docs cards
// (`compact={true}`, since those render at a fraction of the size).
export function ResumeSkeleton({ className, compact = false }: { className?: string; compact?: boolean }) {
  if (compact) {
    return (
      <div className={cn('w-full h-full bg-white p-3 flex flex-col gap-1.5 animate-pulse', className)}>
        <div className="h-2 w-2/3 bg-slate-200 rounded mx-auto" />
        <div className="h-1.5 w-4/5 bg-slate-100 rounded mx-auto mb-1" />
        <div className="h-px w-full bg-slate-100 my-0.5" />
        <div className="h-1.5 w-full bg-slate-100 rounded" />
        <div className="h-1.5 w-5/6 bg-slate-100 rounded" />
        <div className="h-1.5 w-full bg-slate-100 rounded" />
        <div className="h-1.5 w-2/3 bg-slate-100 rounded" />
      </div>
    )
  }

  return (
    <div className={cn('w-full h-full bg-white p-10 flex flex-col gap-5 animate-pulse', className)}>
      {/* Header: name + title + contact line */}
      <div className="flex flex-col items-center gap-2.5">
        <div className="h-5 w-1/2 bg-slate-200 rounded" />
        <div className="h-3 w-2/3 bg-slate-100 rounded" />
        <div className="h-2.5 w-3/4 bg-slate-100 rounded" />
      </div>
      <div className="h-px w-full bg-slate-100" />

      {/* Summary section */}
      <div className="space-y-2">
        <div className="h-3 w-1/3 bg-slate-200 rounded" />
        <div className="h-2.5 w-full bg-slate-100 rounded" />
        <div className="h-2.5 w-full bg-slate-100 rounded" />
        <div className="h-2.5 w-4/5 bg-slate-100 rounded" />
      </div>

      {/* Experience section with bullets */}
      <div className="space-y-2.5">
        <div className="h-3 w-1/4 bg-slate-200 rounded" />
        <div className="flex items-center justify-between">
          <div className="h-2.5 w-1/3 bg-slate-100 rounded" />
          <div className="h-2.5 w-16 bg-slate-100 rounded" />
        </div>
        {['w-full', 'w-11/12', 'w-4/5'].map((w) => (
          <div key={w} className="flex items-start gap-2">
            <div className="h-1.5 w-1.5 rounded-full bg-slate-100 mt-1 shrink-0" />
            <div className={cn('h-2.5 bg-slate-100 rounded', w)} />
          </div>
        ))}
      </div>

      {/* Skills section */}
      <div className="space-y-2">
        <div className="h-3 w-1/4 bg-slate-200 rounded" />
        <div className="flex flex-wrap gap-1.5">
          {['w-16', 'w-20', 'w-14', 'w-24', 'w-12'].map((w) => (
            <div key={w} className={cn('h-4 bg-slate-100 rounded-full', w)} />
          ))}
        </div>
      </div>
    </div>
  )
}
