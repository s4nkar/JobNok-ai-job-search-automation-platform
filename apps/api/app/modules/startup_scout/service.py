"""Startup Scout business logic — SQLAlchemy-backed.

_run_crawl runs as a FastAPI BackgroundTask (after the HTTP response is
sent), so it cannot reuse the request-scoped AsyncSession from Depends(get_db)
— it opens its own session via AsyncSessionLocal() and commits incrementally,
mirroring the original supabase-py calls' per-statement auto-commit behavior.
"""

import asyncio
import logging
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.shared.repository import UserScopedRepository
from app.shared.utils import row_to_dict
from app.modules.startup_scout.models import StartupScoutCompany, StartupScoutContact
from app.modules.startup_scout.schemas import SaveCompanyRequest
from app.modules.startup_scout.engine import (
    apollo_search_contacts,
    enrich_linkedin_url,
    verify_contact,
    web_search_contacts,
)

log = logging.getLogger(__name__)

MIN_VERIFIED_CONTACTS = 2

# In-process cancel flags keyed by company_id.
# Set to True by the /stop endpoint; run_crawl checks between each contact save.
_cancel_flags: dict[str, bool] = {}


class CompanyRepository(UserScopedRepository[StartupScoutCompany]):
    model = StartupScoutCompany


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
    obj = await CompanyRepository(db).create(
        user_id,
        name=req.name.strip(),
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
