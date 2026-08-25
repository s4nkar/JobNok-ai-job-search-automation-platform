"""Identity provisioning — turns a verified Clerk identity into this app's
internal `profiles` row. JWT verification itself lives in core/security.py;
this module owns what happens once we know who the caller is.
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.profile.models import Profile


async def resolve_or_create_profile(db: AsyncSession, clerk_user_id: str) -> Profile:
    """Look up profiles by clerk_user_id, creating a minimal row if missing.

    Normally a no-op lookup — the Clerk webhook (routes.py, user.created)
    provisions the row before any API request arrives. This is a fallback for
    the rare race where a request lands first. Clerk's default session claims
    don't include email, so the placeholder here gets corrected once the
    webhook processes (upsert_from_webhook overwrites it).
    """
    row = (
        await db.execute(select(Profile).where(Profile.clerk_user_id == clerk_user_id))
    ).scalar_one_or_none()
    if row is not None:
        return row

    stmt = (
        pg_insert(Profile)
        .values(clerk_user_id=clerk_user_id, email=f"{clerk_user_id}@unknown.local")
        .on_conflict_do_nothing(index_elements=["clerk_user_id"])
        .returning(Profile)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    await db.flush()
    if row is None:
        # Lost a concurrent-insert race — the other request's row exists now.
        row = (
            await db.execute(select(Profile).where(Profile.clerk_user_id == clerk_user_id))
        ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=500, detail="Could not resolve or create profile")
    return row


async def upsert_from_webhook(
    db: AsyncSession, clerk_user_id: str, email: str, full_name: str | None
) -> Profile:
    """Create or refresh a profile from a Clerk user.created/user.updated webhook."""
    row = (
        await db.execute(select(Profile).where(Profile.clerk_user_id == clerk_user_id))
    ).scalar_one_or_none()
    if row is not None:
        row.email = email
        row.full_name = full_name
        await db.flush()
        return row

    stmt = (
        pg_insert(Profile)
        .values(clerk_user_id=clerk_user_id, email=email, full_name=full_name)
        .on_conflict_do_update(
            index_elements=["clerk_user_id"], set_={"email": email, "full_name": full_name}
        )
        .returning(Profile)
    )
    row = (await db.execute(stmt)).scalar_one()
    await db.flush()
    return row


async def delete_by_clerk_id(db: AsyncSession, clerk_user_id: str) -> None:
    """Cascade-delete a profile (and every FK'd row) on a user.deleted webhook."""
    row = (
        await db.execute(select(Profile).where(Profile.clerk_user_id == clerk_user_id))
    ).scalar_one_or_none()
    if row is not None:
        await db.delete(row)
        await db.flush()


def require_role(role: str):
    """FastAPI dependency factory — gate a route to profiles.role == role.

    Usage: @router.patch(..., dependencies=[Depends(require_role("admin"))])
    """

    async def _check(request: Request, db: AsyncSession = Depends(get_db)) -> str:
        # Deferred import: core.security imports resolve_or_create_profile from
        # this module, so importing get_current_user_id at module load time
        # here would be circular. By request time both modules are fully loaded.
        from app.core.security import get_current_user_id

        user_id = await get_current_user_id(request, db)
        profile = (
            await db.execute(select(Profile).where(Profile.id == user_id))
        ).scalar_one_or_none()
        if profile is None or profile.role != role:
            # get_current_user_id may have just created this profile row
            # (resolve_or_create_profile's fallback path, when the Clerk
            # webhook hasn't provisioned it yet). Commit that before raising -
            # get_db's exception handler rolls back on ANY Exception,
            # HTTPException included, which would otherwise silently discard
            # a brand-new profile every time an authenticated-but-
            # unauthorized user hits a role-gated route. "We identified you"
            # and "you're not authorized for this" are separate facts; one
            # shouldn't undo the other. Safe here specifically because this
            # runs as a route-level dependency, before the route body (and
            # any of its own writes) ever executes.
            await db.commit()
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user_id

    return _check
