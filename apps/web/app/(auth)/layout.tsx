import { Baloo_Chettan_2 } from 'next/font/google'
import { tools, toolBadgeColors } from '@/lib/tools'

// Malayalam-script font for the wordmark ("നോക്ക്" = "look/search" in
// Malayalam — the second half of "JobNok"). Also covers Latin so "Job"
// renders in the same typeface rather than falling back to the site font.
const baloo = Baloo_Chettan_2({ subsets: ['latin', 'malayalam'], weight: ['600', '700'] })

// Every real tool, evenly ringed around the center wordmark (36° apart) so
// none of them crowd the text — same icon/color pairing used on the
// homepage's bento grid and footer.
const positions: Record<string, { top: string; left: string }> = {
  'resume-tailor': { top: '4%', left: '50%' },
  'templates': { top: '13%', left: '77%' },
  'linkedin-fill': { top: '36%', left: '90%' },
  'cover-letter': { top: '64%', left: '90%' },
  'interview-prep': { top: '87%', left: '77%' },
  'tracker': { top: '92%', left: '50%' },
  'startup-scout': { top: '87%', left: '23%' },
  'salary': { top: '64%', left: '6%' },
  'startup-hunt': { top: '36%', left: '6%' },
  'bulk-email': { top: '13%', left: '23%' },
}

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex">
      {/* Form column */}
      <div className="flex-1 flex items-center justify-center p-4 sm:p-8 bg-background">
        <div className="w-full max-w-md">
          {/* Mobile-only brand header — the branded panel takes over from lg: up. */}
          <div className="flex lg:hidden items-center justify-center mb-8">
            <img src="/logo.png" alt="JobNok" className="h-10 w-auto" />
          </div>
          {children}
        </div>
      </div>

      {/* Branded panel — light, with the same soft gradient-orb accents as
          the homepage hero, and a ring of every tool's real icon/color
          scattered around the wordmark instead of a plain stacked list. */}
      <div className="hidden lg:flex flex-1 relative items-center justify-center p-12 border-l border-slate-100 bg-slate-50 overflow-hidden">
        <div className="absolute -top-32 -left-24 w-[420px] h-[420px] rounded-full gradient-brand opacity-[0.12] blur-[110px] pointer-events-none" aria-hidden />
        <div className="absolute -bottom-32 -right-24 w-[380px] h-[380px] rounded-full bg-pink-400 opacity-[0.10] blur-[100px] pointer-events-none" aria-hidden />

        <div className="relative w-full max-w-[460px] aspect-square">
          {tools.map((tool) => {
            const Icon = tool.icon
            const pos = positions[tool.slug]
            if (!pos) return null
            return (
              <div
                key={tool.slug}
                className="absolute flex flex-col items-center gap-1.5 w-20 -translate-x-1/2"
                style={pos}
              >
                <div className={`w-11 h-11 rounded-2xl border flex items-center justify-center ${toolBadgeColors[tool.color]}`}>
                  <Icon className="h-5 w-5" />
                </div>
                <span className="text-[10px] font-medium text-slate-500 text-center leading-tight">{tool.label}</span>
              </div>
            )
          })}

          {/* Center content */}
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-10">
            <img src="/brand-icon.png" alt="" className="w-12 h-12 mb-1" />
            <h1 className={`${baloo.className} text-3xl font-bold text-slate-900 tracking-tight mb-1`}>
              Job <span className="text-gradient-brand">നോക്ക്</span>
            </h1>
            <p className="text-slate-500 text-sm leading-relaxed max-w-[260px]">
              Every tool for your job search resumes, cover letters, interviews, tracking, and outreach in one place.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
