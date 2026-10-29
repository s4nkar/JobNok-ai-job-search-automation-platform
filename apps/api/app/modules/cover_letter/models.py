"""Postgres persistence for explicitly-saved cover letters.

One table, cover_letter_sessions - a saved letter a user chose to keep, not
every generation (generation itself stays stateless/stream-only, see
routes.py). Deliberately simpler than resume_tailor's TailoringSession: no
chunking/matching/draft/template system, no ai_status tracking - only a
successfully-generated letter the user decided to save ever becomes a row.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, UUIDPKMixin, CreatedAtMixin


class CoverLetterSession(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "cover_letter_sessions"
    __table_args__ = (
        # Defense in depth alongside the Pydantic max_length boundary check
        # in schemas.py - belt-and-suspenders per this codebase's input
        # length convention, in case a future code path ever writes this
        # table without going through CoverLetterSaveRequest.
        CheckConstraint("char_length(company) <= 200", name="cover_letter_sessions_company_length_check"),
        CheckConstraint("char_length(role) <= 200", name="cover_letter_sessions_role_length_check"),
        CheckConstraint("char_length(selling_points) <= 3000", name="cover_letter_sessions_selling_points_length_check"),
        CheckConstraint("char_length(content) <= 5000", name="cover_letter_sessions_content_length_check"),
        CheckConstraint("title is null or char_length(title) <= 200", name="cover_letter_sessions_title_length_check"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    company: Mapped[str] = mapped_column(nullable=False)
    role: Mapped[str] = mapped_column(nullable=False)
    selling_points: Mapped[str] = mapped_column(nullable=False)
    resume_text: Mapped[str | None] = mapped_column(nullable=True)
    # The saved (possibly user-edited) letter text, exactly as shown in the
    # frontend's editable textarea at the moment of Save.
    content: Mapped[str] = mapped_column(nullable=False)
    # User-chosen label, same UX as TailoringSession.title - NULL until
    # renamed, falls back to a generic "{role} at {company}" display label.
    title: Mapped[str | None] = mapped_column(nullable=True)
    # Linkage, not ownership - same pattern as TailoringSession's own two
    # columns (resume_tailor/models.py), letting My Docs group a resume and
    # a cover letter saved for the same job. ON DELETE SET NULL: a saved
    # letter is still worth keeping if the user later deletes the
    # application/opportunity it was written for.
    source_opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("startup_hunt_opportunities.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_application_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("job_search_applications.id", ondelete="SET NULL"),
        nullable=True,
    )
