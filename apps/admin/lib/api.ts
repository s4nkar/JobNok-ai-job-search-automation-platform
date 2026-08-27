// Same window.Clerk pattern as apps/web's lib/api.ts - called from plain
// async functions (react-query queryFns), not just component render bodies,
// so this reads the token off window.Clerk directly rather than the
// useAuth() hook (which can only be called at a component's top level).

declare global {
  interface Window {
    Clerk?: { session?: { getToken: () => Promise<string | null> } }
  }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const token = await window.Clerk?.session?.getToken()

  const headers = new Headers(init.headers)
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  return fetch(input, { ...init, headers })
}

/**
 * GET + parse-JSON, throwing ApiError on a non-2xx response so callers
 * (and react-query's error state) can distinguish 403 (logged in, not an
 * admin - a normal, expected state for this app) from every other failure.
 */
export async function apiGet<T>(input: string): Promise<T> {
  const res = await apiFetch(input)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(res.status, body.detail || `Request failed: ${res.status}`)
  }
  return res.json()
}
