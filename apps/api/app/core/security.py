"""JWT verification for Clerk session tokens, and the request-scoped user
resolver every route depends on.

verify_jwt() is pure crypto/claims verification — no DB access, mirroring the
same shape this module had for Supabase. Turning a verified Clerk identity
into this app's internal user id is feature logic, not infra, so it lives in
app/modules/auth/service.py; get_current_user_id() below is thin orchestration
that delegates to it, kept here only because every route module imports this
one dependency (same reason app/core/database.py::get_db isn't a "module").
"""

from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError, PyJWKClientError
from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auth.service import resolve_or_create_profile

# JWKS client for Clerk's RS256 signing keys.
# Example: https://your-app.clerk.accounts.dev/.well-known/jwks.json
_jwks_client = PyJWKClient(settings.clerk_jwks_url)


def verify_jwt(token: str) -> dict[str, Any]:
    """Validate a Clerk session JWT and return the decoded payload.

    Clerk only signs asymmetrically (RS256) — no HS256 legacy path.
    Raises HTTPException(401) if invalid, expired, or issued for a different app.
    """
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg")

        if alg != "RS256":
            raise HTTPException(status_code=401, detail=f"Unsupported JWT algorithm: {alg}")

        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iss": True,
            },
        )

        # azp (authorized party) is Clerk's equivalent of an audience check —
        # confirms this token was issued for THIS app's origin, not some other
        # application on the same Clerk instance replaying a valid token here.
        if payload.get("azp") != settings.app_url:
            raise HTTPException(status_code=401, detail="Token issued for a different origin")

        return payload

    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except HTTPException:
        raise
    except (InvalidTokenError, PyJWKClientError) as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


async def get_current_user_id(request: Request, db: AsyncSession) -> str:
    """Extract and validate the Bearer JWT, then resolve it to this app's
    internal profiles.id (a UUID, not Clerk's own user id string).

    Provisioning normally happens via the Clerk webhook
    (app/modules/auth/routes.py) before this is ever called; the
    lookup-or-create in resolve_or_create_profile is a fallback for the rare
    case where a request lands before the webhook has processed.
    """
    auth = request.headers.get("Authorization", "")

    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = auth.removeprefix("Bearer ").strip()
    payload = verify_jwt(token)

    clerk_sub = payload.get("sub")
    if not clerk_sub:
        raise HTTPException(status_code=401, detail="No sub claim in token")

    profile = await resolve_or_create_profile(db, clerk_sub)
    return str(profile.id)
