"""Unit tests for service.py's pure helper functions - the subset of
startup_hunt's business logic that needs no DB session/SQLAlchemy model,
just plain dicts (and a minimal fake Job row for the cache-adapter
helpers). DB-backed functions (create/update/delete/search orchestration)
are out of scope here - they need a live Postgres fixture this repo
doesn't have yet."""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.modules.startup_hunt import service


# ── _parse_dt ────────────────────────────────────────────────────────────

def test_parse_dt_parses_zulu_iso_string():
    dt = service._parse_dt("2024-05-01T10:00:00Z")
    assert dt == datetime(2024, 5, 1, 10, 0, 0, tzinfo=timezone.utc)


def test_parse_dt_none_for_none_input():
    assert service._parse_dt(None) is None


# ── _opportunity_lookup_key ──────────────────────────────────────────────

def test_opportunity_lookup_key_prefers_canonical_url():
    data = {"canonical_job_url": "https://acme.ai/jobs/1", "company_name": "Acme", "role_title": "AI Engineer", "location": "Berlin"}
    assert service._opportunity_lookup_key(data) == "https://acme.ai/jobs/1"


def test_opportunity_lookup_key_falls_back_to_composite_key():
    data = {"canonical_job_url": None, "company_name": "Acme", "role_title": "AI Engineer", "location": "Berlin"}
    assert service._opportunity_lookup_key(data) == "acme|ai engineer|berlin"


def test_opportunity_lookup_key_composite_key_is_case_insensitive():
    data = {"canonical_job_url": "", "company_name": "ACME", "role_title": "Ai Engineer", "location": "BERLIN"}
    assert service._opportunity_lookup_key(data) == "acme|ai engineer|berlin"


# ── _job_row_to_opportunity_dict ─────────────────────────────────────────

def _fake_job_row(**overrides) -> SimpleNamespace:
    base = dict(
        title="AI Engineer",
        company="Acme",
        description="Build ML pipelines",
        source="theirstack",
        location="Berlin, Germany",
        country="Germany",
        apply_url="https://acme.ai/apply",
        canonical_url="https://acme.ai/jobs/1",
        posted_at=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_job_row_to_opportunity_dict_marks_cache_hit_and_job_kind():
    row = _fake_job_row()
    item = service._job_row_to_opportunity_dict(row)
    assert item["cache_hit"] is True
    assert item["opportunity_kind"] == "job"
    assert item["company_name"] == "Acme"
    assert item["direct_apply_url"] == "https://acme.ai/apply"


def test_job_row_to_opportunity_dict_maps_theirstack_source_type_and_label():
    row = _fake_job_row(source="theirstack")
    item = service._job_row_to_opportunity_dict(row)
    assert item["source_type"] == "theirstack_search"
    assert item["source_name"] == "TheirStack"


def test_job_row_to_opportunity_dict_maps_non_theirstack_source_verbatim():
    row = _fake_job_row(source="greenhouse")
    item = service._job_row_to_opportunity_dict(row)
    assert item["source_type"] == "greenhouse"
    assert item["source_name"] == "Greenhouse"


def test_job_row_to_opportunity_dict_builds_raw_text_from_title_company_description():
    row = _fake_job_row(title="AI Engineer", company="Acme", description="Build ML pipelines")
    item = service._job_row_to_opportunity_dict(row)
    assert item["raw_text"] == "AI Engineer Acme Build ML pipelines"


def test_job_row_to_opportunity_dict_handles_missing_description():
    row = _fake_job_row(description=None)
    item = service._job_row_to_opportunity_dict(row)
    assert item["raw_text"] == "AI Engineer Acme"


# ── _opportunity_to_job_cache_row ────────────────────────────────────────

def _opportunity_item(**overrides) -> dict:
    base = dict(
        canonical_job_url="https://acme.ai/jobs/1",
        direct_apply_url="https://acme.ai/apply",
        portal_job_url=None,
        posted_at=None,
        country="Germany",
        source_type="theirstack_search",
        role_title="AI Engineer",
        company_name="Acme",
        location="Berlin",
        description_text="Build ML pipelines",
        raw_text="AI Engineer Acme Build ML pipelines",
    )
    base.update(overrides)
    return base


def test_opportunity_to_job_cache_row_none_when_no_canonical_url():
    assert service._opportunity_to_job_cache_row(_opportunity_item(canonical_job_url=None, direct_apply_url=None, portal_job_url=None)) is None


def test_opportunity_to_job_cache_row_maps_theirstack_search_to_theirstack_provider():
    row = service._opportunity_to_job_cache_row(_opportunity_item(source_type="theirstack_search"))
    assert row["provider_type"] == "theirstack"
    assert row["external_job_id"] == "https://acme.ai/jobs/1"
    assert row["job_url"] == "https://acme.ai/apply"


def test_opportunity_to_job_cache_row_falls_back_to_portal_url_for_apply_url():
    row = service._opportunity_to_job_cache_row(
        _opportunity_item(direct_apply_url=None, portal_job_url="https://acme.ai/portal")
    )
    assert row["job_url"] == "https://acme.ai/portal"


def test_opportunity_to_job_cache_row_truncates_description_to_2000_chars():
    long_text = "x" * 5000
    row = service._opportunity_to_job_cache_row(_opportunity_item(description_text=long_text))
    assert len(row["description_text"]) == 2000


# ── _normalize_scores_to_top_result ──────────────────────────────────────

def test_normalize_scores_to_top_result_scales_relative_to_max():
    results = [{"score_total": 10.0}]
    overflow = [{"score_total": 5.0}]
    service._normalize_scores_to_top_result(results, overflow)
    assert results[0]["score_total"] == 100.0
    assert overflow[0]["score_total"] == 50.0


def test_normalize_scores_to_top_result_zeroes_out_when_max_is_non_positive():
    results = [{"score_total": -3.0}, {"score_total": 0.0}]
    service._normalize_scores_to_top_result(results)
    assert all(item["score_total"] == 0.0 for item in results)


def test_normalize_scores_to_top_result_no_op_on_empty_lists():
    # Must not raise on an empty combined input.
    service._normalize_scores_to_top_result([], [])


# ── _response_cache_key ──────────────────────────────────────────────────

def test_response_cache_key_is_stable_regardless_of_key_order():
    key1 = service._response_cache_key({"query": "AI Engineer", "location": "Berlin"})
    key2 = service._response_cache_key({"location": "Berlin", "query": "AI Engineer"})
    assert key1 == key2
    assert key1.startswith("startup_hunt:")


def test_response_cache_key_differs_for_different_payloads():
    key1 = service._response_cache_key({"query": "AI Engineer"})
    key2 = service._response_cache_key({"query": "ML Engineer"})
    assert key1 != key2


# ── _strip_personalized_fields / _reattach_saved_state ───────────────────

def test_strip_personalized_fields_blanks_saved_state():
    response = {
        "results": [{"saved": True, "saved_status": "applied", "saved_opportunity_id": "123", "role_title": "AI Engineer"}],
        "overflow_results": [{"saved": True, "saved_status": "saved", "saved_opportunity_id": "456"}],
    }
    stripped = service._strip_personalized_fields(response)
    assert stripped["results"][0]["saved"] is False
    assert stripped["results"][0]["saved_status"] is None
    assert stripped["results"][0]["role_title"] == "AI Engineer"
    assert stripped["overflow_results"][0]["saved_opportunity_id"] is None
    # original response dict must be untouched (shallow copy, not mutation)
    assert response["results"][0]["saved"] is True


def test_reattach_saved_state_applies_current_users_existing_map():
    response = {
        "results": [{"canonical_job_url": "https://acme.ai/jobs/1", "company_name": "Acme", "role_title": "AI Engineer", "location": "Berlin"}],
        "overflow_results": [],
    }
    existing = {"https://acme.ai/jobs/1": {"opportunity_status": "contacted", "id": "abc"}}
    service._reattach_saved_state(response, existing)
    assert response["results"][0]["saved"] is True
    assert response["results"][0]["saved_status"] == "contacted"
    assert response["results"][0]["saved_opportunity_id"] == "abc"


def test_reattach_saved_state_marks_unsaved_when_no_match():
    response = {"results": [{"canonical_job_url": "https://other.ai/jobs/1"}], "overflow_results": []}
    service._reattach_saved_state(response, {})
    assert response["results"][0]["saved"] is False
    assert response["results"][0]["saved_status"] is None


# ── _url_fields ────────────────────────────────────────────────────────

def test_url_fields_derives_canonical_url_from_direct_apply_when_missing():
    payload = {"direct_apply_url": "https://acme.ai/jobs/1?utm_source=x", "canonical_job_url": None}
    fields = service._url_fields(payload)
    assert fields["canonical_job_url"] == "https://acme.ai/jobs/1"


def test_url_fields_prefers_explicit_canonical_url_when_present():
    payload = {"direct_apply_url": "https://acme.ai/jobs/1", "canonical_job_url": "https://acme.ai/jobs/1-canonical"}
    fields = service._url_fields(payload)
    assert fields["canonical_job_url"] == "https://acme.ai/jobs/1-canonical"


def test_url_fields_all_none_when_payload_has_no_urls():
    fields = service._url_fields({})
    assert fields == {
        "direct_apply_url": None,
        "canonical_job_url": None,
        "portal_job_url": None,
        "company_website_url": None,
        "company_careers_url": None,
    }
