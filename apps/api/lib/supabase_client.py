"""Supabase admin client (service role) for backend operations.

The service role key bypasses RLS — only use for backend-initiated writes
(e.g., creating email_recipients, updating campaign status from the Celery worker).

User JWT validation supports both:
- HS256 legacy Supabase JWT secret verification
- RS256 / ES256 Supabase signing-key verification via JWKS
"""

from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError, PyJWKClientError
from supabase import create_client, Client
from fastapi import HTTPException, Request
from lib.config import settings


# Module-level singleton — one HTTP session shared across all requests.
# supabase-py is synchronous; callers must use asyncio.to_thread() to avoid
# blocking the uvicorn event loop.
_supabase_client: Client | None = None


# JWKS client for newer Supabase asymmetric signing keys.
# Example:
# https://your-project.supabase.co/auth/v1/.well-known/jwks.json
_supabase_url = settings.supabase_url.rstrip("/")
_supabase_issuer = f"{_supabase_url}/auth/v1"
_supabase_jwks_url = f"{_supabase_url}/auth/v1/.well-known/jwks.json"
_jwks_client = PyJWKClient(_supabase_jwks_url)


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


def verify_jwt(token: str) -> dict[str, Any]:
    """Validate a Supabase JWT and return the decoded payload.

    Supports:
    - HS256 tokens using SUPABASE_JWT_SECRET
    - RS256 / ES256 tokens using Supabase JWKS

    Raises HTTPException(401) if invalid or expired.
    """
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg")

        if alg in {"RS256", "ES256"}:
            signing_key = _jwks_client.get_signing_key_from_jwt(token)

            return jwt.decode(
                token,
                signing_key.key,
                algorithms=[alg],
                issuer=_supabase_issuer,
                audience="authenticated",
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )

        if alg == "HS256":
            return jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                issuer=_supabase_issuer,
                audience="authenticated",
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )

        raise HTTPException(
            status_code=401,
            detail=f"Unsupported JWT algorithm: {alg}",
        )

    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except HTTPException:
        raise
    except (InvalidTokenError, PyJWKClientError) as e:
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