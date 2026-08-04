from datetime import datetime

from sqlalchemy import Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, UUIDPKMixin


class LinkedinCache(Base, UUIDPKMixin):
    __tablename__ = "linkedin_cache"
    __table_args__ = (
        Index("linkedin_cache_url_idx", "linkedin_url"),
        Index("linkedin_cache_scraped_at_idx", "scraped_at"),
    )

    # No user_id, no RLS — shared cache across users for the same URL.
    linkedin_url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    scraped_data: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    scraped_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
