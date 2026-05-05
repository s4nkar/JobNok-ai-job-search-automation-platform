"""Supabase admin client (service role) for backend operations.

The service role key bypasses RLS — only use for backend-initiated writes
(e.g., creating email_recipients, updating campaign status from the Celery worker).
JWT validation is done separately via verify_jwt().
"""

import jwt
from supabase import create_client, Client
from fastapi import HTTPException, Request
from lib.config import settings

# Module-level singleton — one HTTP session shared across all requests.
# supabase-py is synchronous; callers must use asyncio.to_thread() to avoid
# blocking the uvicorn event loop.
_supabase_client: Client | None = None


def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _supabase_client


def verify_jwt(token: str) -> dict:
    """Validate a Supabase JWT and return the decoded payload.

    Raises HTTPException(401) if invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={"verify_exp": True},
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


def get_user_id(request: Request) -> str:
    """Extract and validate the user_id from the Bearer JWT in the request."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = auth.removeprefix("Bearer ").strip()
    payload = verify_jwt(token)

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="No user_id in token")

    return user_id
