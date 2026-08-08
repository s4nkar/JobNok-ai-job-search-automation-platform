import uuid
from datetime import date, datetime

from sqlalchemy import Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base


class Profile(Base):
    __tablename__ = "profiles"

    # App-generated — Clerk's own user id (a string like "user_xxx", not a
    # UUID) is never used as the primary key directly; clerk_user_id below
    # maps it to this internal id instead, so every other table's FK stays a
    # plain uuid unaffected by the auth-provider's id format.
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    clerk_user_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    role: Mapped[str] = mapped_column(Text, server_default="user", nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan: Mapped[str] = mapped_column(Text, server_default="free", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    # CV profile extended fields
    job_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_street: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_country: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(nullable=True)
    nationality: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    website_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_authorization: Mapped[str | None] = mapped_column(Text, nullable=True)
    cv_photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    cv_email: Mapped[str | None] = mapped_column(Text, nullable=True)
