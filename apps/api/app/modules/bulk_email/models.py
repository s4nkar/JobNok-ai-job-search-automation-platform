import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, UUIDPKMixin, CreatedAtMixin


class EmailCampaign(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "email_campaigns"
    __table_args__ = (
        Index("campaigns_user_id_idx", "user_id"),
        Index("campaigns_status_idx", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # draft | queued | sending | completed | paused | failed — no DB CHECK constraint,
    # just a comment in schema.sql; not enforced here either to match the real DB.
    status: Mapped[str] = mapped_column(Text, server_default="draft", nullable=False)
    delay_seconds: Mapped[int] = mapped_column(Integer, server_default="30", nullable=False)


class EmailRecipient(Base, UUIDPKMixin):
    __tablename__ = "email_recipients"
    __table_args__ = (
        Index("recipients_campaign_id_idx", "campaign_id"),
        Index("recipients_status_idx", "status"),
    )

    # No created_at / user_id column — ownership is derived transitively through campaign_id.
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("email_campaigns.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, server_default="", nullable=False)
    variables: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    # queued | sending | sent | failed
    status: Mapped[str] = mapped_column(Text, server_default="queued", nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
