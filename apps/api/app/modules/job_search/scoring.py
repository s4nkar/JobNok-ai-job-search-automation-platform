"""Provider-agnostic matching + scoring - runs identically over raw listings
regardless of which provider (or the DB cache) produced them."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from app.ai.llm import provider as ai_provider
from app.core.config import settings
from app.services.cache import cached_prompt_parse

# Per-provider quality/trust weighting, added to every listing from that
# provider - e.g. a government job board's postings might be worth trusting
# more than an aggregator's. Single-provider today, so this is a flat bonus;
# extend this map as providers are added rather than re-deriving weights
# elsewhere.
_PROVIDER_QUALITY_BONUS: dict[str, float] = {
    "adzuna": 2.0,
}
_DEFAULT_PROVIDER_QUALITY_BONUS = 1.5


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def tokenize(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 1]


def _dedupe_preferences(preferences: dict[str, Any]) -> dict[str, Any]:
    """Strip anything from keywords that's already shown elsewhere (as a
    language or the company stage). A term can legitimately belong to both -
    "english" is genuinely a keyword-ish concept and a language, "seed" is
    genuinely a keyword and a company stage - but the frontend renders
    keywords/languages/company_stage as separate pill lists with no
    cross-field dedup, so showing the same term twice reads as a bug, not a
    feature. Applied uniformly to both the LLM and heuristic-fallback paths,
    since the fallback (a plain tokenize() of the prompt) has the identical
    overlap risk - e.g. it'll put "english" in both keywords and languages
    just as easily as the LLM would.
    """
    exclude = set(preferences["languages"])
    if preferences["company_stage"]:
        exclude.add(preferences["company_stage"])
    preferences["keywords"] = [kw for kw in preferences["keywords"] if kw not in exclude]
    return preferences


async def parse_preferences_prompt(prompt: str | None) -> dict[str, Any]:
    if not prompt or not prompt.strip():
        return {"keywords": [], "languages": [], "company_stage": None, "notes": []}

    async def _parse() -> dict[str, Any]:
        system = """You extract structured job search preferences.
Return JSON only with this shape:
{
  "keywords": [string],
  "languages": [string],
  "company_stage": string | null,
  "notes": [string]
}
Keep values short and normalized."""

        try:
            text = await ai_provider.generate_text(prompt.strip(), system=system, max_tokens=250, tier="light")
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                return _dedupe_preferences({
                    "keywords": [str(v).strip().lower() for v in data.get("keywords", []) if str(v).strip()],
                    "languages": [str(v).strip().lower() for v in data.get("languages", []) if str(v).strip()],
                    "company_stage": (str(data.get("company_stage")).strip().lower() if data.get("company_stage") else None),
                    "notes": [str(v).strip() for v in data.get("notes", []) if str(v).strip()],
                })
        except Exception:
            pass

        return _dedupe_preferences({
            "keywords": tokenize(prompt),
            "languages": ["english"] if "english" in prompt.lower() else [],
            "company_stage": None,
            "notes": [],
        })

    return await cached_prompt_parse(
        "job_search_preferences", prompt.strip(), settings.prompt_parse_cache_ttl_seconds, _parse
    )


def score_all(
    raw_jobs: list[dict[str, Any]],
    payload: dict[str, Any],
    preferences: dict[str, Any],
    user_applications: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    scored = []
    for job in raw_jobs:
        enriched = _score_job(job, payload, preferences, user_applications)
        if enriched is not None:
            scored.append(enriched)
    return scored


def _score_job(
    job: dict[str, Any],
    payload: dict[str, Any],
    preferences: dict[str, Any],
    user_applications: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    query = payload["query"]
    location = payload["location"]
    country = (payload.get("country") or "").strip().lower()
    cutoff_hours = payload.get("posted_within_hours")
    remote_only = bool(payload.get("remote_only"))

    title_text = f'{job["role"]} {job["company"]} {job.get("description_text", "")}'
    role_and_company_tokens = set(tokenize(f'{job["role"]} {job["company"]}'))
    query_tokens = tokenize(query)
    # Gate on role+company only, not the full description, AND on whole
    # tokens, not substrings. Two separate false-positive sources fixed here:
    # (1) a stray keyword match anywhere in a long description (especially
    # Arbeitnow's full, untruncated text vs. Adzuna's ~500-char excerpt) let
    # clearly unrelated postings through, e.g. "Lead Product Designer"
    # matching an "AI/ML Engineer" search because "AI" appeared once in an
    # unrelated paragraph; (2) a plain substring check let a query token
    # match *inside* an unrelated word - e.g. token "ml" matching inside
    # company name "VML", not because the job has anything to do with ML.
    # Description matches still count toward the score below via the full
    # title_text - this only tightens the initial pass.
    if query_tokens and not (set(query_tokens) & role_and_company_tokens):
        return None

    location_text = normalize_text(job["location"])
    location_requested = normalize_text(location)
    metadata = job.get("metadata") or {}
    # `metadata.get("country", "")` only falls back to "" when the key is
    # missing - a provider that explicitly writes {"country": None} (e.g.
    # Arbeitnow, which has no country field to report) gets None back, which
    # str()'d and normalized becomes the literal text "none" - a value that
    # then satisfied neither `== country` nor most substring checks, so a
    # country filter silently rejected almost every result from that
    # provider. `or ""` collapses both "missing" and "explicitly None" to
    # the same empty signal.
    metadata_country = normalize_text(str(metadata.get("country") or ""))
    has_country_signal = bool(metadata_country)
    is_remote = "remote" in location_text or bool(metadata.get("remote"))

    if remote_only and not is_remote:
        return None

    # These two gates only reject on a country mismatch when the provider
    # actually told us a country - a provider with no country data at all
    # isn't penalized for that; it just doesn't get the "matched location
    # filter" scoring bonus below, so it still naturally ranks below listings
    # that do confirm a match.
    if location_requested not in {"", "remote"} and location_requested not in location_text:
        if has_country_signal and not (country and country == metadata_country):
            return None

    if country and has_country_signal and country not in location_text and country != metadata_country:
        return None

    posted_at = parse_dt(job.get("posted_at"))
    age_hours = 999999.0
    if posted_at:
        age_hours = max(0.0, (_now_utc() - posted_at).total_seconds() / 3600)
        if cutoff_hours is not None and age_hours > cutoff_hours:
            return None
    elif cutoff_hours is not None:
        return None

    preference_keywords = [kw for kw in preferences.get("keywords", []) if kw]
    preference_languages = [kw for kw in preferences.get("languages", []) if kw]
    company_stage = preferences.get("company_stage")

    evidence: list[str] = []
    score = 0.0

    token_hits = sum(1 for token in query_tokens if token in normalize_text(title_text))
    score += token_hits * 4
    if token_hits:
        evidence.append(f"Matched role keywords: {', '.join(sorted(set(token for token in query_tokens if token in normalize_text(title_text))))}")

    if location_requested and (location_requested in location_text or (location_requested == "remote" and is_remote)):
        score += 3
        evidence.append(f"Matched location filter: {payload['location']}")

    if is_remote:
        score += 1

    if posted_at:
        score += max(0.0, 48 - min(age_hours, 48)) / 6
        evidence.append(f"Posting appears recent: about {int(age_hours)} hours old")

    description_text = normalize_text(job.get("description_text", ""))
    metadata_text = normalize_text(json.dumps(metadata, default=str))
    matched_preference_keywords = [kw for kw in preference_keywords if kw in description_text or kw in metadata_text or kw in location_text]
    if matched_preference_keywords:
        score += len(matched_preference_keywords) * 2
        evidence.append(f"Matched preference keywords: {', '.join(matched_preference_keywords[:4])}")

    if preference_languages:
        source_languages = [normalize_text(str(v)) for v in metadata.get("languages", [])] if isinstance(metadata.get("languages"), list) else []
        matched_languages = [lang for lang in preference_languages if lang in source_languages or lang in description_text]
        if matched_languages:
            score += len(matched_languages) * 1.5
            evidence.append(f"Matched language preference: {', '.join(matched_languages)}")

    if company_stage:
        source_stage = normalize_text(str(metadata.get("stage", "")))
        if company_stage and company_stage in source_stage:
            score += 2
            evidence.append(f"Matched company stage: {metadata.get('stage')}")

    score += _PROVIDER_QUALITY_BONUS.get(job["provider_type"], _DEFAULT_PROVIDER_QUALITY_BONUS)

    canonical_url = job["job_url_canonical"]
    application = user_applications.get(canonical_url)

    citation = {
        "source_name": job["source_name"],
        "canonical_url": canonical_url,
        "job_url": job["job_url"],
        "posted_at": posted_at.isoformat() if posted_at else None,
        "evidence": evidence[:4] or [f"Matched {job['source_name']} listing"],
        "extraction_note": f"Fetched from {job['source_name']} and ranked against your filters.",
    }

    return {
        "source_name": job["source_name"],
        "provider_type": job["provider_type"],
        "external_job_id": job["external_job_id"],
        "company": job["company"],
        "role": job["role"],
        "location": job["location"],
        "job_url": job["job_url"],
        "job_url_canonical": canonical_url,
        "posted_at": posted_at.isoformat() if posted_at else None,
        "applied": bool(application and application.get("application_status") == "applied"),
        "application_status": application.get("application_status") if application else None,
        "tracked_application_id": application.get("id") if application else None,
        "citation": citation,
        "ranking": {"score": round(score, 3), "age_hours": age_hours},
        # Carried through so the frontend can show it and later carry it into
        # resume/cover-letter tools on apply, instead of discarding it after
        # the match decision.
        "description_text": job.get("description_text") or None,
        "salary_min": metadata.get("salary_min"),
        "salary_max": metadata.get("salary_max"),
    }


def score_bonus_job(
    job: dict[str, Any], payload: dict[str, Any], user_applications: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    """Lighter scoring for a provider with no country field (Arbeitnow) -
    title+company relevance and freshness/remote (both real, structured
    Arbeitnow fields) still apply, but deliberately NO location/country
    filtering: without a country signal there's nothing reliable to filter
    on, and pretending otherwise is what caused these results to previously
    either wrongly reject genuine local matches or wrongly admit results
    from anywhere in the world. These are shown separately as unverified-
    location "bonus" finds instead, not merged into the main ranked list -
    no citation/evidence, no score, just enough to render a simple card.
    """
    query = payload["query"]
    role_and_company_tokens = set(tokenize(f'{job["role"]} {job["company"]}'))
    query_tokens = tokenize(query)
    if query_tokens and not (set(query_tokens) & role_and_company_tokens):
        return None

    metadata = job.get("metadata") or {}
    location_text = normalize_text(job["location"])
    is_remote = "remote" in location_text or bool(metadata.get("remote"))
    if bool(payload.get("remote_only")) and not is_remote:
        return None

    cutoff_hours = payload.get("posted_within_hours")
    posted_at = parse_dt(job.get("posted_at"))
    if posted_at:
        age_hours = max(0.0, (_now_utc() - posted_at).total_seconds() / 3600)
        if cutoff_hours is not None and age_hours > cutoff_hours:
            return None
    elif cutoff_hours is not None:
        return None

    canonical_url = job["job_url_canonical"]
    application = user_applications.get(canonical_url)

    return {
        "source_name": job["source_name"],
        "provider_type": job["provider_type"],
        "external_job_id": job["external_job_id"],
        "company": job["company"],
        "role": job["role"],
        "location": job["location"],
        "job_url": job["job_url"],
        "job_url_canonical": canonical_url,
        "posted_at": posted_at.isoformat() if posted_at else None,
        "applied": bool(application and application.get("application_status") == "applied"),
        "application_status": application.get("application_status") if application else None,
        "tracked_application_id": application.get("id") if application else None,
        "description_text": job.get("description_text") or None,
    }
