"""Bulk company-registry resolution (Pipeline B, PRD section 8.2) - reuses
resolver.py's existing try_direct_resolve/try_fallback_resolve unchanged
(same 3 ATS types), only the write target differs: a CompanyRegistry row
instead of a StartupHuntSource row (see resolver.py's own module docstring
for the "My Sources" flow this doesn't touch).
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.modules.startup_hunt import resolver
from app.modules.startup_hunt.models import CompanyRegistry

_NO_CAREERS_PAGE_ERROR = "No website or careers URL to resolve against."


async def resolve_company(company: CompanyRegistry) -> None:
    """Mutates `company` in place (caller flushes/commits). Tries the fast
    direct-resolve path first (one slug guess per ATS type), falling back to
    the slower multi-variant resolver only if that misses - mirrors
    service.py's resolve_startup_hunt_source, minus its cross-user reuse
    tier (no equivalent here: every company is already a single global row,
    there's no "has some other user already resolved this" question to ask).

    On no ATS match, falls through to the generic career-page crawler as a
    best-effort fallback (ats_provider='generic') rather than failing
    outright when there's still a website/careers URL to try - it may find
    zero jobs (the sync worker marks the company 'no_jobs' then, not a
    resolution failure - see PRD section 21).
    """
    company_input = company.career_url or company.website_url or company.name
    resolved = await resolver.try_direct_resolve(company_input)
    if resolved is None:
        resolved = await resolver.try_fallback_resolve(company_input)

    company.last_resolved_at = datetime.now(timezone.utc)

    if resolved is not None:
        company.ats_provider = resolved.type
        company.ats_identifier = resolved.slug
        company.career_url = resolved.url or company.career_url
        company.status = "resolved"
        company.last_error = None
        return

    fallback_url = company.career_url or company.website_url
    if fallback_url:
        company.ats_provider = "generic"
        company.ats_identifier = None
        company.career_url = fallback_url
        company.status = "resolved"
        company.last_error = None
        return

    company.status = "no_careers_page"
    company.last_error = _NO_CAREERS_PAGE_ERROR
