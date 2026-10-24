"""Unit tests for job_search.schemas — Pydantic request validators, focused
on the custom field_validator logic (length bounds, enum checks, JSON-size
DoS guard, ISO-datetime parsing)."""

import json

import pytest
from pydantic import ValidationError

from app.modules.job_search.schemas import (
    JobSearchApplicationCreateRequest,
    JobSearchApplicationUpdateRequest,
    JobSearchRequest,
    _MAX_JSON_FIELD_BYTES,
)


# ── JobSearchRequest ─────────────────────────────────────────────────────


def test_job_search_request_accepts_minimal_valid_payload():
    req = JobSearchRequest(query="backend engineer", location="Berlin")
    assert req.query == "backend engineer"
    assert req.posted_within_hours == 24
    assert req.result_limit == 10
    assert req.remote_only is False


@pytest.mark.parametrize("field", ["query", "location"])
def test_job_search_request_rejects_text_shorter_than_two_chars(field):
    kwargs = {"query": "backend engineer", "location": "Berlin"}
    kwargs[field] = "a"
    with pytest.raises(ValidationError):
        JobSearchRequest(**kwargs)


@pytest.mark.parametrize("field", ["query", "location"])
def test_job_search_request_rejects_text_longer_than_two_hundred_chars(field):
    kwargs = {"query": "backend engineer", "location": "Berlin"}
    kwargs[field] = "a" * 201
    with pytest.raises(ValidationError):
        JobSearchRequest(**kwargs)


def test_job_search_request_strips_whitespace_from_query_and_location():
    req = JobSearchRequest(query="  backend engineer  ", location="  Berlin  ")
    assert req.query == "backend engineer"
    assert req.location == "Berlin"


def test_job_search_request_normalizes_country_whitespace_and_keeps_none():
    assert JobSearchRequest(query="backend engineer", location="Berlin", country="  DE  ").country == "DE"
    assert JobSearchRequest(query="backend engineer", location="Berlin", country=None).country is None


@pytest.mark.parametrize("value", [0, 721, -1])
def test_job_search_request_rejects_posted_within_hours_out_of_bounds(value):
    with pytest.raises(ValidationError):
        JobSearchRequest(query="backend engineer", location="Berlin", posted_within_hours=value)


@pytest.mark.parametrize("value", [1, 720])
def test_job_search_request_accepts_posted_within_hours_at_boundaries(value):
    req = JobSearchRequest(query="backend engineer", location="Berlin", posted_within_hours=value)
    assert req.posted_within_hours == value


@pytest.mark.parametrize("value", [0, 51, -1])
def test_job_search_request_rejects_result_limit_out_of_bounds(value):
    with pytest.raises(ValidationError):
        JobSearchRequest(query="backend engineer", location="Berlin", result_limit=value)


@pytest.mark.parametrize("value", [1, 50])
def test_job_search_request_accepts_result_limit_at_boundaries(value):
    req = JobSearchRequest(query="backend engineer", location="Berlin", result_limit=value)
    assert req.result_limit == value


def test_job_search_request_rejects_preferences_prompt_over_five_hundred_chars():
    with pytest.raises(ValidationError):
        JobSearchRequest(query="backend engineer", location="Berlin", preferences_prompt="a" * 501)


def test_job_search_request_blank_preferences_prompt_becomes_none():
    req = JobSearchRequest(query="backend engineer", location="Berlin", preferences_prompt="   ")
    assert req.preferences_prompt is None


# ── JobSearchApplicationCreateRequest ───────────────────────────────────


def _create_kwargs(**overrides):
    kwargs = dict(
        job_url="https://example.com/job/1",
        source_name="Adzuna",
        company="Acme Corp",
        role="Backend Engineer",
        location="Berlin, Germany",
        citation_payload={"evidence": ["Matched listing"]},
    )
    kwargs.update(overrides)
    return kwargs


def test_job_search_application_create_accepts_minimal_valid_payload():
    req = JobSearchApplicationCreateRequest(**_create_kwargs())
    assert req.application_status == "applied"
    assert req.search_context == {}


@pytest.mark.parametrize("field", ["source_name", "company", "role", "location"])
def test_job_search_application_create_rejects_blank_required_text_fields(field):
    with pytest.raises(ValidationError):
        JobSearchApplicationCreateRequest(**_create_kwargs(**{field: "   "}))


@pytest.mark.parametrize("field", ["source_name", "company", "role", "location"])
def test_job_search_application_create_rejects_required_text_over_three_hundred_chars(field):
    with pytest.raises(ValidationError):
        JobSearchApplicationCreateRequest(**_create_kwargs(**{field: "a" * 301}))


def test_job_search_application_create_rejects_job_description_over_limit():
    with pytest.raises(ValidationError):
        JobSearchApplicationCreateRequest(**_create_kwargs(job_description="a" * 20_001))


def test_job_search_application_create_blank_job_description_becomes_none():
    req = JobSearchApplicationCreateRequest(**_create_kwargs(job_description="   "))
    assert req.job_description is None


def test_job_search_application_create_rejects_external_job_id_over_limit():
    with pytest.raises(ValidationError):
        JobSearchApplicationCreateRequest(**_create_kwargs(external_job_id="a" * 301))


def test_job_search_application_create_rejects_oversized_citation_payload():
    oversized = {"evidence": ["x" * _MAX_JSON_FIELD_BYTES]}
    assert len(json.dumps(oversized)) > _MAX_JSON_FIELD_BYTES
    with pytest.raises(ValidationError):
        JobSearchApplicationCreateRequest(**_create_kwargs(citation_payload=oversized))


def test_job_search_application_create_rejects_oversized_search_context():
    oversized = {"notes": ["x" * _MAX_JSON_FIELD_BYTES]}
    with pytest.raises(ValidationError):
        JobSearchApplicationCreateRequest(**_create_kwargs(search_context=oversized))


@pytest.mark.parametrize("status", ["saved", "applied", "skipped"])
def test_job_search_application_create_accepts_valid_statuses(status):
    req = JobSearchApplicationCreateRequest(**_create_kwargs(application_status=status))
    assert req.application_status == status


def test_job_search_application_create_rejects_invalid_status():
    with pytest.raises(ValidationError):
        JobSearchApplicationCreateRequest(**_create_kwargs(application_status="pending"))


def test_job_search_application_create_accepts_valid_iso_datetime_with_z_suffix():
    req = JobSearchApplicationCreateRequest(**_create_kwargs(posted_at="2026-01-10T06:00:00Z"))
    assert req.posted_at == "2026-01-10T06:00:00+00:00"


def test_job_search_application_create_rejects_invalid_datetime_string():
    with pytest.raises(ValidationError):
        JobSearchApplicationCreateRequest(**_create_kwargs(applied_at="not-a-date"))


def test_job_search_application_create_blank_datetime_becomes_none():
    req = JobSearchApplicationCreateRequest(**_create_kwargs(posted_at="  "))
    assert req.posted_at is None


# ── JobSearchApplicationUpdateRequest ───────────────────────────────────


@pytest.mark.parametrize("status", ["saved", "applied", "skipped"])
def test_job_search_application_update_accepts_valid_statuses(status):
    req = JobSearchApplicationUpdateRequest(application_status=status)
    assert req.application_status == status


def test_job_search_application_update_rejects_invalid_status():
    with pytest.raises(ValidationError):
        JobSearchApplicationUpdateRequest(application_status="pending")


def test_job_search_application_update_rejects_invalid_applied_at():
    with pytest.raises(ValidationError):
        JobSearchApplicationUpdateRequest(application_status="applied", applied_at="not-a-date")


def test_job_search_application_update_blank_applied_at_becomes_none():
    req = JobSearchApplicationUpdateRequest(application_status="saved", applied_at="  ")
    assert req.applied_at is None
