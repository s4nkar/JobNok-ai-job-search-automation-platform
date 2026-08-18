const stats = [
  { value: '4×', label: 'Cheaper and faster than a single-prompt AI resume tool' },
  { value: '10', label: 'Tools in one free account, no separate subscriptions' },
  { value: '0', label: 'Invented qualifications. Matching is deterministic, not AI guesswork' },
  { value: 'Free', label: 'No credit card, no trial countdown' },
]

export function ProofStrip() {
  return (
    <section className="border-y border-slate-100 bg-white mt-8">
      <div className="container py-12 grid grid-cols-2 lg:grid-cols-4 gap-8">
        {stats.map((stat) => (
          <div key={stat.label}>
            <p className="text-3xl font-bold text-slate-900 tracking-tight mb-1.5">{stat.value}</p>
            <p className="text-sm text-slate-500 leading-snug">{stat.label}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
