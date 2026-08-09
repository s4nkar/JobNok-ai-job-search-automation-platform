import { auth } from '@clerk/nextjs/server'
import { redirect } from 'next/navigation'
import { Hero } from '@/components/marketing/Hero'
import { ProofStrip } from '@/components/marketing/ProofStrip'
import { BentoGrid } from '@/components/marketing/BentoGrid'
import { PipelineShowcase } from '@/components/marketing/PipelineShowcase'
import { FinalCta } from '@/components/marketing/FinalCta'

export default async function HomePage() {
  const { userId } = await auth()
  if (userId) redirect('/templates')

  return (
    <>
      <Hero />
      <ProofStrip />
      <BentoGrid />
      <PipelineShowcase />
      <FinalCta />
    </>
  )
}
