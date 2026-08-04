import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, UUIDPKMixin, CreatedAtMixin


class JobApplication(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "job_applications"
    __table_args__ = (
        Index("applications_user_id_idx", "user_id"),
        Index("applications_status_idx", "status"),
        Index("applications_follow_up_idx", "follow_up_date"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    company: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    applied_at: Mapped[date] = mapped_column(
        Date, server_default=text("current_date"), nullable=False
    )
    # Applied | Phone Screen | Interview | Offer | Rejected | Withdrawn
    status: Mapped[str] = mapped_column(Text, server_default="Applied", nullable=False)
    follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Trigger-managed (set_updated_at()) — no ORM onupdate, see shared/models.py note.
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
