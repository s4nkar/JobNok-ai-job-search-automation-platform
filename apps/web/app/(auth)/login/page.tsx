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
    <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-8">
      <div className="space-y-2">
        <div className="h-5 w-32 animate-pulse rounded-full bg-slate-100" />
        <div className="h-3.5 w-52 animate-pulse rounded-full bg-slate-100" />
      </div>
      <div className="mt-6 space-y-3">
        <div className="h-9 w-full animate-pulse rounded-xl bg-slate-100" />
        <div className="h-9 w-full animate-pulse rounded-xl bg-slate-100" />
        <div className="h-9 w-full animate-pulse rounded-xl bg-slate-100" />
      </div>
    </div>
  )
}