"""Shared profile logic used by the profile module and by other modules that
need to guarantee a profiles row exists before writing FK-dependent rows."""

import asyncio
from fastapi import Request

from app.core.security import verify_jwt


async def ensure_profile_exists(sb, user_id: str, request: Request) -> None:
    """Upsert a profiles row so FK constraints don't fail for users whose profile trigger missed."""
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    claims = verify_jwt(token)
    email = claims.get("email") or f"{user_id}@unknown.local"
    try:
        await asyncio.to_thread(
            lambda: sb.table("profiles")
            .upsert({"id": user_id, "email": email}, on_conflict="id")
            .execute()
        )
    except Exception:
        pass
