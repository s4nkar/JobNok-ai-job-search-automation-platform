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
    <div className="w-full">
      <div className="rounded-lg border bg-card p-6 shadow-sm">
        <div className="space-y-2">
          <div className="h-6 w-40 animate-pulse rounded bg-muted" />
          <div className="h-4 w-64 animate-pulse rounded bg-muted" />
        </div>
        <div className="mt-6 space-y-4">
          <div className="h-10 w-full animate-pulse rounded bg-muted" />
          <div className="h-10 w-full animate-pulse rounded bg-muted" />
          <div className="h-10 w-full animate-pulse rounded bg-muted" />
        </div>
      </div>
    </div>
  )
}