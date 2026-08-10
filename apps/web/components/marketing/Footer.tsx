import Link from 'next/link'
import { tools } from '@/lib/tools'

export function Footer() {
  return (
    <footer className="border-t border-slate-100 bg-white">
      <div className="container py-14 grid grid-cols-2 md:grid-cols-4 gap-10">
        <div className="col-span-2 md:col-span-1">
          <img src="/logo.png" alt="JobNok" className="h-6 w-auto mb-3" />
          <p className="text-sm text-slate-500 leading-relaxed max-w-[240px]">
            Every tool for your job search. Resumes, cover letters, interviews, tracking, and outreach in one place.
          </p>
        </div>

        <div>
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest mb-3">Tools</p>
          <ul className="space-y-2">
            {tools.slice(0, 6).map((tool) => (
              <li key={tool.slug}>
                <Link href={tool.href} className="text-sm text-slate-500 hover:text-slate-900 transition-colors">
                  {tool.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest mb-3">More tools</p>
          <ul className="space-y-2">
            {tools.slice(6).map((tool) => (
              <li key={tool.slug}>
                <Link href={tool.href} className="text-sm text-slate-500 hover:text-slate-900 transition-colors">
                  {tool.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest mb-3">Company</p>
          <ul className="space-y-2">
            <li><Link href="/contact" className="text-sm text-slate-500 hover:text-slate-900 transition-colors">Contact</Link></li>
            <li><Link href="/terms" className="text-sm text-slate-500 hover:text-slate-900 transition-colors">Terms of Service</Link></li>
            <li><Link href="/privacy" className="text-sm text-slate-500 hover:text-slate-900 transition-colors">Privacy Policy</Link></li>
          </ul>
        </div>
      </div>

      <div className="border-t border-slate-100">
        <div className="container py-5 text-xs text-slate-400">
          © {new Date().getFullYear()} JobNok. All rights reserved.
        </div>
      </div>
    </footer>
  )
}
