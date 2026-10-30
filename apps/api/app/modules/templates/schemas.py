"""Request/response models for the templates feature (resume-template CRUD)."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

# Mirrors the frontend's TemplateCategory union (apps/web/lib/types.ts) —
# kept in sync by hand, same pattern CLAUDE.md documents for every other
# Zod/Pydantic pair in this codebase. Previously a bare `str` on the
# backend accepted any value regardless of what the frontend's Zod enum
# allowed - no server-side enforcement at all.
TemplateCategory = Literal[
    "Cold DM - Recruiter", "Cold DM - Hiring Manager", "Follow-Up", "Referral Ask", "Email Outreach", "Custom",
]

# Previously unbounded (CLAUDE.md: "Input length limits: every text field
# has a max length... Unbounded inputs are a DoS vector") - name/content had
# only a min-length check, no ceiling at either the Pydantic or DB layer.
_NAME_MAX_LENGTH = 100
_CONTENT_MAX_LENGTH = 5000


class TemplateIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=_NAME_MAX_LENGTH)
    category: TemplateCategory
    content: str = Field(..., min_length=10, max_length=_CONTENT_MAX_LENGTH)


class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=_NAME_MAX_LENGTH)
    category: Optional[TemplateCategory] = None
    content: Optional[str] = Field(None, min_length=10, max_length=_CONTENT_MAX_LENGTH)
    # use_count is intentionally NOT here - a client could previously PUT
    # an arbitrary integer directly (the frontend computed "current + 1"
    # client-side and sent it, trusting that value outright - a race
    # between two tabs/rapid copies could also under-count). It's now only
    # ever changed via POST /templates/{id}/use, which increments
    # atomically at the DB layer. See routes.py/service.py.
