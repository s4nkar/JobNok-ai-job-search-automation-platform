"""Supabase admin client (service role) — TRANSITIONAL.

The service role key bypasses RLS — only use for backend-initiated writes.
This module exists only until every feature module has migrated its queries
to SQLAlchemy (see app/core/database.py); it is deleted once that migration
completes. JWT verification does not depend on this client — see
app/core/security.py.
"""

from supabase import create_client, Client
from app.core.config import settings


# Module-level singleton — one HTTP session shared across all requests.
# supabase-py is synchronous; callers must use asyncio.to_thread() to avoid
# blocking the uvicorn event loop.
_supabase_client: Client | None = None


def get_supabase() -> Client:
    global _supabase_client

    if _supabase_client is None:
        _supabase_client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
        # supabase-py 2.x passes the key as apikey but not as Authorization Bearer.
        # Without this, PostgREST falls back to the anon role which blocks some tables.
        _supabase_client.postgrest.auth(settings.supabase_service_role_key)

    return _supabase_client
