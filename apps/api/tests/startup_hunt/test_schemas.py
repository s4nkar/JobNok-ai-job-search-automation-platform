"""Unit tests for schemas.py's Pydantic validators - boundary validation
for every startup_hunt request body (CLAUDE.md: "Validate: Zod + Pydantic").
Each test targets a specific field_validator's accept/reject boundary."""

import pytest
from pydantic import ValidationError

from app.modules.startup_hunt.schemas import (
    StartupHuntOpportunityCreateRequest,
    StartupHuntOpportunityUpdateRequest,
    StartupHuntSearchRequest,
    StartupHuntSourceIn,
    StartupHuntSourceResolveRequest,
)


# ── StartupHuntSearchRequest ─────────────────────────────────────────────

def test_search_request_rejects_too_short_query():
    with pytest.raises(ValidationError):
        StartupHuntSearchRequest(query="a")


def test_search_request_rejects_too_long_query():
    with pytest.raises(ValidationError):
        StartupHuntSearchRequest(query="x" * 201)


def test_search_request_strips_whitespace_from_query():
    req = StartupHuntSearchRequest(query="  AI Engineer  ")
    assert req.query == "AI Engineer"


def test_search_request_rejects_too_short_location():
    with pytest.raises(ValidationError):
        StartupHuntSearchRequest(query="AI Engineer", location="x")


def test_search_request_rejects_too_long_location():
    with pytest.raises(ValidationError):
        StartupHuntSearchRequest(query="AI Engineer", location="x" * 301)


def test_search_request_country_blank_normalizes_to_none():
    req = StartupHuntSearchRequest(query="AI Engineer", country="   ")
    assert req.country is None


def test_search_request_rejects_too_long_country():
    with pytest.raises(ValidationError):
        StartupHuntSearchRequest(query="AI Engineer", country="x" * 101)


def test_search_request_rejects_too_long_company_stage():
    with pytest.raises(ValidationError):
        StartupHuntSearchRequest(query="AI Engineer", company_stage="x" * 51)


def test_search_request_rejects_too_long_strategy_prompt():
    with pytest.raises(ValidationError):
        StartupHuntSearchRequest(query="AI Engineer", strategy_prompt="x" * 501)


def test_search_request_posted_within_hours_must_be_in_range():
    with pytest.raises(ValidationError):
        StartupHuntSearchRequest(query="AI Engineer", posted_within_hours=0)
    with pytest.raises(ValidationError):
        StartupHuntSearchRequest(query="AI Engineer", posted_within_hours=1441)
    req = StartupHuntSearchRequest(query="AI Engineer", posted_within_hours=24)
    assert req.posted_within_hours == 24


def test_search_request_result_limit_must_be_in_range():
    with pytest.raises(ValidationError):
        StartupHuntSearchRequest(query="AI Engineer", result_limit=0)
    with pytest.raises(ValidationError):
        StartupHuntSearchRequest(query="AI Engineer", result_limit=51)
    req = StartupHuntSearchRequest(query="AI Engineer", result_limit=50)
    assert req.result_limit == 50


def test_search_request_defaults_are_sensible():
    req = StartupHuntSearchRequest(query="AI Engineer")
    assert req.location == "Germany"
    assert req.country == "Germany"
    assert req.include_seeded_sources is False
    assert req.result_limit == 25


# ── StartupHuntOpportunityCreateRequest ──────────────────────────────────

def _create_payload(**overrides) -> dict:
    base = dict(
        company_name="Acme AI",
        role_title="AI Engineer",
        location="Berlin",
        source_name="Greenhouse",
        source_type="greenhouse",
        citation_payload={"source_name": "Greenhouse"},
    )
    base.update(overrides)
    return base


def test_opportunity_create_requires_non_empty_text_fields():
    with pytest.raises(ValidationError):
        StartupHuntOpportunityCreateRequest(**_create_payload(company_name="   "))


def test_opportunity_create_rejects_text_field_over_300_chars():
    with pytest.raises(ValidationError):
        StartupHuntOpportunityCreateRequest(**_create_payload(company_name="x" * 301))


def test_opportunity_create_rejects_invalid_opportunity_kind():
    with pytest.raises(ValidationError):
        StartupHuntOpportunityCreateRequest(**_create_payload(opportunity_kind="internship"))


def test_opportunity_create_accepts_valid_opportunity_kinds():
    for kind in ("job", "outreach_lead"):
        req = StartupHuntOpportunityCreateRequest(**_create_payload(opportunity_kind=kind))
        assert req.opportunity_kind == kind


def test_opportunity_create_rejects_invalid_opportunity_status():
    with pytest.raises(ValidationError):
        StartupHuntOpportunityCreateRequest(**_create_payload(opportunity_status="bogus"))


def test_opportunity_create_accepts_valid_opportunity_statuses():
    for status in ("saved", "applied", "contacted", "skipped"):
        req = StartupHuntOpportunityCreateRequest(**_create_payload(opportunity_status=status))
        assert req.opportunity_status == status


def test_opportunity_create_rejects_invalid_iso_datetime():
    with pytest.raises(ValidationError):
        StartupHuntOpportunityCreateRequest(**_create_payload(posted_at="not-a-date"))


def test_opportunity_create_accepts_zulu_iso_datetime():
    req = StartupHuntOpportunityCreateRequest(**_create_payload(posted_at="2024-05-01T10:00:00Z"))
    assert req.posted_at == "2024-05-01T10:00:00+00:00"


def test_opportunity_create_blank_optional_datetime_becomes_none():
    req = StartupHuntOpportunityCreateRequest(**_create_payload(posted_at="   "))
    assert req.posted_at is None


def test_opportunity_create_nullable_text_field_over_limit_rejected():
    with pytest.raises(ValidationError):
        StartupHuntOpportunityCreateRequest(**_create_payload(country="x" * 301))


def test_opportunity_create_defaults_match_expectations():
    req = StartupHuntOpportunityCreateRequest(**_create_payload())
    assert req.opportunity_kind == "job"
    assert req.opportunity_status == "saved"
    assert req.score_total == 0
    assert req.contacts == []


# ── StartupHuntOpportunityUpdateRequest ──────────────────────────────────

def test_opportunity_update_rejects_invalid_status():
    with pytest.raises(ValidationError):
        StartupHuntOpportunityUpdateRequest(opportunity_status="bogus")


def test_opportunity_update_accepts_valid_status():
    req = StartupHuntOpportunityUpdateRequest(opportunity_status="applied")
    assert req.opportunity_status == "applied"


# ── StartupHuntSourceIn ──────────────────────────────────────────────────

def test_source_in_rejects_disallowed_type():
    with pytest.raises(ValidationError):
        StartupHuntSourceIn(type="myworkdayjobs", name="Acme")


def test_source_in_accepts_allowed_type_case_insensitively():
    req = StartupHuntSourceIn(type="GREENHOUSE", name="Acme")
    assert req.type == "greenhouse"


def test_source_in_rejects_blank_name():
    with pytest.raises(ValidationError):
        StartupHuntSourceIn(type="greenhouse", name="   ")


def test_source_in_rejects_name_over_300_chars():
    with pytest.raises(ValidationError):
        StartupHuntSourceIn(type="greenhouse", name="x" * 301)


def test_source_in_rejects_slug_over_100_chars():
    with pytest.raises(ValidationError):
        StartupHuntSourceIn(type="greenhouse", name="Acme", slug="x" * 101)


def test_source_in_blank_company_normalizes_to_none():
    req = StartupHuntSourceIn(type="greenhouse", name="Acme", company="  ")
    assert req.company is None


# ── StartupHuntSourceResolveRequest ──────────────────────────────────────

def test_source_resolve_request_rejects_too_short_input():
    with pytest.raises(ValidationError):
        StartupHuntSourceResolveRequest(company_input="a")


def test_source_resolve_request_rejects_too_long_input():
    with pytest.raises(ValidationError):
        StartupHuntSourceResolveRequest(company_input="x" * 301)


def test_source_resolve_request_strips_whitespace():
    req = StartupHuntSourceResolveRequest(company_input="  Acme AI  ")
    assert req.company_input == "Acme AI"
