export function InfoPageLayout({
  title,
  lastUpdated,
  children,
}: {
  title: string
  lastUpdated?: string
  children: React.ReactNode
}) {
  return (
    <div className="container max-w-3xl py-16 sm:py-20">
      <div className="rounded-2xl border border-slate-100 bg-white shadow-card p-8 sm:p-10">
        <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight mb-1">{title}</h1>
        {lastUpdated && <p className="text-xs text-slate-400 mb-8">Last updated {lastUpdated}</p>}
        {!lastUpdated && <div className="mb-8" />}
        <div className="space-y-6 text-sm text-slate-600 leading-relaxed">{children}</div>
      </div>
    </div>
  )
}

export function InfoSection({ heading, children }: { heading: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-base font-semibold text-slate-900 mb-2">{heading}</h2>
      <p>{children}</p>
    </section>
  )
}
