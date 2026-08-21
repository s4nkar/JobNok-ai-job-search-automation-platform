"""Cross-provider dedup + ranking.

A single-fingerprint approach (canonical URL, falling back to company+role+
location) is enough when there's one provider, but breaks once there's more
than one: each provider hands out its own redirect/tracking URL for the same
real-world posting, so two providers listing the identical job never share a
canonical URL. This mirrors startup_hunt's proven fix for the same problem
(engine.py's _dedupe_opportunities) - a union-find over multiple fingerprint
keys per item, so a job matched via one provider's URL and another's
semantic (company+role+location) key still merges into one group.
"""

from __future__ import annotations

from typing import Any

from app.modules.job_search.scoring import normalize_text

# Stripped before comparing roles across providers, so "Senior Software
# Engineer" and "Software Engineer" for the same real opening still match -
# mirrors startup_hunt's _normalize_role_for_dedupe seniority stopword list.
_ROLE_NOISE_WORDS = {
    "senior", "sr", "staff", "principal", "lead", "junior", "jr",
    "intern", "internship", "associate", "entry", "level",
}


def _normalize_role(role: str) -> str:
    words = [w for w in normalize_text(role).split(" ") if w and w not in _ROLE_NOISE_WORDS]
    return " ".join(words)



# Placeholder values providers fall back to when they have no real company
# name (e.g. an agency posting hides the client). Genuinely different
# postings can both land on the same placeholder, so it must never feed the
# semantic dedup key - that would merge unrelated jobs just because neither
# provider told us who's hiring.
_GENERIC_COMPANY_NAMES = {"unknown company", "confidential", "private employer", "n/a"}


def _dedupe_keys(item: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    canonical = item.get("job_url_canonical")
    if canonical:
        keys.append(f"url:{canonical}")

    company_key = normalize_text(item.get("company", ""))
    role_key = _normalize_role(item.get("role", ""))
    location_key = normalize_text(item.get("location", ""))
    if company_key and role_key and company_key not in _GENERIC_COMPANY_NAMES:
        keys.append(f"semantic:{company_key}|{role_key}|{location_key}")

    return keys


def _merge_group(group: list[dict[str, Any]]) -> dict[str, Any]:
    if len(group) == 1:
        return group[0]

    primary = max(group, key=lambda item: item["ranking"]["score"])
    for other in group:
        if other is primary:
            continue
        # A duplicate the user already applied to shouldn't lose that status
        # just because a different provider's copy happened to score higher.
        if not primary.get("applied") and other.get("applied"):
            primary["applied"] = other["applied"]
            primary["application_status"] = other["application_status"]
            primary["tracked_application_id"] = other["tracked_application_id"]
        if not primary.get("description_text") and other.get("description_text"):
            primary["description_text"] = other["description_text"]
        if primary.get("salary_min") is None and other.get("salary_min") is not None:
            primary["salary_min"] = other["salary_min"]
        if primary.get("salary_max") is None and other.get("salary_max") is not None:
            primary["salary_max"] = other["salary_max"]

        primary_evidence = primary["citation"].get("evidence", [])
        other_evidence = other["citation"].get("evidence", [])
        primary["citation"]["evidence"] = list(dict.fromkeys(primary_evidence + other_evidence))[:4]

    return primary


def dedupe_and_rank(scored_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[list[dict[str, Any]]] = []
    key_to_group: dict[str, int] = {}

    for item in scored_jobs:
        keys = _dedupe_keys(item)
        matched_indexes = sorted({key_to_group[k] for k in keys if k in key_to_group})

        if not matched_indexes:
            group_index = len(groups)
            groups.append([item])
        else:
            group_index = matched_indexes[0]
            groups[group_index].append(item)
            # The item's keys bridge two previously-separate groups (e.g. one
            # provider's item matched group A by URL, another's matched group
            # B by semantic key) - merge them into one.
            for other_index in matched_indexes[1:]:
                groups[group_index].extend(groups[other_index])
                groups[other_index] = []

        for key in keys:
            key_to_group[key] = group_index

    merged = [_merge_group(group) for group in groups if group]
    merged.sort(key=lambda item: (-item["ranking"]["score"], item["ranking"]["age_hours"]))
    return merged
