import { ShieldAlert, TriangleAlert } from 'lucide-react'
import { ApiError } from '@/lib/api'

// Distinguishes "you're signed in but not an admin" (403 - a normal,
// expected state for this app, not a bug) from every other failure, since
// the two need very different messaging.
export function ApiErrorState({ error }: { error: unknown }) {
  const isForbidden = error instanceof ApiError && error.status === 403

  if (isForbidden) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-24 text-center">
        <ShieldAlert className="h-8 w-8 text-muted-foreground" />
        <div>
          <p className="font-medium">Access denied</p>
          <p className="text-sm text-muted-foreground">
            Your account isn&apos;t marked as an admin. Ask someone with access to update your profile role.
          </p>
        </div>
      </div>
    )
  }

  const message = error instanceof Error ? error.message : 'Something went wrong loading this page.'
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-24 text-center">
      <TriangleAlert className="h-8 w-8 text-muted-foreground" />
      <div>
        <p className="font-medium">Couldn&apos;t load this page</p>
        <p className="text-sm text-muted-foreground">{message}</p>
      </div>
    </div>
  )
}
