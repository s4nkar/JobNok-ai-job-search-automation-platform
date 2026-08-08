import { Baloo_Chettan_2 } from 'next/font/google'
import { FileSearch, PenLine, MessageSquare, DollarSign, Briefcase, Mail, Linkedin, Compass, Radar } from 'lucide-react'

// Malayalam-script font for the wordmark ("നോക്ക്" = "look/search" in
// Malayalam — the second half of "JobNok"). Also covers Latin so "Job"
// renders in the same typeface rather than falling back to the site font.
const baloo = Baloo_Chettan_2({ subsets: ['latin', 'malayalam'], weight: ['600', '700'] })

// Same icon + accent-color pairing documented for the sidebar/dashboard —
// keeps the collage's color language consistent with the rest of the app.
// Positioned in a loose ring around the center; each carries its tool name
// so the icon alone doesn't have to be self-explanatory.
const collage = [
  { icon: Radar, label: 'Startup Scout', color: 'cyan', top: '0%', left: '4%' },
  { icon: FileSearch, label: 'Resume Tailor', color: 'violet', top: '0%', left: '54%' },
  { icon: PenLine, label: 'Cover Letter', color: 'pink', top: '20%', left: '84%' },
  { icon: Linkedin, label: 'LinkedIn Fill', color: 'blue', top: '44%', left: '0%' },
  { icon: Compass, label: 'Startup Hunt', color: 'orange', top: '46%', left: '88%' },
  { icon: MessageSquare, label: 'Interview Prep', color: 'teal', top: '76%', left: '2%' },
  { icon: DollarSign, label: 'Salary Research', color: 'emerald', top: '90%', left: '28%' },
  { icon: Briefcase, label: 'Tracker', color: 'indigo', top: '92%', left: '58%' },
  { icon: Mail, label: 'Bulk Email', color: 'amber', top: '74%', left: '86%' },
] as const

const badgeColors: Record<string, string> = {
  cyan: 'bg-cyan-500/15 text-cyan-300 border-cyan-400/20',
  violet: 'bg-violet-500/15 text-violet-300 border-violet-400/20',
  pink: 'bg-pink-500/15 text-pink-300 border-pink-400/20',
  blue: 'bg-blue-500/15 text-blue-300 border-blue-400/20',
  orange: 'bg-orange-500/15 text-orange-300 border-orange-400/20',
  teal: 'bg-teal-500/15 text-teal-300 border-teal-400/20',
  emerald: 'bg-emerald-500/15 text-emerald-300 border-emerald-400/20',
  indigo: 'bg-indigo-500/15 text-indigo-300 border-indigo-400/20',
  amber: 'bg-amber-500/15 text-amber-300 border-amber-400/20',
}

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex">
      {/* Form column */}
      <div className="flex-1 flex items-center justify-center p-4 sm:p-8 bg-background">
        <div className="w-full max-w-md">
          {/* Mobile-only brand header — the branded panel takes over from lg: up.
              Full lockup image (icon + wordmark + tagline) — the logo's own
              text is dark-on-transparent, so it only works on this light bg. */}
          <div className="flex lg:hidden items-center justify-center mb-8">
            <img src="/logo.png" alt="JobNok" className="h-10 w-auto" />
          </div>
          {children}
        </div>
      </div>

      {/* Branded panel — same dark surface as the sidebar, with a loose
          collage of every tool's real icon/color scattered around the
          wordmark instead of a plain stacked list. */}
      <div
        className="hidden lg:flex flex-1 relative items-center justify-center p-12 border-l"
        style={{ backgroundColor: 'hsl(var(--sidebar-bg))', borderColor: 'hsl(var(--sidebar-border))' }}
      >
        <div className="relative w-full max-w-[460px] aspect-square">
          {collage.map(({ icon: Icon, label, color, top, left }, i) => (
            <div
              key={i}
              className="absolute flex flex-col items-center gap-1.5 w-20 -translate-x-1/2"
              style={{ top, left }}
            >
              <div className={`w-11 h-11 rounded-2xl border flex items-center justify-center ${badgeColors[color]}`}>
                <Icon className="h-5 w-5" />
              </div>
              <span className="text-[10px] font-medium text-slate-400 text-center leading-tight">{label}</span>
            </div>
          ))}

          {/* Center content */}
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-10">
            <img src="/brand-icon.png" alt="" className="w-12 h-12 mb-1" />
            <h1 className={`${baloo.className} text-3xl font-bold text-white tracking-tight mb-1`}>Job നോക്ക്</h1>
            {/* <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-widest mb-4">JobNok</p> */}
            <p className="text-slate-400 text-sm leading-relaxed max-w-[260px]">
              Every tool for your job search resumes, cover letters, interviews, tracking, and outreach in one place.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
