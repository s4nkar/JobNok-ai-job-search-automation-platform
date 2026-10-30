"""Repository layer for interview_prep's one Postgres table."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.shared.repository import UserScopedRepository
from app.modules.interview_prep.models import InterviewPrepSession


class InterviewPrepSessionRepository(UserScopedRepository[InterviewPrepSession]):
    model = InterviewPrepSession

    async def get_by_source(
        self, user_id: str, *, source_opportunity_id: str | None = None, source_application_id: str | None = None,
    ) -> InterviewPrepSession | None:
        """The existing session already linked to this job, if any - the
        upsert target for "only one saved interview kit per job" (see
        service.py::resolve_session). Exactly one of the two ids should be
        given; if both are None this returns None rather than matching
        every unlinked row."""
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
        job_description: str,
        company: str | None,
        role: str | None,
        result: dict[str, Any],
        source_opportunity_id: str | None = None,
        source_application_id: str | None = None,
    ) -> InterviewPrepSession:
        return await self.create(
            user_id,
            job_description=job_description,
            company=company,
            role=role,
            result=result,
            source_opportunity_id=source_opportunity_id,
            source_application_id=source_application_id,
        )

    async def set_title(self, user_id: str, id_: str, title: str) -> InterviewPrepSession | None:
        return await self.update(user_id, id_, title=title)
