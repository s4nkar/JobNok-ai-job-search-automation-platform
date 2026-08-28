"""Shared funding-stage vocabulary and detection.

Single source of truth reused by startup_scout's DDG-snippet parsing
(engine.py::_detect_funding_stage/_canonical_stage, kept as thin wrappers
around this module for backward compatibility) and startup_hunt's StartupMap
`keywords` field parsing (discovery/startupmap.py) - both write into the
same company_registry.funding_stage column, so they need one vocabulary,
not two copies that can silently drift apart.
"""

from __future__ import annotations

import re

# Canonical, lowercase-hyphenated form - matches
# startup_scout/schemas.py::_VALID_FUNDING_STAGES exactly. This is what's
# actually stored in company_registry.funding_stage and compared against a
# search request's funding_stages list - display formatting is a separate,
# later step (see display_stage below), never stored.
VALID_STAGES = {"angel", "pre-seed", "seed", "series-a", "series-b", "series-c", "series-d", "series-e"}

_STAGE_ALIASES: dict[str, str] = {
    "angel": "angel",
    "pre-seed": "pre-seed", "pre seed": "pre-seed",
    "seed": "seed",
    "series-a": "series-a", "series a": "series-a",
    "series-b": "series-b", "series b": "series-b",
    "series-c": "series-c", "series c": "series-c",
    "series-c+": "series-c", "series c+": "series-c",
    "series-d": "series-d", "series d": "series-d",
    "series-e": "series-e", "series e": "series-e",
}

# Earliest to latest - used by stages_at_or_below to turn a single ceiling
# selection ("seed") into every stage a search for it should also surface
# ("angel", "pre-seed", "seed") - someone hunting for early-stage companies
# almost always wants everything earlier too, not just an exact-stage match
# that misses a Pre-Seed company purely because it hasn't progressed yet.
STAGE_ORDER: list[str] = ["angel", "pre-seed", "seed", "series-a", "series-b", "series-c", "series-d", "series-e"]

STAGE_DISPLAY: dict[str, str] = {
    "angel": "Angel",
    "pre-seed": "Pre-Seed",
    "seed": "Seed",
    "series-a": "Series A",
    "series-b": "Series B",
    "series-c": "Series C",
    "series-d": "Series D",
    "series-e": "Series E",
}

_STAGE_DETECT_RE = re.compile(
    r"\b(pre[- ]seed|seed|series\s+[abc][\+]?|series[- ][abc][\+]?|angel)\b",
    re.I,
)


def canonical_stage(raw: str) -> str:
    """Normalize an arbitrary stage-ish string to the canonical
    lowercase-hyphenated form, or return it lowercased/unchanged if it's not
    a recognized stage - used to compare an already-detected stage against a
    requested filter list, not for detection from free text (see
    detect_stage below for that)."""
    key = re.sub(r"\s+", " ", raw.strip().lower())
    return _STAGE_ALIASES.get(key, key)


def detect_stage(text: str) -> str | None:
    """Scan free text for the first funding-stage mention (e.g. a DDG
    snippet, or StartupMap's `keywords` field), return the canonical
    lowercase-hyphenated form, or None if no stage is mentioned."""
    m = _STAGE_DETECT_RE.search(text)
    if not m:
        return None
    return canonical_stage(m.group(0))


def stages_at_or_below(ceiling: str) -> list[str]:
    """Expands a single ceiling stage into every canonical stage at or
    before it in STAGE_ORDER. Falls back to a single-element exact-match
    list if `ceiling` isn't a recognized stage - a search still runs, it
    just won't broaden beyond the literal value given."""
    canonical = canonical_stage(ceiling)
    if canonical not in STAGE_ORDER:
        return [canonical]
    return STAGE_ORDER[: STAGE_ORDER.index(canonical) + 1]


def display_stage(canonical: str) -> str:
    """Canonical lowercase-hyphenated form -> Title-Case display form
    ("series-a" -> "Series A"), for showing on a card. Falls back to
    title-casing the raw value if it isn't a recognized canonical stage."""
    return STAGE_DISPLAY.get(canonical, canonical.replace("-", " ").title())


_EMPLOYEE_RANGE_DETECT_RE = re.compile(
    r"\b(1-10|11-50|51-100|101-250|251-500|501-1?000|1[,.]?001-5[,.]?000|5[,.]?001-10[,.]?000)\b"
)


def detect_employee_range(text: str) -> tuple[int | None, int | None]:
    """Scan free text for an employee-count band mention (e.g. "11-50
    employees"), return (min, max), or (None, None) if none found. Shared by
    startup_scout's own snippet parsing (kept as a thin wrapper, see
    engine.py::_detect_employee_range) and the DDG fallback lookup used when
    a crawler-discovered company's own source has no structured employee
    count at all (see startup_hunt/workers/backfill_worker.py)."""
    m = _EMPLOYEE_RANGE_DETECT_RE.search(text)
    if not m:
        return None, None
    return parse_employee_range(m.group(1))


_RANGE_RE = re.compile(r"(\d[\d,.\s]*\d|\d)\s*-\s*(\d[\d,.\s]*\d|\d)")


def parse_employee_range(range_str: str) -> tuple[int | None, int | None]:
    """Parse a "51-200"/"1,001-5,000"/"1.001-5.000" (German thousand-sep)
    style employee-band string into (min, max) integers, or (None, None) if
    it doesn't parse. Shared by both directions: startup_scout's own
    _detect_employee_range output (write-back) and a search request's
    size_range filter bucket (read-side matching) - same string shape
    either way, one parser."""
    if not range_str:
        return None, None
    m = _RANGE_RE.search(range_str)
    if not m:
        return None, None
    try:
        low = int(re.sub(r"[,.\s]", "", m.group(1)))
        high = int(re.sub(r"[,.\s]", "", m.group(2)))
    except ValueError:
        return None, None
    return low, high
