"""One-off, idempotent admin promotion.

Creating the actual Clerk account is a manual step done in the Clerk
dashboard (or the app's own sign-up flow) - that's Clerk's job, not this
script's. This only handles the one thing Clerk's dashboard has no concept
of: setting profiles.role='admin' in our own database, once that person has
signed in at least once (which is what provisions their `profiles` row -
normally via the Clerk webhook, see app/modules/auth/service.py's
upsert_from_webhook, but see the ADMIN_CLERK_USER_ID note below for why
that doesn't always apply).

Run deliberately, manually - never on every app boot:

    docker compose exec api python -m app.scripts.promote_admin

Set ADMIN_EMAIL, or ADMIN_CLERK_USER_ID, or both (clerk_user_id wins if
both are set - it's the more reliable of the two, see below).

Why both exist: Clerk's webhook can't reach `localhost` from Clerk's own
servers, so in local dev the ONLY thing that ever provisions a `profiles`
row is the synchronous fallback in get_current_user_id/
resolve_or_create_profile, which has no real email to work with yet - it
writes a placeholder `{clerk_user_id}@unknown.local`. An ADMIN_EMAIL lookup
can never match that placeholder, so local dev needs ADMIN_CLERK_USER_ID
instead (find it in the Clerk dashboard's Users list). In a real deployment
with a publicly reachable webhook endpoint, the row carries the real email
and ADMIN_EMAIL works fine on its own.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.modules.profile.models import Profile

_PLACEHOLDER_EMAIL_SUFFIX = "@unknown.local"


async def promote(*, email: str | None, clerk_user_id: str | None) -> str:
    async with AsyncSessionLocal() as db:
        if clerk_user_id:
            identifier = clerk_user_id
            profile = (
                await db.execute(select(Profile).where(Profile.clerk_user_id == clerk_user_id))
            ).scalar_one_or_none()
        else:
            identifier = email
            profile = (
                await db.execute(select(Profile).where(Profile.email == email))
            ).scalar_one_or_none()

        if profile is None:
            hint = ""
            if email and not clerk_user_id:
                placeholders = (
                    await db.execute(
                        select(Profile).where(Profile.email.like(f"%{_PLACEHOLDER_EMAIL_SUFFIX}"))
                    )
                ).scalars().all()
                if placeholders:
                    ids = ", ".join(p.clerk_user_id for p in placeholders)
                    hint = (
                        f"\nNote: found {len(placeholders)} profile(s) with a placeholder email "
                        f"({_PLACEHOLDER_EMAIL_SUFFIX}) - likely local dev, where Clerk's webhook "
                        "can't reach localhost. If one of these is you, set ADMIN_CLERK_USER_ID "
                        f"instead (find it in the Clerk dashboard's Users list): {ids}"
                    )
            return (
                f"No profiles row found for {identifier!r} yet - sign in at least once first so "
                f"the profile gets provisioned, then re-run this.{hint}"
            )

        if profile.role == "admin":
            return f"{identifier} is already an admin - nothing to do."

        previous_role = profile.role
        profile.role = "admin"
        await db.commit()
        return f"Promoted {identifier} to admin (was role={previous_role!r})."


async def main() -> None:
    email = settings.admin_email.strip() or None
    clerk_user_id = settings.admin_clerk_user_id.strip() or None

    if not email and not clerk_user_id:
        print("Missing required env var: set ADMIN_EMAIL or ADMIN_CLERK_USER_ID", file=sys.stderr)
        raise SystemExit(1)

    print(await promote(email=email, clerk_user_id=clerk_user_id))


if __name__ == "__main__":
    asyncio.run(main())
