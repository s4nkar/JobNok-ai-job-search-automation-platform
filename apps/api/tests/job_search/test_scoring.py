"""Unit tests for job_search.scoring — deterministic matching/scoring over
raw provider listings, no I/O (parse_preferences_prompt's AI call is mocked
via monkeypatch, and its cache wrapper is bypassed the same way
test_ai_provider.py bypasses Upstash calls — see _bypass_prompt_cache)."""

from datetime import datetime, timezone

import pytest

from app.modules.job_search import scoring

_FIXED_NOW = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _fixed_now(monkeypatch):
    """Pins scoring._now_utc so posting-age math is deterministic instead of
    depending on wall-clock time at test-run time."""
    monkeypatch.setattr(scoring, "_now_utc", lambda: _FIXED_NOW)


def _raw_job(**overrides):
    job = {
        "source_name": "Adzuna",
        "provider_type": "adzuna",
        "external_job_id": "123",
        "company": "Acme Corp",
        "role": "Backend Engineer",
        "location": "Berlin, Germany",
        "job_url": "https://example.com/job/123",
        "job_url_canonical": "https://example.com/job/123",
        "posted_at": "2026-01-10T06:00:00Z",  # 6 hours before _FIXED_NOW
        "description_text": "We are hiring a backend engineer with Python experience.",
        "metadata": {},
    }
    job.update(overrides)
    return job


def _payload(**overrides):
    payload = {
        "query": "backend engineer",
        "location": "Berlin",
        "country": None,
        "posted_within_hours": None,
        "remote_only": False,
        "result_limit": 10,
    }
    payload.update(overrides)
    return payload


_DEFAULT_PREFERENCES = {"keywords": [], "languages": [], "company_stage": None, "notes": []}


def _score_one(job=None, payload=None, preferences=None, user_applications=None):
    scored = scoring.score_all(
        [job or _raw_job()],
        payload or _payload(),
        preferences or _DEFAULT_PREFERENCES,
        user_applications or {},
    )
    return scored[0] if scored else None


# ── normalize_text / tokenize / parse_dt ────────────────────────────────


def test_normalize_text_collapses_whitespace_and_lowercases():
    assert scoring.normalize_text("  Senior   Backend\nEngineer  ") == "senior backend engineer"


def test_tokenize_filters_single_character_tokens_and_lowercases():
    assert scoring.tokenize("AI/ML Engineer at Co.") == ["ai", "ml", "engineer", "at", "co"]


def test_parse_dt_returns_none_for_none_and_empty():
    assert scoring.parse_dt(None) is None
    assert scoring.parse_dt("") is None


def test_parse_dt_handles_z_suffix_as_utc():
    dt = scoring.parse_dt("2026-01-10T06:00:00Z")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == 0
    assert dt.hour == 6


def test_parse_dt_attaches_utc_to_naive_datetime():
    dt = scoring.parse_dt("2026-01-10T06:00:00")
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == 0


def test_parse_dt_returns_none_for_invalid_string():
    assert scoring.parse_dt("not-a-date") is None


# ── score_all / _score_job gating ───────────────────────────────────────


def test_score_all_rejects_job_with_no_overlap_between_query_and_role_or_company():
    job = _raw_job(role="Data Scientist", company="Beta Inc")
    payload = _payload(query="backend engineer")
    assert scoring.score_all([job], payload, _DEFAULT_PREFERENCES, {}) == []


def test_score_all_matches_query_token_against_company_name_alone():
    job = _raw_job(role="Platform Specialist", company="Acme Corp")
    payload = _payload(query="acme")
    result = _score_one(job, payload)
    assert result is not None


def test_score_all_remote_only_rejects_non_remote_job():
    job = _raw_job(location="Berlin, Germany", metadata={})
    payload = _payload(remote_only=True)
    assert _score_one(job, payload) is None


def test_score_all_remote_only_accepts_job_with_remote_metadata_flag():
    job = _raw_job(location="Berlin, Germany", metadata={"remote": True})
    payload = _payload(remote_only=True)
    assert _score_one(job, payload) is not None


def test_score_all_remote_only_accepts_job_with_remote_in_location_text():
    job = _raw_job(location="Remote - Germany")
    payload = _payload(remote_only=True)
    assert _score_one(job, payload) is not None


def test_score_all_rejects_job_on_country_mismatch_when_metadata_has_country():
    job = _raw_job(location="Berlin, Germany", metadata={"country": "us"})
    payload = _payload(location="Berlin", country="de")
    assert _score_one(job, payload) is None


def test_score_all_accepts_job_when_metadata_country_matches():
    job = _raw_job(location="Berlin, Germany", metadata={"country": "de"})
    payload = _payload(location="Berlin", country="de")
    assert _score_one(job, payload) is not None


def test_score_all_does_not_penalize_missing_country_signal():
    """A provider with no country field at all (metadata has no 'country' key)
    must not be rejected just because the location text doesn't literally
    contain the requested country/location string."""
    job = _raw_job(location="Somewhere Else", metadata={})
    payload = _payload(location="Berlin", country="de")
    assert _score_one(job, payload) is not None


def test_score_all_rejects_job_posted_before_cutoff():
    job = _raw_job(posted_at="2026-01-08T06:00:00Z")  # 54 hours before _FIXED_NOW
    payload = _payload(posted_within_hours=24)
    assert _score_one(job, payload) is None


def test_score_all_rejects_job_with_no_posted_at_when_cutoff_given():
    job = _raw_job(posted_at=None)
    payload = _payload(posted_within_hours=24)
    assert _score_one(job, payload) is None


def test_score_all_accepts_job_with_no_posted_at_when_no_cutoff_given():
    job = _raw_job(posted_at=None)
    payload = _payload(posted_within_hours=None)
    result = _score_one(job, payload)
    assert result is not None
    assert result["ranking"]["age_hours"] == 999999.0


# ── score computation ───────────────────────────────────────────────────


def test_score_all_computes_expected_score_and_evidence():
    job = _raw_job()  # role/company tokens match "backend engineer", posted 6h ago, adzuna
    payload = _payload()
    result = _score_one(job, payload)

    # token_hits(2) * 4 = 8; location bonus = 3; recency = (48-6)/6 = 7;
    # provider quality bonus (adzuna) = 2.0 -> 8 + 3 + 7 + 2.0 = 20.0
    assert result["ranking"]["score"] == 20.0
    assert result["ranking"]["age_hours"] == 6.0
    assert result["citation"]["evidence"] == [
        "Matched role keywords: backend, engineer",
        "Matched location filter: Berlin",
        "Posting appears recent: about 6 hours old",
    ]


def test_score_all_adds_remote_bonus_with_no_evidence_line():
    job = _raw_job(location="Remote - Germany")
    payload = _payload(location="Berlin")
    result = _score_one(job, payload)
    assert not any("remote" in line.lower() for line in result["citation"]["evidence"])
    # location bonus doesn't apply here since "berlin" isn't in "remote - germany",
    # but the +1 remote bonus does, silently.
    assert result["ranking"]["score"] == pytest.approx(8 + 1 + 7 + 2.0)


def test_score_all_adds_preference_keyword_language_and_company_stage_bonuses():
    # query/location/posted_at all blanked out so the only evidence/score
    # contributions left are the preference bonuses + the flat provider
    # quality bonus - the citation's evidence list is capped at 4 entries
    # (see test_score_all_caps_evidence_at_four_entries), so isolating these
    # three here avoids them being silently truncated by unrelated entries.
    job = _raw_job(
        description_text="We need a backend engineer who knows python well.",
        metadata={"languages": ["english"], "stage": "seed series"},
        posted_at=None,
    )
    payload = _payload(query="", location="", posted_within_hours=None)
    preferences = {"keywords": ["python"], "languages": ["english"], "company_stage": "seed", "notes": []}

    result = _score_one(job, payload, preferences)

    assert "Matched preference keywords: python" in result["citation"]["evidence"]
    assert "Matched language preference: english" in result["citation"]["evidence"]
    assert "Matched company stage: seed series" in result["citation"]["evidence"]
    # keyword(2) + language(1.5) + stage(2) + adzuna provider quality bonus(2.0)
    assert result["ranking"]["score"] == pytest.approx(2 + 1.5 + 2 + 2.0)


def test_score_all_caps_evidence_at_four_entries():
    job = _raw_job(
        description_text="We need a backend engineer who knows python and german well.",
        metadata={"languages": ["english", "german"], "stage": "seed series"},
    )
    payload = _payload()
    preferences = {
        "keywords": ["python"],
        "languages": ["english", "german"],
        "company_stage": "seed",
        "notes": [],
    }
    result = _score_one(job, payload, preferences)
    assert len(result["citation"]["evidence"]) == 4
    assert result["citation"]["evidence"][0] == "Matched role keywords: backend, engineer"
    assert result["citation"]["evidence"][1] == "Matched location filter: Berlin"
    assert result["citation"]["evidence"][2] == "Posting appears recent: about 6 hours old"
    assert result["citation"]["evidence"][3] == "Matched preference keywords: python"


def test_score_all_falls_back_to_source_name_evidence_when_nothing_matched():
    job = _raw_job(location="Remote", posted_at=None)
    payload = _payload(query="", location="", posted_within_hours=None)
    result = _score_one(job, payload)
    assert result["citation"]["evidence"] == ["Matched Adzuna listing"]


def test_score_all_applies_default_quality_bonus_for_unlisted_provider():
    # Empty query/location and no posted_at isolate every other scoring term
    # (token match, location match, recency) at zero, leaving only the
    # per-provider quality bonus.
    job = _raw_job(provider_type="bundesagentur", source_name="Bundesagentur", posted_at=None)
    payload = _payload(query="", location="", posted_within_hours=None)
    result = _score_one(job, payload)
    assert result["ranking"]["score"] == scoring._DEFAULT_PROVIDER_QUALITY_BONUS


def test_score_all_marks_applied_from_user_applications_by_canonical_url():
    job = _raw_job(job_url_canonical="https://example.com/job/applied")
    user_applications = {
        "https://example.com/job/applied": {"application_status": "applied", "id": "app-1"},
    }
    result = _score_one(job, user_applications=user_applications)
    assert result["applied"] is True
    assert result["application_status"] == "applied"
    assert result["tracked_application_id"] == "app-1"


def test_score_all_marks_saved_but_not_applied():
    job = _raw_job(job_url_canonical="https://example.com/job/saved")
    user_applications = {
        "https://example.com/job/saved": {"application_status": "saved", "id": "app-2"},
    }
    result = _score_one(job, user_applications=user_applications)
    assert result["applied"] is False
    assert result["application_status"] == "saved"
    assert result["tracked_application_id"] == "app-2"


# ── score_bonus_job ──────────────────────────────────────────────────────


def test_score_bonus_job_skips_location_filtering_entirely():
    """Unlike score_all, score_bonus_job never rejects on country/location —
    only title/company relevance, remote_only, and the posted_within_hours
    cutoff apply."""
    job = _raw_job(location="Anywhere, Nowhere", metadata={})
    payload = _payload(location="Berlin", country="de")
    result = scoring.score_bonus_job(job, payload, {})
    assert result is not None
    assert "ranking" not in result
    assert "citation" not in result


def test_score_bonus_job_rejects_on_query_mismatch():
    job = _raw_job(role="Data Scientist", company="Beta Inc")
    payload = _payload(query="backend engineer")
    assert scoring.score_bonus_job(job, payload, {}) is None


def test_score_bonus_job_respects_remote_only():
    job = _raw_job(location="Berlin, Germany")
    payload = _payload(remote_only=True)
    assert scoring.score_bonus_job(job, payload, {}) is None


def test_score_bonus_job_respects_posted_within_hours_cutoff():
    job = _raw_job(posted_at="2026-01-08T06:00:00Z")
    payload = _payload(posted_within_hours=24)
    assert scoring.score_bonus_job(job, payload, {}) is None


def test_score_bonus_job_marks_applied_from_user_applications():
    job = _raw_job(job_url_canonical="https://example.com/job/applied")
    user_applications = {
        "https://example.com/job/applied": {"application_status": "applied", "id": "app-9"},
    }
    result = scoring.score_bonus_job(job, _payload(), user_applications)
    assert result["applied"] is True
    assert result["tracked_application_id"] == "app-9"


# ── parse_preferences_prompt ─────────────────────────────────────────────


def _bypass_prompt_cache(monkeypatch):
    """Bypasses cached_prompt_parse's Redis round-trip entirely — same reason
    test_ai_provider.py neutralizes circuit_is_open/check_tool_budget: left
    unpatched, a real httpx call to Upstash could hang or desync any provider
    mock in the same test."""

    async def _fake_cached_prompt_parse(namespace, prompt, ttl_seconds, parse_fn):
        return await parse_fn()

    monkeypatch.setattr(scoring, "cached_prompt_parse", _fake_cached_prompt_parse)


async def test_parse_preferences_prompt_returns_defaults_for_empty_prompt(monkeypatch):
    calls = []

    async def fake_generate_text(*args, **kwargs):
        calls.append(args)
        return "{}"

    monkeypatch.setattr(scoring.ai_provider, "generate_text", fake_generate_text)

    result = await scoring.parse_preferences_prompt("   ")
    assert result == {"keywords": [], "languages": [], "company_stage": None, "notes": []}
    assert calls == []  # no AI call made for an empty prompt


async def test_parse_preferences_prompt_parses_llm_json_and_dedupes_keywords(monkeypatch):
    _bypass_prompt_cache(monkeypatch)

    async def fake_generate_text(prompt, system, max_tokens=250, tier="light", reasoning_effort=None):
        return (
            '{"keywords": ["python", "english", "seed"], "languages": ["English"], '
            '"company_stage": "Seed", "notes": ["remote-friendly"]}'
        )

    monkeypatch.setattr(scoring.ai_provider, "generate_text", fake_generate_text)

    result = await scoring.parse_preferences_prompt("Looking for python roles, prefer english-speaking seed startups")

    # "english" and "seed" are excluded from keywords since they also appear
    # as a language / company_stage value.
    assert result["keywords"] == ["python"]
    assert result["languages"] == ["english"]
    assert result["company_stage"] == "seed"
    assert result["notes"] == ["remote-friendly"]


async def test_parse_preferences_prompt_falls_back_to_heuristic_on_ai_failure(monkeypatch):
    _bypass_prompt_cache(monkeypatch)

    async def fake_generate_text(*args, **kwargs):
        raise Exception("provider exhausted")

    monkeypatch.setattr(scoring.ai_provider, "generate_text", fake_generate_text)

    result = await scoring.parse_preferences_prompt("I want english-speaking python roles")

    assert "english" in result["languages"]
    assert result["company_stage"] is None
    assert "python" in result["keywords"]
    # "english" is excluded from keywords because it's already in languages
    assert "english" not in result["keywords"]
