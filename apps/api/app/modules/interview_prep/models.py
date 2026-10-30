"""Postgres persistence for explicitly-saved interview-prep kits.

One table, interview_prep_sessions - mirrors cover_letter_sessions (same
explicit-Save-only, no-ai_status-tracking shape): a kit the user chose to
keep, not every generation. "result" holds the already-validated
generation output (role_assessment + questions + dsa_questions +
system_design_questions) as JSONB rather than re-deriving columns per field -
it's read-only display data on reopen, never queried into individually.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, UUIDPKMixin, CreatedAtMixin


class InterviewPrepSession(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "interview_prep_sessions"
    __table_args__ = (
        # Defense in depth alongside the Pydantic max_length boundary check
        # in schemas.py - belt-and-suspenders per this codebase's input
        # length convention.
        CheckConstraint("char_length(job_description) <= 12000", name="interview_prep_sessions_jd_length_check"),
        CheckConstraint("company is null or char_length(company) <= 200", name="interview_prep_sessions_company_length_check"),
        CheckConstraint("role is null or char_length(role) <= 200", name="interview_prep_sessions_role_length_check"),
        CheckConstraint("title is null or char_length(title) <= 200", name="interview_prep_sessions_title_length_check"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    job_description: Mapped[str] = mapped_column(nullable=False)
    # Unlike cover_letter_sessions' company/role (always literal form
    # fields), these are nullable here - a plain pasted JD with no known
    # company/role context is a normal, common case for this tool.
    company: Mapped[str | None] = mapped_column(nullable=True)
    role: Mapped[str | None] = mapped_column(nullable=True)
    # The validated generation output: role_assessment, questions,
    # dsa_questions, system_design_questions - same shape
    # validate_interview_response returns.
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # User-chosen label, same UX as the other two tools' sessions - NULL
    # until renamed, falls back to a generated display label.
    title: Mapped[str | None] = mapped_column(nullable=True)
    # Linkage, not ownership - same pattern as TailoringSession/
    # CoverLetterSession, letting My Docs group a resume, a cover letter,
    # and an interview kit all saved for the same job. ON DELETE SET NULL:
    # a saved kit is still worth keeping if the user later deletes the
    # application/opportunity it was prepared for.
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
