"""Cross-module helpers shared by more than one feature module."""

import re

from fastapi import HTTPException
from sqlalchemy import inspect

_SENTENCE_END_RE = re.compile(r"[.!?](?=\s|$)")


def clean_truncated_text(text: str, min_keep_ratio: float = 0.4) -> str:
    """Trims a hard-truncated description back to its last complete
    sentence instead of leaving it cut off mid-word.

    Both startup_hunt/discovery/startupmap.py (StartupMap's own JSON-LD
    `description` field, verified live to be hard-capped at exactly 300
    characters server-side with no more text to fetch beyond that) and
    startup_scout/engine.py (a DDG search snippet, sliced at a fixed
    character count) produce text that's cut off at an arbitrary character
    position, not a word or sentence boundary - there is no "full"
    description to recover in either case, only a cleaner way to present
    what's already there.

    Cuts back to the last ". "/"! "/"? " if one exists and doing so doesn't
    throw away most of the text (min_keep_ratio guards against a case where
    the only sentence break is very early, which would leave almost
    nothing); otherwise falls back to the last complete word plus an
    ellipsis, so it's never a naked mid-word cut either way.
    """
    text = text.strip()
    if not text or text[-1] in ".!?":
        return text
    matches = list(_SENTENCE_END_RE.finditer(text))
    if matches:
        cut = matches[-1].end()
        if cut >= len(text) * min_keep_ratio:
            return text[:cut].strip()
    last_space = text.rfind(" ")
    if last_space > 0:
        return text[:last_space].rstrip(",;:-–— ") + "…"
    return text + "…"


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
