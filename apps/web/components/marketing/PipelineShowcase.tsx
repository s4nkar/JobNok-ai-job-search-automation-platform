const steps = [
  { label: 'Chunk', detail: 'Resume and job description split into bullets, skills, summary' },
  { label: 'Embed', detail: 'Each chunk turned into a vector, cached per resume' },
  { label: 'Match', detail: 'Similarity matrix maps requirements to evidence' },
  { label: 'Score', detail: 'Keyword overlap + embedding similarity, per category' },
  { label: 'LLM prose', detail: 'One focused call, just for headline, summary, and rewrites', accent: true },
]

export function PipelineShowcase() {
  return (
    <section id="pipeline" className="bg-slate-50 border-y border-slate-100">
      <div className="container py-20 sm:py-28 grid lg:grid-cols-2 gap-14 items-center">
        <div>
          <p className="text-[11px] font-semibold text-indigo-600 uppercase tracking-widest mb-3">Resume Tailor, under the hood</p>
          <h2 className="text-3xl sm:text-4xl font-bold text-slate-900 tracking-tight mb-5">
            Your match score isn&apos;t an AI&apos;s opinion.
          </h2>
          <p className="text-slate-600 text-base leading-relaxed mb-4">
            Resume and job description are chunked and embedded, then matched and scored with
            a similarity matrix and keyword overlap — plain numpy, deterministic, same inputs
            always produce the same score. The LLM is called exactly once, only for prose:
            the headline, the tailored summary, and bullet rewrites, constrained to the evidence
            that was already matched. It can&apos;t invent a qualification you don&apos;t have.
          </p>
          <p className="text-slate-600 text-base leading-relaxed">
            That split makes it about 4× cheaper and faster than a single-prompt AI resume tool,
            and if the embedding provider is ever down, matching falls back to keyword-only
            instead of failing silently — you still get a result, flagged as reduced-accuracy.
          </p>
        </div>

        <div className="flex flex-col gap-2.5">
          {steps.map((step) => (
            <div
              key={step.label}
              className={`flex items-center gap-4 rounded-xl border p-4 bg-white ${
                step.accent ? 'border-indigo-200 ring-1 ring-indigo-100' : 'border-slate-100'
              }`}
            >
              <span
                className={`text-sm font-semibold shrink-0 w-24 ${
                  step.accent ? 'text-indigo-600' : 'text-slate-700'
                }`}
              >
                {step.label}
              </span>
              <span className="text-sm text-slate-500">{step.detail}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
