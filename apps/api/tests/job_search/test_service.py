"""Unit tests for job_search.service — limited to pure helpers and helpers
whose only I/O is a trivially-fakeable AsyncSession/Redis call. search_recent_jobs,
_fetch_db_candidates, _upsert_jobs_cache, _fetch_provider_safe, _fetch_bonus_jobs,
and the create/update/delete/list/get CRUD functions all need a real DB session
(no fixture exists for one yet in this repo) or real provider network calls —
left untested here, see the test-writer's final report."""

import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.modules.job_search import service
from app.modules.job_search.models import Job


# ── _parse_dt ────────────────────────────────────────────────────────────


def test_parse_dt_returns_none_for_none():
    assert service._parse_dt(None) is None


def test_parse_dt_parses_z_suffix_as_utc():
    dt = service._parse_dt("2026-01-10T06:00:00Z")
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == 0


# ── _response_cache_key ──────────────────────────────────────────────────


def _payload(**overrides):
    payload = {
        "query": "backend engineer",
        "location": "Berlin",
        "country": None,
        "posted_within_hours": 24,
        "remote_only": False,
        "result_limit": 10,
    }
    payload.update(overrides)
    return payload


def test_response_cache_key_is_case_and_whitespace_insensitive():
    key1 = service._response_cache_key(_payload(query="Backend Engineer", country="DE"))
    key2 = service._response_cache_key(_payload(query=" backend engineer ", country="de"))
    assert key1 == key2


def test_response_cache_key_differs_for_different_query():
    key1 = service._response_cache_key(_payload(query="backend engineer"))
    key2 = service._response_cache_key(_payload(query="frontend engineer"))
    assert key1 != key2


def test_response_cache_key_is_not_namespaced_per_provider():
    assert service._response_cache_key(_payload()).startswith("job_search:")


# ── _job_row_to_raw_dict ──────────────────────────────────────────────────


def test_job_row_to_raw_dict_maps_adzuna_source_name_and_converts_decimal_salary():
    row = Job(
        source="adzuna",
        source_job_id="abc123",
        title="Backend Engineer",
        company="Acme Corp",
        location="Berlin, Germany",
        country="de",
        description="A great job.",
        salary_min=Decimal("50000"),
        salary_max=Decimal("80000"),
        category="it",
        apply_url="https://example.com/apply",
        canonical_url="https://example.com/job",
        posted_at=None,
    )

    result = service._job_row_to_raw_dict(row)

    assert result["source_name"] == "Adzuna"
    assert result["provider_type"] == "adzuna"
    assert result["role"] == "Backend Engineer"
    assert result["metadata"]["salary_min"] == 50000.0
    assert isinstance(result["metadata"]["salary_min"], float)
    assert result["metadata"]["country"] == "de"
    assert result["posted_at"] is None


def test_job_row_to_raw_dict_titlecases_unlisted_source_name():
    row = Job(
        source="bundesagentur",
        source_job_id="x",
        title="Role",
        company="Co",
        location="Loc",
        apply_url="https://example.com/apply",
        canonical_url="https://example.com/job",
    )

    result = service._job_row_to_raw_dict(row)

    assert result["source_name"] == "Bundesagentur"


def test_job_row_to_raw_dict_defaults_missing_description_to_empty_string():
    row = Job(
        source="adzuna",
        source_job_id="x",
        title="Role",
        company="Co",
        location="Loc",
        apply_url="https://example.com/apply",
        canonical_url="https://example.com/job",
    )

    result = service._job_row_to_raw_dict(row)

    assert result["description_text"] == ""


def test_job_row_to_raw_dict_leaves_salary_none_when_unset():
    row = Job(
        source="adzuna",
        source_job_id="x",
        title="Role",
        company="Co",
        location="Loc",
        apply_url="https://example.com/apply",
        canonical_url="https://example.com/job",
    )

    result = service._job_row_to_raw_dict(row)

    assert result["metadata"]["salary_min"] is None
    assert result["metadata"]["salary_max"] is None


# ── _check_rate_limit_fail_open ───────────────────────────────────────────


async def test_check_rate_limit_fail_open_raises_429_on_burst_limit_exceeded(monkeypatch):
    async def fake_burst(*args, **kwargs):
        return False

    monkeypatch.setattr(service, "check_burst_limit", fake_burst)

    with pytest.raises(HTTPException) as exc_info:
        await service._check_rate_limit_fail_open("user-1")
    assert exc_info.value.status_code == 429


async def test_check_rate_limit_fail_open_raises_429_on_daily_limit_exceeded(monkeypatch):
    async def fake_burst(*args, **kwargs):
        return True

    async def fake_daily(*args, **kwargs):
        return False, 0

    monkeypatch.setattr(service, "check_burst_limit", fake_burst)
    monkeypatch.setattr(service, "check_rate_limit", fake_daily)

    with pytest.raises(HTTPException) as exc_info:
        await service._check_rate_limit_fail_open("user-1")
    assert exc_info.value.status_code == 429
    assert str(settings.rate_limit_job_search_per_day) in exc_info.value.detail


async def test_check_rate_limit_fail_open_returns_remaining_when_allowed(monkeypatch):
    async def fake_burst(*args, **kwargs):
        return True

    async def fake_daily(*args, **kwargs):
        return True, 7

    monkeypatch.setattr(service, "check_burst_limit", fake_burst)
    monkeypatch.setattr(service, "check_rate_limit", fake_daily)

    remaining = await service._check_rate_limit_fail_open("user-1")
    assert remaining == 7


async def test_check_rate_limit_fail_open_fails_open_to_none_when_daily_check_errors(monkeypatch):
    async def fake_burst(*args, **kwargs):
        return True

    async def fake_daily(*args, **kwargs):
        raise Exception("redis down")

    monkeypatch.setattr(service, "check_burst_limit", fake_burst)
    monkeypatch.setattr(service, "check_rate_limit", fake_daily)

    assert await service._check_rate_limit_fail_open("user-1") is None


async def test_check_rate_limit_fail_open_treats_burst_error_as_ok(monkeypatch):
    async def fake_burst(*args, **kwargs):
        raise Exception("redis down")

    async def fake_daily(*args, **kwargs):
        return True, 3

    monkeypatch.setattr(service, "check_burst_limit", fake_burst)
    monkeypatch.setattr(service, "check_rate_limit", fake_daily)

    assert await service._check_rate_limit_fail_open("user-1") == 3


# ── _check_applications_rate_limit_fail_open ──────────────────────────────


async def test_check_applications_rate_limit_fail_open_raises_429_when_exceeded(monkeypatch):
    async def fake_daily(*args, **kwargs):
        return False, 0

    monkeypatch.setattr(service, "check_rate_limit", fake_daily)

    with pytest.raises(HTTPException) as exc_info:
        await service._check_applications_rate_limit_fail_open("user-1")
    assert exc_info.value.status_code == 429


async def test_check_applications_rate_limit_fail_open_is_noop_when_allowed(monkeypatch):
    async def fake_daily(*args, **kwargs):
        return True, 5

    monkeypatch.setattr(service, "check_rate_limit", fake_daily)

    await service._check_applications_rate_limit_fail_open("user-1")  # must not raise


async def test_check_applications_rate_limit_fail_open_fails_open_on_redis_error(monkeypatch):
    async def fake_daily(*args, **kwargs):
        raise Exception("redis down")

    monkeypatch.setattr(service, "check_rate_limit", fake_daily)

    await service._check_applications_rate_limit_fail_open("user-1")  # must not raise


# ── _find_job_id ─────────────────────────────────────────────────────────


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, _stmt):
        return _FakeResult(self._results.pop(0))


async def test_find_job_id_returns_id_from_external_job_id_lookup():
    job_id = uuid.uuid4()
    db = _FakeDB([job_id])

    result = await service._find_job_id(
        db, source_name="Adzuna", external_job_id="123", job_url_canonical="https://example.com/job"
    )
    assert result == str(job_id)


async def test_find_job_id_falls_back_to_canonical_url_when_external_id_lookup_misses():
    job_id = uuid.uuid4()
    db = _FakeDB([None, job_id])  # first (external_job_id) lookup misses, second (canonical) hits

    result = await service._find_job_id(
        db, source_name="Adzuna", external_job_id="123", job_url_canonical="https://example.com/job"
    )
    assert result == str(job_id)


async def test_find_job_id_skips_external_id_lookup_when_none_given():
    db = _FakeDB([None])  # only the canonical-url lookup should run

    result = await service._find_job_id(
        db, source_name="Adzuna", external_job_id=None, job_url_canonical="https://example.com/job"
    )
    assert result is None
