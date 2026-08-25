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
    """Mutates `company` in place (caller flushes/commits).

    Tries company NAME first (slug-guessing against all 3 ATS types via
    resolver.try_direct_resolve/try_fallback_resolve), only falling through
    to scanning an actual URL (career_url if known, else the homepage) if
    that misses. This order matters and isn't arbitrary: resolver.py's
    try_fallback_resolve explicitly skips its own slug-guessing entirely
    whenever the input already looks like a URL ("already retried in full
    just above" - see its own comment), since it was built for the "My
    Sources" flow where a user provides a name OR a careers URL, never
    both. Discovery only ever gives us a homepage URL, never a bare name-as-
    input case that flow expects - passing that URL in first (as an earlier
    version of this function did) meant slug-guessing never ran at all, and
    every company fell straight through to the generic fallback regardless
    of whether it actually had a real, resolvable ATS board.

    On no ATS match either way, falls through to the generic career-page
    crawler as a best-effort fallback (ats_provider='generic') rather than
    failing outright when there's still a website/careers URL to try - it
    may find zero jobs (the sync worker marks the company 'no_jobs' then,
    not a resolution failure - see PRD section 21).
    """
    resolved = await resolver.try_direct_resolve(company.name)
    if resolved is None:
        resolved = await resolver.try_fallback_resolve(company.name)

    if resolved is None:
        url_input = company.career_url or company.website_url
        if url_input:
            resolved = await resolver.try_direct_resolve(url_input)

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
