import Link from 'next/link'
import { Baloo_Chettan_2 } from 'next/font/google'
import { FlowDiagram } from './FlowDiagram'

// Same Malayalam-script wordmark treatment as the auth panel — "നോക്ക്" means
// "look/search" in Malayalam, the second half of "JobNok".
const baloo = Baloo_Chettan_2({ subsets: ['latin', 'malayalam'], weight: ['600', '700'] })

export function Hero() {
  return (
    <section className="relative overflow-hidden pt-10 pb-28 min-h-[760px] sm:min-h-[820px]">
      {/* Background Orbs */}
      <div className="absolute -top-32 -left-40 w-[550px] h-[550px] rounded-full bg-indigo-500/10 blur-[130px] pointer-events-none" aria-hidden />
      <div className="absolute -top-20 right-0 w-[500px] h-[500px] rounded-full bg-pink-500/10 blur-[120px] pointer-events-none" aria-hidden />

      {/* Full-bleed Flow Canvas overlay */}
      <div className="absolute inset-0 top-20 w-full h-full z-10">
        <div className="container relative mx-auto h-full max-w-7xl">
          <FlowDiagram />
        </div>
      </div>

      {/* Centered Hero Copy in foreground */}
      <div className="container relative mx-auto px-4 sm:px-6 lg:px-8 max-w-7xl z-20 pointer-events-none">
        <div className="max-w-2xl mx-auto text-center pt-2 pointer-events-auto">
          <span className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-slate-200 bg-white/95 text-xs font-medium text-slate-600 mb-6 shadow-xs backdrop-blur-xs">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            Free · No credit card · 10 tools, one account
          </span>

          <p className={`${baloo.className} text-lg font-semibold text-indigo-600 mb-2`}>
            Job <span className="text-gradient-brand">നോക്ക്</span>
          </p>

          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-slate-900 mb-5 leading-[1.12]">
            Search smarter, apply faster, follow up on time.
          </h1>

          <p className="text-slate-600 text-base sm:text-lg leading-relaxed mb-8 max-w-xl mx-auto">
            Tailor your resume against real job descriptions with a deterministic match score,
            auto-fill applications, draft cold DMs, research salary benchmarks, and track
            every startup lead and job opportunity in one unified platform.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link
              href="/signup"
              className="inline-flex items-center justify-center h-12 px-7 rounded-full text-sm font-semibold gradient-brand text-white shadow-brand hover:opacity-95 transition-all transform active:scale-95"
            >
              Get started free
            </Link>
            <Link
              href="#tools"
              className="inline-flex items-center justify-center h-12 px-7 rounded-full text-sm font-semibold border border-slate-200 text-slate-700 bg-white hover:bg-slate-50 transition-colors shadow-xs"
            >
              See the tools
            </Link>
          </div>
        </div>
      </div>
    </section>
  )
}
