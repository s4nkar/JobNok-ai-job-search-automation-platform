import { Suspense } from 'react'
import LoginFormClient from './LoginFormClient'

export default function LoginPage() {
  return (
    <Suspense fallback={<LoginFallback />}>
      <LoginFormClient />
    </Suspense>
  )
}

function LoginFallback() {
  return (
    <div className="rounded-2xl p-8 shadow-2xl bg-white/[0.04] border border-white/10 backdrop-blur-xl">
      <div className="space-y-2">
        <div className="h-5 w-32 animate-pulse rounded-full bg-white/10" />
        <div className="h-3.5 w-52 animate-pulse rounded-full bg-white/5" />
      </div>
      <div className="mt-6 space-y-3">
        <div className="h-11 w-full animate-pulse rounded-xl bg-white/5" />
        <div className="h-11 w-full animate-pulse rounded-xl bg-white/5" />
        <div className="h-11 w-full animate-pulse rounded-xl bg-white/5" />
      </div>
    </div>
  )
}