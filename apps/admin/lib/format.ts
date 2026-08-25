// Small hand-rolled relative-time formatter - not worth a date library for
// one function in a basic internal tool. Handles both directions since it's
// used for both past timestamps (last_synced_at) and future ones
// (next_crawl_at).
export function formatRelativeTime(iso: string | null): string {
  if (!iso) return 'not set'
  const then = new Date(iso).getTime()
  const diffMs = Date.now() - then
  const future = diffMs < 0
  const diffSeconds = Math.round(Math.abs(diffMs) / 1000)

  let magnitude: string
  if (diffSeconds < 60) {
    magnitude = 'less than a minute'
  } else {
    const diffMinutes = Math.round(diffSeconds / 60)
    if (diffMinutes < 60) {
      magnitude = `${diffMinutes}m`
    } else {
      const diffHours = Math.round(diffMinutes / 60)
      if (diffHours < 24) {
        magnitude = `${diffHours}h`
      } else {
        magnitude = `${Math.round(diffHours / 24)}d`
      }
    }
  }

  return future ? `in ${magnitude}` : `${magnitude} ago`
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return 'Not set'
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}
