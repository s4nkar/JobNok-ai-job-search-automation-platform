import uuid

from sqlalchemy import ARRAY, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, UUIDPKMixin, CreatedAtMixin


class Template(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "templates"
    __table_args__ = (
        Index("templates_user_id_idx", "user_id"),
        Index("templates_category_idx", "category"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, server_default="Custom", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    placeholders: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default="{}", nullable=False
    )
    use_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
