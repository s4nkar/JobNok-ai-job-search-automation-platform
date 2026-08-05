"""Job application tracker CRUD business logic — SQLAlchemy-backed."""

from datetime import date

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.repository import UserScopedRepository
from app.shared.utils import row_to_dict
from app.modules.tracker.models import JobApplication
from app.modules.tracker.schemas import ApplicationIn


class TrackerRepository(UserScopedRepository[JobApplication]):
    model = JobApplication


def _application_fields(body: ApplicationIn) -> dict:
    """Convert ApplicationIn's string/float wire types to the Python types
    asyncpg expects for Date/Integer columns (Postgres/PostgREST used to
    coerce these implicitly; SQLAlchemy+asyncpg requires exact types)."""
    data = body.model_dump()
    data["applied_at"] = date.fromisoformat(data["applied_at"])
    if data.get("follow_up_date"):
        data["follow_up_date"] = date.fromisoformat(data["follow_up_date"])
    if data.get("salary_min") is not None:
        data["salary_min"] = int(data["salary_min"])
    if data.get("salary_max") is not None:
        data["salary_max"] = int(data["salary_max"])
    return data


async def list_applications(db: AsyncSession, user_id: str) -> list[dict]:
    rows = await TrackerRepository(db).list(user_id, order_by=JobApplication.created_at.desc())
    return [row_to_dict(r) for r in rows]


async def create_application(db: AsyncSession, user_id: str, body: ApplicationIn) -> dict:
    obj = await TrackerRepository(db).create(user_id, **_application_fields(body))
    return row_to_dict(obj)


async def update_application(db: AsyncSession, user_id: str, app_id: str, body: ApplicationIn) -> dict:
    obj = await TrackerRepository(db).update(user_id, app_id, **_application_fields(body))
    if obj is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row_to_dict(obj)


async def delete_application(db: AsyncSession, user_id: str, app_id: str) -> None:
    ok = await TrackerRepository(db).delete(user_id, app_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
