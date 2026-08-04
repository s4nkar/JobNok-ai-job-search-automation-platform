"""Cross-module helpers shared by more than one feature module."""

from fastapi import HTTPException
from sqlalchemy import inspect


def _rl_error(tool: str, limit: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail=f"Daily limit of {limit} {tool} uses reached. Resets at midnight UTC."
    )


def row_to_dict(obj) -> dict:
    """Serialize a SQLAlchemy model instance into a plain JSON-safe dict.

    FastAPI's jsonable_encoder doesn't know how to serialize arbitrary ORM
    objects (it would walk __dict__ and choke on SQLAlchemy's internal
    _sa_instance_state), but it handles plain dicts — including UUID/datetime/
    date values within them — natively.

    Uses mapper introspection (not obj.__table__.columns + getattr(obj, c.name))
    because a few models rename their Python attribute away from the DB column
    name (e.g. OpportunityArtifact.metadata_ -> db column "metadata", since
    `metadata` is reserved on declarative models for Base.metadata). Column-name
    getattr would silently return that unrelated class attribute instead of the
    real value in those cases.
    """
    mapper = inspect(obj).mapper
    return {attr.columns[0].name: getattr(obj, attr.key) for attr in mapper.column_attrs}
