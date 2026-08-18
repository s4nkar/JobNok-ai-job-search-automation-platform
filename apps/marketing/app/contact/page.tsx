import type { Metadata } from 'next'
import { Mail } from 'lucide-react'
import { InfoPageLayout } from '@/components/InfoPageLayout'

export const metadata: Metadata = { title: 'Contact | JobNok' }

// Placeholder address — swap for the real support inbox before launch.
const CONTACT_EMAIL = 'hello@jobnok.com'

export default function ContactPage() {
  return (
    <InfoPageLayout title="Contact">
      <p>
        Questions, bug reports, or feedback on any of the tools — reach out and we&apos;ll get back to you.
      </p>
      <a
        href={`mailto:${CONTACT_EMAIL}`}
        className="inline-flex items-center gap-2 h-10 px-4 rounded-lg border border-slate-200 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
      >
        <Mail className="h-4 w-4" />
        {CONTACT_EMAIL}
      </a>
    </InfoPageLayout>
  )
}
