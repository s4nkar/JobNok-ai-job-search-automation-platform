/**
 * Authenticated fetch wrapper.
 * Attaches the Supabase JWT to every /api/* request so FastAPI can
 * validate the user via get_user_id(). Falls back to plain fetch for
 * non-API paths or when no session exists.
 */
import { createClient } from '@/lib/supabase/client'

export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const supabase = createClient()
  const { data: { session } } = await supabase.auth.getSession()

  const headers = new Headers(init.headers)
  if (session?.access_token) {
    headers.set('Authorization', `Bearer ${session.access_token}`)
  }

  return fetch(input, { ...init, headers })
}
