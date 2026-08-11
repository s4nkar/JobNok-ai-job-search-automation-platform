import { config } from '@/lib/config'

export function FinalCta() {
  return (
    <section className="relative overflow-hidden">
      <div
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[480px] h-[480px] rounded-full gradient-brand opacity-[0.10] blur-[110px] pointer-events-none"
        aria-hidden
      />

      <div className="container relative py-20 sm:py-28 flex flex-col items-center text-center">
        <h2 className="text-3xl sm:text-4xl font-bold text-slate-900 tracking-tight mb-4 max-w-xl">
          No subscription, no trial countdown.
        </h2>
        <p className="text-slate-500 text-base leading-relaxed mb-9 max-w-md">
          Start with whichever tool you need right now. The rest are there when you need them too.
        </p>

        <a
          href={`${config.appUrl}/signup`}
          className="inline-flex items-center justify-center h-12 px-8 rounded-full text-sm font-semibold gradient-brand text-white shadow-brand hover:opacity-90 transition-opacity mb-4"
        >
          Get started free
        </a>

        <a href={`${config.appUrl}/login`} className="text-sm text-slate-500 hover:text-slate-800 transition-colors">
          Already have an account? Log in
        </a>
      </div>
    </section>
  )
}
