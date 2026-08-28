"""Startup Scout business logic — SQLAlchemy-backed.

_run_crawl runs as a FastAPI BackgroundTask (after the HTTP response is
sent), so it cannot reuse the request-scoped AsyncSession from Depends(get_db)
— it opens its own session via AsyncSessionLocal() and commits incrementally,
mirroring the original supabase-py calls' per-statement auto-commit behavior.
"""

import asyncio
import hashlib
import json
import logging
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.services.cache import acquire_lock, get_cached, jittered_ttl, record_search_outcome, set_cached
from app.shared import funding_stages
from app.shared.repository import UserScopedRepository
from app.shared.utils import row_to_dict
from app.modules.startup_hunt.discovery.discovery_service import upsert_discovered
from app.modules.startup_hunt.discovery.startup_source import DiscoveredStartup
from app.modules.startup_hunt.models import CompanyRegistry
from app.modules.startup_scout import engine
from app.modules.startup_scout.models import StartupScoutCompany, StartupScoutContact
from app.modules.startup_scout.schemas import SaveCompanyRequest
from app.modules.startup_scout.engine import (
    apollo_search_contacts,
    enrich_linkedin_url,
    verify_contact,
    web_search_contacts,
)

log = logging.getLogger(__name__)

_SINGLE_FLIGHT_LOCK_TTL_SECONDS = 20
_SINGLE_FLIGHT_POLL_INTERVAL_SECONDS = 0.5
_SINGLE_FLIGHT_MAX_WAIT_SECONDS = 10

MIN_VERIFIED_CONTACTS = 2

# In-process cancel flags keyed by company_id.
# Set to True by the /stop endpoint; run_crawl checks between each contact save.
_cancel_flags: dict[str, bool] = {}


class CompanyRepository(UserScopedRepository[StartupScoutCompany]):
    model = StartupScoutCompany


# ── Phase A search: response cache + company_registry DB-first layer ───────

def _response_cache_key(location: str, funding_stages: list[str], industry: str, limit: int) -> str:
    parts = [
        location.strip().lower(),
        ",".join(sorted(s.strip().lower() for s in funding_stages)),
        industry.strip().lower(),
        str(limit),
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"startup_scout:{digest}"


async def _company_registry_candidates(
    db: AsyncSession, location: str, funding_stages_filter: list[str], limit: int
) -> list[dict]:
    """DB-first layer, reusing the crawler's own company_registry - free,
    always-available candidates for any location the crawler (or a prior
    startup_scout search) has already discovered.

    CompanyRegistry.country/.city are free text copied straight from whatever
    the discovery source reported (e.g. "Germany" - see
    startup_hunt/discovery/startupmap.py), not ISO codes, so this matches via
    a plain case-insensitive substring check against location's own
    comma-separated parts rather than a country-code lookup.

    funding_stage CAN now be verified (both discovery paths populate it - see
    app/shared/funding_stages.py) - a row with a still-NULL value is excluded
    when a filter is given rather than assumed to match, since "unknown"
    isn't evidence of a match. Company size is not filterable (removed from
    the UI - too sparse to search on, see employee_count_min/max's own
    genuinely-empty-for-many-companies ceiling), it's still returned below
    for display only, when the row happens to have it.
    """
    parts = [p.strip() for p in location.split(",") if p.strip()]
    if not parts:
        return []
    conditions = [or_(*[
        or_(CompanyRegistry.city.ilike(f"%{p}%"), CompanyRegistry.country.ilike(f"%{p}%"))
        for p in parts
    ])]

    if funding_stages_filter:
        conditions.append(CompanyRegistry.funding_stage.in_(funding_stages_filter))

    rows = (
        await db.execute(
            select(CompanyRegistry)
            .where(*conditions)
            .order_by(CompanyRegistry.last_discovered_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "name": row.name,
            "description": row.description or "",
            "funding_stage": funding_stages.display_stage(row.funding_stage) if row.funding_stage else "",
            "location": ", ".join(p for p in [row.city, row.country] if p) or location,
            "size_range": (
                f"{row.employee_count_min}-{row.employee_count_max}"
                if row.employee_count_min is not None and row.employee_count_max is not None
                else ""
            ),
            "website": row.website_url or "",
            "domain": row.domain or "",
            "source": "company_registry",
        }
        for row in rows
    ]


async def _store_discovered_companies(db: AsyncSession, location: str, companies: list[dict]) -> None:
    """Feed live-scraped companies back into the crawler's company_registry so
    a repeat search (from anyone) can be served from _company_registry_candidates
    instead of scraping again, and so startup_hunt's own resolution pipeline
    might eventually resolve/sync jobs for a company scout found first (see
    ingestion/scheduler.py::sweep_undiscovered_companies, which is what
    actually enqueues that resolution - this function only writes the row).

    domain/website_url are deliberately left None. What engine._parse_company
    calls "website" is the DIRECTORY PROFILE page (e.g.
    crunchbase.com/organization/x), never the startup's own site, and its
    "domain" is that directory's domain (crunchbase.com) - writing either into
    company_registry.domain/website_url would corrupt those fields for
    startup_hunt's ats_resolver.py, which uses website_url as a career-page
    fallback target. discovery_source_url (whose whole purpose is "where I
    found this listing") is the field this profile URL actually belongs in.

    city: best-effort only, and only when location has no comma (a single
    unambiguous value) - a multi-city search ("Berlin, Munich, Remote") can't
    be attributed to one specific found company's actual city. Written into
    `city` regardless of whether it's actually a city or country name (e.g.
    "Germany") since _company_registry_candidates' own read-side query already
    checks both columns - a search for "Germany" will still find a row with
    "Germany" sitting in `city`, so this is functionally harmless even though
    it isn't fully accurate data.
    """
    location_parts = [p.strip() for p in location.split(",") if p.strip()]
    single_location = location_parts[0] if len(location_parts) == 1 else None

    items: list[DiscoveredStartup] = []
    for c in companies:
        profile_url = (c.get("website") or "").strip()
        name = (c.get("name") or "").strip()
        if not profile_url or not name:
            continue
        # engine._parse_company already extracts these from the scraped
        # snippet (they're what the UI card shows) - just weren't being
        # persisted anywhere until now. funding_stage comes back in
        # Title-Case display form ("Series A"); canonical_stage() converts
        # to the lowercase-hyphenated form the DB column actually stores.
        raw_stage = (c.get("funding_stage") or "").strip()
        employee_min, employee_max = funding_stages.parse_employee_range(c.get("size_range") or "")
        items.append(
            DiscoveredStartup(
                name=name,
                domain=None,
                website_url=None,
                country=None,
                city=single_location,
                discovery_source="startup_scout",
                discovery_source_url=profile_url,
                discovery_source_id=profile_url.rstrip("/").lower(),
                funding_stage=funding_stages.canonical_stage(raw_stage) if raw_stage else None,
                employee_count_min=employee_min,
                employee_count_max=employee_max,
                description=(c.get("description") or "").strip() or None,
            )
        )
    if not items:
        return
    try:
        await upsert_discovered(db, items)
        await db.commit()
    except Exception:
        await db.rollback()
        log.warning("startup_scout: failed to write discovered companies back to company_registry", exc_info=True)


def _dedupe_key(c: dict) -> str:
    """Prefers a real registrable domain, EXCEPT for a known startup-
    directory host (crunchbase.com, wellfound.com, ... - see
    engine.py::_DIRECTORY_PROFILE_PATHS) - there, "domain" is the
    DIRECTORY's own domain, not the startup's (a scraped live "website" for
    these is really a directory profile page, see
    _store_discovered_companies' docstring above), so every company sourced
    from the same directory would otherwise collapse onto one shared
    bare-domain key ("crunchbase.com") and wrongly dedupe against each
    other - verified live: a London/AI/seed search's live top-up found 3
    distinct Crunchbase-listed companies but only 1 survived the old logic,
    the other 2 silently vanishing as "duplicates" of the first. Falls back
    to the full profile URL (unique per company) for those hosts instead.
    """
    domain = (c.get("domain") or "").rstrip("/").lower()
    if domain and domain not in engine._DIRECTORY_PROFILE_PATHS:
        return domain
    website = (c.get("website") or "").rstrip("/").lower()
    return website or domain or c.get("name", "").strip().lower()


async def search_startups_stream(
    *,
    location: str,
    funding_stages: list[str],
    industry: str,
    limit: int,
):
    """Phase A orchestration, as an async generator of progressive events
    instead of one final dict - L2 company_registry is near-instant (a local
    DB query), while the live DDG top-up (engine.search_startups) is the slow
    part (observed several seconds, sometimes more, per search) - see
    routes.py::scout_search, which streams these events straight to the
    frontend as newline-delimited JSON so the UI can render L2's results the
    moment they're known instead of blocking the whole page on DDG.

    Yields:
      {"type": "partial", "companies": [...], "meta": {...}} - L2 results
        only, "meta" reflects L2-so-far (queries_run always 0 here).
      {"type": "done", "companies": [...], "meta": {...}} - the same shape
        callers got from the old non-streaming version, either the L2-only
        result (if L2 alone met `limit`, no "partial" event's companies
        change) or L2 merged with the live DDG top-up.

    Manages its own DB session (AsyncSessionLocal, not Depends(get_db)) -
    this generator keeps running (and yields further events) after the route
    handler's own function body has already returned the StreamingResponse,
    the same reason run_crawl (a BackgroundTask, see this module's own
    docstring) can't reuse a request-scoped session either.

    Caching/single-flight-lock/outcome-recording semantics are unchanged
    from the old non-streaming version - only followers (a second identical
    search arriving while another is already in flight) don't get the
    "partial" event, since they're just waiting on the leader's cache write;
    they still get one "done" event once it appears, same as before.
    """
    cache_key = _response_cache_key(location, funding_stages, industry, limit)
    try:
        cached = await get_cached(cache_key)
    except Exception:
        cached = None
    if cached:
        try:
            result = json.loads(cached)
            await record_search_outcome("startup_scout", "l1_hit")
            yield {"type": "done", **result}
            return
        except json.JSONDecodeError:
            pass

    try:
        is_leader = await acquire_lock(f"{cache_key}:lock", _SINGLE_FLIGHT_LOCK_TTL_SECONDS)
    except Exception:
        is_leader = True

    if not is_leader:
        waited = 0.0
        while waited < _SINGLE_FLIGHT_MAX_WAIT_SECONDS:
            await asyncio.sleep(_SINGLE_FLIGHT_POLL_INTERVAL_SECONDS)
            waited += _SINGLE_FLIGHT_POLL_INTERVAL_SECONDS
            try:
                cached = await get_cached(cache_key)
            except Exception:
                cached = None
            if cached:
                try:
                    result = json.loads(cached)
                    await record_search_outcome("startup_scout", "l1_hit")
                    yield {"type": "done", **result}
                    return
                except json.JSONDecodeError:
                    break

    async with AsyncSessionLocal() as db:
        # Note: this function's own `funding_stages` parameter (the request's
        # list of stages) intentionally shadows the app.shared.funding_stages
        # module imported at the top of this file - that module is only used
        # inside _company_registry_candidates/_store_discovered_companies
        # below, never directly in this function's body.
        db_candidates = await _company_registry_candidates(db, location, funding_stages, limit)

        partial_meta = {
            "total": len(db_candidates), "limit": limit, "queries_run": 0,
            "sources": {"company_registry": len(db_candidates)} if db_candidates else {},
            "location": location, "industry": industry.strip() or None,
            "funding_stages": funding_stages,
        }
        # L2 rows always have a confirmed (non-NULL) funding_stage when a
        # stage filter is active - see _company_registry_candidates - so
        # there's no "unconfirmed" concept for this layer, unlike the live
        # DDG top-up below.
        yield {"type": "partial", "companies": db_candidates, "unconfirmed": [], "meta": partial_meta}

        if db_candidates and len(db_candidates) >= limit:
            result = {"companies": db_candidates[:limit], "unconfirmed": [], "meta": {**partial_meta, "total": limit}}
            try:
                await set_cached(cache_key, json.dumps(result), jittered_ttl(settings.startup_scout_response_cache_ttl_seconds))
            except Exception:
                pass
            await record_search_outcome("startup_scout", "l2_full")
            yield {"type": "done", **result}
            return

        live_limit = max(10, limit - len(db_candidates))
        live_result = await engine.search_startups(
            location=location, funding_stages=funding_stages, industry=industry,
            limit=live_limit,
        )
        live_companies = live_result["companies"]
        live_unconfirmed = live_result["unconfirmed"]

        # Only the confirmed bucket is written back to company_registry -
        # `live_unconfirmed` (no detectable stage) deliberately never reaches
        # this call. Writing those back would let a company like OpenAI (also
        # has no detectable stage in its Crunchbase snippet) get swept into
        # the shared registry via a "seed" search, and from there into
        # startup_hunt's own resolution/sync pipeline showing up as a
        # "startup" job source - the confirmed/unconfirmed split doubles as
        # the fix for that, not just a display nicety.
        await _store_discovered_companies(db, location, live_companies)

        seen: set[str] = set()
        merged: list[dict] = []
        for c in db_candidates + live_companies:
            key = _dedupe_key(c)
            if key in seen:
                continue
            seen.add(key)
            merged.append(c)
        merged = merged[:limit]

        # Unconfirmed results never count toward `limit` and are deduped
        # against the confirmed list too, in case the same company shows up
        # both ways (already-known via L2 with a confirmed stage, and again
        # in this live batch with an undetected one).
        unconfirmed_merged: list[dict] = []
        for c in live_unconfirmed:
            key = _dedupe_key(c)
            if key in seen:
                continue
            seen.add(key)
            unconfirmed_merged.append(c)

        sources = dict(live_result["meta"]["sources"])
        company_registry_count = sum(1 for c in merged if c.get("source") == "company_registry")
        if company_registry_count:
            sources["company_registry"] = company_registry_count

        result = {
            "companies": merged,
            "unconfirmed": unconfirmed_merged,
            "meta": {
                "total": len(merged), "limit": limit,
                "queries_run": live_result["meta"]["queries_run"],
                "sources": sources, "location": location,
                "industry": industry.strip() or None, "funding_stages": funding_stages,
            },
        }
        try:
            await set_cached(cache_key, json.dumps(result), jittered_ttl(settings.startup_scout_response_cache_ttl_seconds))
        except Exception:
            pass
        await record_search_outcome("startup_scout", "live")
        yield {"type": "done", **result}


async def list_companies(db: AsyncSession, user_id: str) -> list[dict]:
    rows = await CompanyRepository(db).list(user_id, order_by=StartupScoutCompany.created_at.desc())
    return [row_to_dict(r) for r in rows]


async def get_company_or_404(db: AsyncSession, user_id: str, company_id: str) -> dict:
    row = await CompanyRepository(db).get(user_id, company_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return row_to_dict(row)


async def save_company(db: AsyncSession, user_id: str, req: SaveCompanyRequest) -> dict:
    if not req.name.strip():
        raise HTTPException(status_code=422, detail="name is required")

    name = req.name.strip()
    website = req.website.strip()

    # Idempotent save: clicking Save on a company already in this user's
    # tracker (e.g. a repeat search re-showing the same result from cache)
    # must not create a second row for it - previously it did, since this
    # just called .create() unconditionally with no existence check.
    # website is the more reliable key when present (a startup's own site
    # doesn't change name-casing between searches the way a scraped title
    # might); falls back to a case-insensitive name match otherwise.
    dedupe_condition = (
        func.lower(StartupScoutCompany.website) == website.lower()
        if website
        else func.lower(StartupScoutCompany.name) == name.lower()
    )
    existing = (
        await db.execute(
            select(StartupScoutCompany).where(
                StartupScoutCompany.user_id == user_id, dedupe_condition
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return row_to_dict(existing)

    obj = await CompanyRepository(db).create(
        user_id,
        name=name,
        description=req.description,
        what_they_do=req.what_they_do,
        funding_stage=req.funding_stage,
        size_range=req.size_range,
        location=req.location,
        website=req.website,
        linkedin_url=req.linkedin_url,
        source=req.source,
        crawl_status="pending",
    )
    return row_to_dict(obj)


async def delete_company(db: AsyncSession, user_id: str, company_id: str) -> None:
    _cancel_flags[company_id] = True
    ok = await CompanyRepository(db).delete(user_id, company_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Company not found")


async def get_contacts(db: AsyncSession, user_id: str, company_id: str) -> list[dict]:
    rows = (
        await db.execute(
            select(StartupScoutContact)
            .where(StartupScoutContact.company_id == company_id, StartupScoutContact.user_id == user_id)
            .order_by(StartupScoutContact.confidence.desc())
        )
    ).scalars().all()
    return [row_to_dict(r) for r in rows]


async def start_crawl(db: AsyncSession, user_id: str, company_id: str) -> dict:
    company = await get_company_or_404(db, user_id, company_id)
    if company["crawl_status"] == "crawling":
        raise HTTPException(status_code=409, detail="Crawl already in progress")
    return company


async def stop_crawl(db: AsyncSession, user_id: str, company_id: str) -> None:
    company = await get_company_or_404(db, user_id, company_id)
    if company["crawl_status"] != "crawling":
        raise HTTPException(status_code=409, detail="No crawl in progress")
    _cancel_flags[company_id] = True


# ── Background crawl orchestration (own session — runs post-response) ──────

async def _save_contact(db: AsyncSession, company_id: str, user_id: str, contact: dict) -> None:
    obj = StartupScoutContact(
        company_id=company_id,
        user_id=user_id,
        name=contact.get("name"),
        title=contact.get("title"),
        email=contact.get("email"),
        linkedin_url=contact.get("linkedin_url"),
        source=contact.get("source"),
        source_url=contact.get("source_url") or None,
        # Decimal(str(...)) avoids binary-float imprecision landing in the
        # NUMERIC column (a raw Python float binds to its imprecise nearest
        # representable value; going through the decimal string does not).
        confidence=Decimal(str(contact.get("confidence") or 0)),
    )
    db.add(obj)
    await db.flush()


async def _load_saved_contacts(db: AsyncSession, company_id: str) -> list[StartupScoutContact]:
    rows = (
        await db.execute(select(StartupScoutContact).where(StartupScoutContact.company_id == company_id))
    ).scalars().all()
    return list(rows)


async def _enrich_missing_linkedin(db: AsyncSession, company_id: str, company_name: str) -> None:
    rows = await _load_saved_contacts(db, company_id)
    needs_linkedin = [r for r in rows if not r.linkedin_url and r.name]
    log.info("Stage 1.5: enriching LinkedIn for %d contacts without a URL", len(needs_linkedin))

    for row in needs_linkedin:
        if _cancel_flags.get(company_id):
            break
        await asyncio.sleep(1.5)
        linkedin_url = await enrich_linkedin_url(row.name, company_name)
        if not linkedin_url:
            continue
        try:
            row.linkedin_url = linkedin_url
            await db.flush()
            log.info("Stage 1.5: linked %s -> %s", row.name, linkedin_url[:80])
        except Exception as enrich_exc:
            log.warning("Stage 1.5 LinkedIn update failed for %s: %s", row.name, enrich_exc)


async def _verify_saved_contacts(db: AsyncSession, company_id: str, company_name: str) -> int:
    saved_rows = await _load_saved_contacts(db, company_id)
    log.info("Stage 2: verifying %d contacts for %r", len(saved_rows), company_name)

    for row in saved_rows:
        if _cancel_flags.get(company_id):
            break
        contact_name = row.name or ""
        if not contact_name:
            continue

        await asyncio.sleep(1.5)
        is_verified, verification_url = await verify_contact(
            contact_name=contact_name,
            company_name=company_name,
            original_source_url=row.source_url or "",
        )
        try:
            row.is_verified = is_verified
            row.verification_url = verification_url
            await db.flush()
        except Exception as verify_exc:
            log.warning("Stage 2 update failed for contact %s: %s", row.id, verify_exc)

    refreshed_rows = await _load_saved_contacts(db, company_id)
    verified_count = sum(1 for r in refreshed_rows if r.is_verified is True)
    log.info("Stage 2: %d verified contacts for %r", verified_count, company_name)
    return verified_count


async def _supplement_with_apollo(db: AsyncSession, company_id: str, user_id: str, company_name: str) -> int:
    existing_rows = await _load_saved_contacts(db, company_id)
    seen_names = {(r.name or "").strip().lower() for r in existing_rows if (r.name or "").strip()}
    seen_linkedin_urls = {
        (r.linkedin_url or "").strip().rstrip("/").lower() for r in existing_rows if (r.linkedin_url or "").strip()
    }
    seen_emails = {(r.email or "").strip().lower() for r in existing_rows if (r.email or "").strip()}

    apollo_contacts = await apollo_search_contacts(company_name)
    imported = 0
    for contact in apollo_contacts:
        if _cancel_flags.get(company_id):
            break

        name_key = (contact.get("name") or "").strip().lower()
        linkedin_key = (contact.get("linkedin_url") or "").strip().rstrip("/").lower()
        email_key = (contact.get("email") or "").strip().lower()

        is_duplicate = (
            (name_key and name_key in seen_names)
            or (linkedin_key and linkedin_key in seen_linkedin_urls)
            or (email_key and email_key in seen_emails)
        )
        if is_duplicate:
            continue

        await _save_contact(db, company_id, user_id, contact)
        imported += 1

        if name_key:
            seen_names.add(name_key)
        if linkedin_key:
            seen_linkedin_urls.add(linkedin_key)
        if email_key:
            seen_emails.add(email_key)

    log.info("Apollo supplement: imported %d new contacts for %r", imported, company_name)
    return imported


async def run_crawl(company_id: str, user_id: str, company_name: str) -> None:
    """Crawl contacts for a company, saving each one immediately."""
    async with AsyncSessionLocal() as db:
        _cancel_flags.pop(company_id, None)

        company = (
            await db.execute(
                select(StartupScoutCompany).where(
                    StartupScoutCompany.id == company_id, StartupScoutCompany.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if company is None:
            return
        company.crawl_status = "crawling"
        await db.commit()

        await db.execute(
            StartupScoutContact.__table__.delete().where(StartupScoutContact.company_id == company_id)
        )
        await db.commit()

        contacts_saved = 0
        crawl_errored = False

        try:
            web_contacts = await web_search_contacts(company_name)
            for contact in web_contacts:
                if _cancel_flags.get(company_id):
                    break
                await _save_contact(db, company_id, user_id, contact)
                contacts_saved += 1
            await db.commit()

            if contacts_saved == 0 and not _cancel_flags.get(company_id):
                apollo_contacts = await apollo_search_contacts(company_name)
                for contact in apollo_contacts:
                    if _cancel_flags.get(company_id):
                        break
                    await _save_contact(db, company_id, user_id, contact)
                    contacts_saved += 1
                await db.commit()

            verified_contacts = 0
            if contacts_saved > 0 and not _cancel_flags.get(company_id):
                await _enrich_missing_linkedin(db, company_id, company_name)
                verified_contacts = await _verify_saved_contacts(db, company_id, company_name)
                await db.commit()

            if (
                contacts_saved > 0
                and verified_contacts < MIN_VERIFIED_CONTACTS
                and not _cancel_flags.get(company_id)
            ):
                log.info(
                    "Apollo supplement: only %d verified contacts for %r, fetching Apollo",
                    verified_contacts, company_name,
                )
                imported_count = await _supplement_with_apollo(db, company_id, user_id, company_name)
                contacts_saved += imported_count
                if imported_count > 0 and not _cancel_flags.get(company_id):
                    await _enrich_missing_linkedin(db, company_id, company_name)
                    await _verify_saved_contacts(db, company_id, company_name)
                await db.commit()

        except Exception as exc:
            log.warning("Crawl error for company %s: %s", company_name, exc)
            crawl_errored = True
            await db.rollback()

        finally:
            _cancel_flags.pop(company_id, None)

        if crawl_errored:
            final_status = "failed"
        elif contacts_saved > 0:
            final_status = "enriched"
        else:
            final_status = "partial"

        company2 = (
            await db.execute(
                select(StartupScoutCompany).where(
                    StartupScoutCompany.id == company_id, StartupScoutCompany.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if company2 is not None:
            company2.crawl_status = final_status
            await db.commit()
