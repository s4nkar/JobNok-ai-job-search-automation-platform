import type { Metadata } from 'next'
import { InfoPageLayout, InfoSection } from '@/components/marketing/InfoPageLayout'

export const metadata: Metadata = { title: 'Terms of Service | JobNok' }

export default function TermsPage() {
  return (
    <InfoPageLayout title="Terms of Service">
      <p className="text-slate-500">
        Placeholder — JobNok&apos;s full Terms of Service will be published here before general availability.
        The sections below outline what will be covered.
      </p>

      <InfoSection heading="Overview">
        Placeholder — a summary of what using JobNok means you agree to, and who these terms apply to.
      </InfoSection>
      <InfoSection heading="Acceptable Use">
        Placeholder — rules for how the tools (resume tailoring, LinkedIn auto-fill, bulk email, and the rest)
        may and may not be used.
      </InfoSection>
      <InfoSection heading="Your Account">
        Placeholder — your responsibilities around account security, and the conditions under which access
        can be suspended.
      </InfoSection>
      <InfoSection heading="Content You Provide">
        Placeholder — how resumes, job descriptions, and other content you upload are used, and what rights
        you retain over them.
      </InfoSection>
      <InfoSection heading="Changes to These Terms">
        Placeholder — how updates to these terms will be communicated before they take effect.
      </InfoSection>
      <InfoSection heading="Contact">
        Questions about these terms can be sent to the address on the{' '}
        <a href="/contact" className="text-indigo-600 hover:underline">Contact page</a>.
      </InfoSection>
    </InfoPageLayout>
  )
}
