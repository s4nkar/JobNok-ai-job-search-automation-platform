"""Tool usage event logging + aggregation for the dashboard's usage widget."""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.repository import UserScopedRepository
from app.modules.usage.models import ToolUsageEvent

logger = logging.getLogger(__name__)


class ToolUsageRepository(UserScopedRepository[ToolUsageEvent]):
    model = ToolUsageEvent


async def record_event(db: AsyncSession, user_id: str, tool_slug: str) -> None:
    """Fire-and-forget usage log, called from each tool's route right after
    it passes auth/rate-limiting. Wrapped in a SAVEPOINT so a logging failure
    can never poison or roll back the request's actual work — only this
    insert is undone, and the surrounding transaction commits normally.
    """
    try:
        async with db.begin_nested():
            await ToolUsageRepository(db).create(user_id, tool_slug=tool_slug)
    except Exception:
        logger.warning("Failed to record tool usage event: tool=%s", tool_slug, exc_info=True)


async def get_summary(db: AsyncSession, user_id: str) -> list[dict]:
    """Per-tool usage: total count + last-used timestamp, most recently used first."""
    stmt = (
        select(
            ToolUsageEvent.tool_slug,
            func.count().label("use_count"),
            func.max(ToolUsageEvent.created_at).label("last_used_at"),
        )
        .where(ToolUsageEvent.user_id == user_id)
        .group_by(ToolUsageEvent.tool_slug)
        .order_by(func.max(ToolUsageEvent.created_at).desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {"tool_slug": r.tool_slug, "use_count": r.use_count, "last_used_at": r.last_used_at}
        for r in rows
    ]
