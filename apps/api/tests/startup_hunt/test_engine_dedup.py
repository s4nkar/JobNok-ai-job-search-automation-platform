"""Unit tests for engine.py's opportunity dedupe/merge pipeline - pure
functions of input data, mirroring resume_tailor's matcher test style."""

from app.modules.startup_hunt import engine


def _opportunity(**overrides) -> dict:
    base = {
        "company_name": "Acme AI",
        "company_domain": "acme.ai",
        "company_website_url": "https://acme.ai",
        "company_careers_url": None,
        "role_title": "AI Engineer",
        "location": "Berlin, Germany",
        "country": "Germany",
        "source_name": "Greenhouse",
        "source_type": "greenhouse",
        "direct_apply_url": None,
        "canonical_job_url": "https://acme.ai/jobs/1",
        "portal_job_url": None,
        "posted_at": None,
        "opportunity_kind": "job",
        "score_total": 10.0,
        "score_labels": ["Direct Apply"],
        "score_reasons": ["Matched role keywords: ai"],
        "citation": {"source_name": "Greenhouse", "evidence": ["seed evidence"]},
        "company": {},
        "contacts": [],
        "saved": False,
        "saved_status": None,
        "saved_opportunity_id": None,
        "rank_age_hours": 1.0,
        "source_bucket": "ats",
        "cache_hit": False,
    }
    base.update(overrides)
    return base


def test_normalize_role_for_dedupe_strips_seniority_and_location_tokens():
    assert engine._normalize_role_for_dedupe("Senior AI Engineer Berlin") == "ai engineer"


def test_normalize_location_for_dedupe_prefers_country_when_contained():
    assert engine._normalize_location_for_dedupe("Berlin, Germany", "Germany") == "germany"


def test_normalize_location_for_dedupe_detects_known_city():
    assert engine._normalize_location_for_dedupe("Munich remote", None) == "munich"


def test_normalize_location_for_dedupe_falls_back_to_unknown():
    assert engine._normalize_location_for_dedupe("", None) == "unknown"


def test_dedupe_keys_includes_canonical_and_semantic_keys():
    item = _opportunity()
    keys = engine._dedupe_keys(item)
    assert "url:https://acme.ai/jobs/1" in keys
    assert any(key.startswith("semantic:acme ai|ai engineer|") for key in keys)
    assert any(key.startswith("semantic-domain:acme.ai|ai engineer|") for key in keys)


def test_dedupe_keys_canonicalizes_direct_and_portal_urls():
    item = _opportunity(canonical_job_url=None, direct_apply_url="https://acme.ai/jobs/1?utm_source=x")
    keys = engine._dedupe_keys(item)
    assert "url:https://acme.ai/jobs/1" in keys


def test_prefer_opportunity_prefers_higher_score():
    low = _opportunity(score_total=5.0)
    high = _opportunity(score_total=20.0)
    assert engine._prefer_opportunity(low, high) is high
    assert engine._prefer_opportunity(high, low) is high


def test_prefer_opportunity_tiebreaks_on_direct_apply_url():
    no_direct = _opportunity(score_total=10.0, direct_apply_url=None)
    with_direct = _opportunity(score_total=10.0, direct_apply_url="https://acme.ai/apply")
    assert engine._prefer_opportunity(no_direct, with_direct) is with_direct


def test_merge_duplicate_opportunities_unions_contacts_and_labels():
    primary = _opportunity(contacts=[{"email": "a@acme.ai", "name": "A"}], score_labels=["Direct Apply"])
    secondary = _opportunity(
        contacts=[{"email": "b@acme.ai", "name": "B"}],
        score_labels=["Fresh"],
        direct_apply_url="https://acme.ai/apply",
    )
    merged = engine._merge_duplicate_opportunities(primary, secondary)
    emails = {c["email"] for c in merged["contacts"]}
    assert emails == {"a@acme.ai", "b@acme.ai"}
    assert set(merged["score_labels"]) >= {"Direct Apply", "Fresh"}


def test_merge_duplicate_opportunities_fills_missing_urls_from_secondary():
    primary = _opportunity(direct_apply_url=None, company_careers_url=None)
    secondary = _opportunity(direct_apply_url="https://acme.ai/apply", company_careers_url="https://acme.ai/careers")
    merged = engine._merge_duplicate_opportunities(primary, secondary)
    assert merged["direct_apply_url"] == "https://acme.ai/apply"
    assert merged["company_careers_url"] == "https://acme.ai/careers"


def test_merge_duplicate_opportunities_merges_citation_evidence_without_duplicates():
    primary = _opportunity(citation={"evidence": ["a", "b"]})
    secondary = _opportunity(citation={"evidence": ["b", "c"]})
    merged = engine._merge_duplicate_opportunities(primary, secondary)
    assert merged["citation"]["evidence"] == ["a", "b", "c"]


def test_finalize_merged_opportunity_sets_job_kind_when_apply_path_present():
    item = _opportunity(opportunity_kind="outreach_lead", direct_apply_url="https://acme.ai/apply", score_labels=[])
    finalized = engine._finalize_merged_opportunity(item)
    assert finalized["opportunity_kind"] == "job"
    assert "Direct Apply" in finalized["score_labels"]


def test_finalize_merged_opportunity_outreach_lead_without_apply_path():
    item = _opportunity(direct_apply_url=None, company_careers_url=None, opportunity_kind="job")
    finalized = engine._finalize_merged_opportunity(item)
    assert finalized["opportunity_kind"] == "outreach_lead"


def test_finalize_merged_opportunity_assigns_source_bucket_from_source_type():
    item = _opportunity(source_type="theirstack_search")
    assert engine._finalize_merged_opportunity(item)["source_bucket"] == "theirstack"
    item = _opportunity(source_type="apify_actor")
    assert engine._finalize_merged_opportunity(item)["source_bucket"] == "apify"


def test_dedupe_opportunities_merges_items_sharing_canonical_url():
    item_a = _opportunity(canonical_job_url="https://acme.ai/jobs/1", score_total=5.0, contacts=[{"email": "a@acme.ai"}])
    item_b = _opportunity(canonical_job_url="https://acme.ai/jobs/1", score_total=15.0, contacts=[{"email": "b@acme.ai"}])
    result = engine._dedupe_opportunities([item_a, item_b])
    assert len(result) == 1
    assert result[0]["score_total"] == 15.0
    emails = {c["email"] for c in result[0]["contacts"]}
    assert emails == {"a@acme.ai", "b@acme.ai"}


def test_dedupe_opportunities_keeps_distinct_companies_separate():
    item_a = _opportunity(company_name="Acme AI", canonical_job_url="https://acme.ai/jobs/1")
    item_b = _opportunity(company_name="Other Startup", canonical_job_url="https://other.ai/jobs/1", company_domain="other.ai")
    result = engine._dedupe_opportunities([item_a, item_b])
    assert len(result) == 2


def test_dedupe_opportunities_merges_via_semantic_key_without_shared_url():
    item_a = _opportunity(canonical_job_url=None, direct_apply_url=None, portal_job_url=None, score_total=5.0)
    item_b = _opportunity(canonical_job_url=None, direct_apply_url=None, portal_job_url=None, score_total=12.0)
    result = engine._dedupe_opportunities([item_a, item_b])
    assert len(result) == 1
    assert result[0]["score_total"] == 12.0


def test_dedupe_opportunities_empty_input_returns_empty_list():
    assert engine._dedupe_opportunities([]) == []
