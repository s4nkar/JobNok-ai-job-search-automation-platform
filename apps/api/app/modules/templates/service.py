"""Template CRUD business logic — SQLAlchemy-backed."""

import re

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.repository import UserScopedRepository
from app.shared.utils import row_to_dict
from app.modules.templates.models import Template
from app.modules.templates.schemas import TemplateIn, TemplateUpdate


def extract_placeholders(content: str) -> list[str]:
    matches = re.findall(r"\{\{([^}]+)\}\}", content)
    seen: list[str] = []
    for m in matches:
        key = m.strip()
        if key not in seen:
            seen.append(key)
    return seen


class TemplateRepository(UserScopedRepository[Template]):
    model = Template

    async def increment_use_count(self, user_id: str, id_: str) -> Template | None:
        """Atomic `SET use_count = use_count + 1` at the DB layer - avoids
        the race a client-computed "current + 1" PUT had (two rapid copies,
        or two browser tabs, could both read the same stale count and both
        write the same incremented value, silently losing one)."""
        stmt = (
            self._scoped(update(self.model), user_id)
            .where(self.model.id == id_)
            .values(use_count=self.model.use_count + 1)
            .returning(self.model)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


async def list_templates(db: AsyncSession, user_id: str) -> list[dict]:
    rows = await TemplateRepository(db).list(user_id, order_by=Template.created_at.desc())
    return [row_to_dict(r) for r in rows]


async def create_template(db: AsyncSession, user_id: str, body: TemplateIn) -> dict:
    placeholders = extract_placeholders(body.content)
    obj = await TemplateRepository(db).create(
        user_id, **body.model_dump(), placeholders=placeholders
    )
    return row_to_dict(obj)


async def update_template(db: AsyncSession, user_id: str, template_id: str, body: TemplateUpdate) -> dict:
    # exclude_unset distinguishes "not sent" from "sent as null"
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=422, detail="At least one field must be provided")
    if "content" in payload:
        payload["placeholders"] = extract_placeholders(payload["content"])
    obj = await TemplateRepository(db).update(user_id, template_id, **payload)
    if obj is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row_to_dict(obj)


async def delete_template(db: AsyncSession, user_id: str, template_id: str) -> None:
    ok = await TemplateRepository(db).delete(user_id, template_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")


async def increment_use_count(db: AsyncSession, user_id: str, template_id: str) -> dict:
    obj = await TemplateRepository(db).increment_use_count(user_id, template_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row_to_dict(obj)
