"""Repository layer for cover_letter's one Postgres table."""

from __future__ import annotations

from app.shared.repository import UserScopedRepository
from app.modules.cover_letter.models import CoverLetterSession


class CoverLetterSessionRepository(UserScopedRepository[CoverLetterSession]):
    model = CoverLetterSession

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
