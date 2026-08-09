import type { Metadata } from 'next'
import { InfoPageLayout, InfoSection } from '@/components/marketing/InfoPageLayout'

export const metadata: Metadata = { title: 'Privacy Policy | JobNok' }

export default function PrivacyPage() {
  return (
    <InfoPageLayout title="Privacy Policy">
      <p className="text-slate-500">
        Placeholder — JobNok&apos;s full Privacy Policy will be published here before general availability.
        The sections below outline what will be covered.
      </p>

      <InfoSection heading="Overview">
        Placeholder — what this policy covers and who it applies to.
      </InfoSection>
      <InfoSection heading="What We Collect">
        Placeholder — account details, resumes and job descriptions you provide, and basic usage data.
      </InfoSection>
      <InfoSection heading="How We Use It">
        Placeholder — running the tools you use (matching, tailoring, tracking) and improving reliability.
      </InfoSection>
      <InfoSection heading="Third-Party Services">
        Placeholder — JobNok relies on Clerk for authentication, and a small set of AI and embedding
        providers for prose generation and semantic matching. Details on data sharing with each will
        be listed here.
      </InfoSection>
      <InfoSection heading="Your Choices">
        Placeholder — how to access, export, or delete your data.
      </InfoSection>
      <InfoSection heading="Contact">
        Questions about this policy can be sent to the address on the{' '}
        <a href="/contact" className="text-indigo-600 hover:underline">Contact page</a>.
      </InfoSection>
    </InfoPageLayout>
  )
}
