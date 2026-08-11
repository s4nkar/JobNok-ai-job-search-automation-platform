import uuid

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, UUIDPKMixin, CreatedAtMixin


class ToolUsageEvent(Base, UUIDPKMixin, CreatedAtMixin):
    """One row per tool invocation — powers the dashboard's most/recently-used
    widget. Deliberately event-level (not an aggregate counter) so a future
    activity timeline can be built from the same table without a migration."""

    __tablename__ = "tool_usage_events"
    __table_args__ = (
        Index("tool_usage_events_user_id_idx", "user_id"),
        Index("tool_usage_events_user_tool_idx", "user_id", "tool_slug"),
        Index("tool_usage_events_user_created_idx", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    tool_slug: Mapped[str] = mapped_column(Text, nullable=False)
