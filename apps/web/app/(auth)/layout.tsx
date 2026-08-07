import { Fraunces, Manrope } from 'next/font/google'
import { Zap } from 'lucide-react'

const fraunces = Fraunces({
  subsets: ['latin'],
  weight: ['500', '600'],
  style: ['normal', 'italic'],
  variable: '--font-display',
})
const manrope = Manrope({ subsets: ['latin'], variable: '--font-body' })

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div
      className={`${fraunces.variable} ${manrope.variable} min-h-screen flex items-center justify-center p-4 relative overflow-hidden bg-[#08090d]`}
      style={{ fontFamily: 'var(--font-body)' }}
    >
      {/* Fine grid, faded toward the edges */}
      <div className="absolute inset-0 opacity-[0.05] bg-grid-fade pointer-events-none" />
      {/* Single asymmetric glow — not a symmetric blob cluster */}
      <div className="absolute -top-24 right-[15%] w-[560px] h-[560px] rounded-full bg-indigo-600/25 blur-[130px] pointer-events-none" />
      {/* Subtle grain for texture/depth */}
      <div className="absolute inset-0 opacity-[0.03] bg-grain mix-blend-overlay pointer-events-none" />

      <div className="w-full max-w-md relative z-10">
        {/* Brand header */}
        <div className="text-center mb-9">
          <div className="inline-flex items-center justify-center w-11 h-11 rounded-2xl gradient-brand shadow-brand mb-5">
            <Zap className="h-5 w-5 text-white" />
          </div>
          <h1
            className="text-[34px] leading-none text-white tracking-tight"
            style={{ fontFamily: 'var(--font-display)', fontWeight: 600 }}
          >
            QuickJob
          </h1>
          <p className="text-slate-500 mt-3 text-[11px] font-medium uppercase tracking-[0.16em]">
            Job Search, Automated
          </p>
        </div>
        {children}
      </div>
    </div>
  )
}
