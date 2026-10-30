"""Repository layer for cover_letter's one Postgres table."""

from __future__ import annotations

from sqlalchemy import select

from app.shared.repository import UserScopedRepository
from app.modules.cover_letter.models import CoverLetterSession


class CoverLetterSessionRepository(UserScopedRepository[CoverLetterSession]):
    model = CoverLetterSession

    async def get_by_source(
        self, user_id: str, *, source_opportunity_id: str | None = None, source_application_id: str | None = None,
    ) -> CoverLetterSession | None:
        """The existing session already linked to this job, if any - the
        upsert target for "only one saved cover letter per job" (see
        routes.py). Exactly one of the two ids should be given; if both are
        None this returns None rather than matching every unlinked row."""
        if not source_opportunity_id and not source_application_id:
            return None
        stmt = self._scoped(select(self.model), user_id)
        if source_opportunity_id:
            stmt = stmt.where(self.model.source_opportunity_id == source_opportunity_id)
        else:
            stmt = stmt.where(self.model.source_application_id == source_application_id)
        stmt = stmt.order_by(self.model.created_at.desc()).limit(1)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create_session(
        self,
        user_id: str,
        *,
        company: str,
        role: str,
        selling_points: str,
        resume_text: str | None,
        content: str,
        source_opportunity_id: str | None = None,
        source_application_id: str | None = None,
    ) -> CoverLetterSession:
        return await self.create(
            user_id,
            company=company,
            role=role,
            selling_points=selling_points,
            resume_text=resume_text,
            content=content,
            source_opportunity_id=source_opportunity_id,
            source_application_id=source_application_id,
        )

    async def set_title(self, user_id: str, id_: str, title: str) -> CoverLetterSession | None:
        return await self.update(user_id, id_, title=title)
