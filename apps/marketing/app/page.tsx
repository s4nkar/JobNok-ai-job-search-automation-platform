import { Hero } from '@/components/Hero'
import { ProofStrip } from '@/components/ProofStrip'
import { BentoGrid } from '@/components/BentoGrid'
import { PipelineShowcase } from '@/components/PipelineShowcase'
import { FinalCta } from '@/components/FinalCta'

export default function HomePage() {
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
