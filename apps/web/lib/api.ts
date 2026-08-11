/**
 * Authenticated fetch wrapper.
 * Attaches the Clerk session token to every /api/* request so FastAPI can
 * validate the user via get_current_user_id(). Falls back to plain fetch for
 * non-API paths or when no session exists.
 *
 * Uses the global `window.Clerk` singleton (attached by <ClerkProvider>)
 * rather than the useAuth() hook, since apiFetch is called from plain async
 * functions all over the app, not just component render bodies — the hook
 * can only be called at a component's top level, but window.Clerk works
 * anywhere in the browser once Clerk has loaded.
 */

declare global {
  interface Window {
    Clerk?: { session?: { getToken: () => Promise<string | null> } }
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
 * GET + parse-JSON in one call, throwing on a non-2xx response. Built for
 * react-query's queryFn contract (it needs a rejected promise to enter the
 * query's error state — apiFetch alone only returns a Response, it never
 * rejects on a 4xx/5xx).
 */
export async function apiGet<T>(input: string): Promise<T> {
  const res = await apiFetch(input)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed: ${res.status}`)
  }
  return res.json()
}
