"""ARQ task for the slow-path (async fallback) company resolution behind
My Sources' "smart add" flow - see resolver.py for the fast synchronous
path this only runs after, and service.py's resolve_startup_hunt_source for
where a 'pending' row and this job both get created."""

from app.core.database import AsyncSessionLocal
from app.modules.startup_hunt import resolver
from app.modules.startup_hunt.models import StartupHuntSource


async def resolve_startup_hunt_source_task(ctx: dict, source_id: str) -> None:
    """Background fallback resolution for one StartupHuntSource row left
    'pending' by the fast sync path timing out. Tries harder (more slug
    variants, a fresh un-timed-out URL retry - see
    resolver.try_fallback_resolve) than the fast path did, then marks the
    row resolved or failed so the frontend's poll picks up the result."""
    async with AsyncSessionLocal() as session:
        source = await session.get(StartupHuntSource, source_id)
        if source is None or source.status != "pending":
            return  # already resolved/failed/deleted through another path

        resolved = await resolver.try_fallback_resolve(source.name)

        if resolved is not None:
            source.type = resolved.type
            source.slug = resolved.slug
            source.status = "resolved"
            source.resolution_error = None
        else:
            source.status = "failed"
            source.resolution_error = (
                "Could not find a Greenhouse, Lever, or Ashby board for this company. "
                "Try a more specific name, paste its careers URL directly, or add it manually."
            )

        await session.commit()
