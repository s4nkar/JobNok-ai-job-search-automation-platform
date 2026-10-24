"""Unit tests for job_search.dedup — union-find-over-multiple-fingerprint-keys
dedup/merge/rank, pure logic, no I/O, no mocking needed."""

from app.modules.job_search import dedup


def _scored_job(**overrides):
    job = {
        "source_name": "Adzuna",
        "provider_type": "adzuna",
        "external_job_id": "1",
        "company": "Acme Corp",
        "role": "Software Engineer",
        "location": "Berlin, Germany",
        "job_url": "https://a.example.com/job/1",
        "job_url_canonical": "https://a.example.com/job/1",
        "posted_at": "2026-01-10T06:00:00+00:00",
        "applied": False,
        "application_status": None,
        "tracked_application_id": None,
        "citation": {"evidence": ["Matched role keywords: engineer"]},
        "ranking": {"score": 10.0, "age_hours": 6.0},
        "description_text": None,
        "salary_min": None,
        "salary_max": None,
    }
    job.update(overrides)
    return job


def test_dedupe_and_rank_merges_duplicate_canonical_urls_keeping_higher_score_as_primary():
    low = _scored_job(job_url_canonical="https://a.example.com/job/1", ranking={"score": 5.0, "age_hours": 10.0})
    high = _scored_job(
        job_url_canonical="https://a.example.com/job/1", ranking={"score": 9.0, "age_hours": 2.0}, company="Acme Corp"
    )

    result = dedup.dedupe_and_rank([low, high])

    assert len(result) == 1
    assert result[0]["ranking"]["score"] == 9.0


def test_dedupe_and_rank_merges_across_providers_via_semantic_key():
    adzuna_job = _scored_job(
        job_url_canonical="https://a.example.com/job/1",
        provider_type="adzuna",
        company="Acme Corp",
        role="Software Engineer",
        location="Berlin, Germany",
        ranking={"score": 8.0, "age_hours": 5.0},
    )
    bund_job = _scored_job(
        job_url_canonical="https://b.example.com/job/999",  # different URL, different provider
        provider_type="bundesagentur",
        company="Acme Corp",
        role="Senior Software Engineer",  # seniority noise word stripped before comparing
        location="Berlin, Germany",
        ranking={"score": 12.0, "age_hours": 1.0},
    )

    result = dedup.dedupe_and_rank([adzuna_job, bund_job])

    assert len(result) == 1
    assert result[0]["ranking"]["score"] == 12.0


def test_dedupe_and_rank_does_not_merge_generic_company_placeholders():
    """Two different unrelated postings can both legitimately be listed under
    a generic placeholder like "confidential" — that must never feed the
    semantic dedup key, since it would incorrectly merge unrelated jobs."""
    first = _scored_job(
        job_url_canonical="https://a.example.com/job/1",
        company="confidential",
        role="Software Engineer",
        location="Berlin, Germany",
    )
    second = _scored_job(
        job_url_canonical="https://b.example.com/job/2",
        company="Confidential",  # case-insensitive match to the same generic placeholder
        role="Software Engineer",
        location="Berlin, Germany",
    )

    result = dedup.dedupe_and_rank([first, second])

    assert len(result) == 2


def test_dedupe_and_rank_preserves_applied_status_from_lower_scoring_duplicate():
    primary = _scored_job(
        job_url_canonical="https://a.example.com/job/1",
        ranking={"score": 10.0, "age_hours": 1.0},
        applied=False,
        application_status=None,
        tracked_application_id=None,
    )
    other = _scored_job(
        job_url_canonical="https://a.example.com/job/1",
        ranking={"score": 5.0, "age_hours": 1.0},
        applied=True,
        application_status="applied",
        tracked_application_id="app-1",
    )

    result = dedup.dedupe_and_rank([primary, other])

    assert len(result) == 1
    assert result[0]["applied"] is True
    assert result[0]["application_status"] == "applied"
    assert result[0]["tracked_application_id"] == "app-1"


def test_dedupe_and_rank_does_not_overwrite_primarys_own_applied_status():
    primary = _scored_job(
        job_url_canonical="https://a.example.com/job/1",
        ranking={"score": 10.0, "age_hours": 1.0},
        applied=True,
        application_status="applied",
        tracked_application_id="app-primary",
    )
    other = _scored_job(
        job_url_canonical="https://a.example.com/job/1",
        ranking={"score": 5.0, "age_hours": 1.0},
        applied=True,
        application_status="applied",
        tracked_application_id="app-other",
    )

    result = dedup.dedupe_and_rank([primary, other])

    assert result[0]["tracked_application_id"] == "app-primary"


def test_dedupe_and_rank_backfills_missing_description_and_salary_from_duplicate():
    primary = _scored_job(
        job_url_canonical="https://a.example.com/job/1",
        ranking={"score": 10.0, "age_hours": 1.0},
        description_text=None,
        salary_min=None,
        salary_max=None,
    )
    other = _scored_job(
        job_url_canonical="https://a.example.com/job/1",
        ranking={"score": 5.0, "age_hours": 1.0},
        description_text="Full description here",
        salary_min=50000,
        salary_max=80000,
    )

    result = dedup.dedupe_and_rank([primary, other])

    assert result[0]["description_text"] == "Full description here"
    assert result[0]["salary_min"] == 50000
    assert result[0]["salary_max"] == 80000


def test_dedupe_and_rank_merges_evidence_deduped_and_capped_at_four():
    primary = _scored_job(
        job_url_canonical="https://a.example.com/job/1",
        ranking={"score": 10.0, "age_hours": 1.0},
        citation={"evidence": ["shared one", "primary two", "primary three"]},
    )
    other = _scored_job(
        job_url_canonical="https://a.example.com/job/1",
        ranking={"score": 5.0, "age_hours": 1.0},
        citation={"evidence": ["shared one", "other two", "other three"]},
    )

    result = dedup.dedupe_and_rank([primary, other])

    assert result[0]["citation"]["evidence"] == ["shared one", "primary two", "primary three", "other two"]


def test_dedupe_and_rank_sorts_by_score_descending_then_age_hours_ascending_on_ties():
    low_score = _scored_job(
        job_url_canonical="https://a.example.com/job/1", company="A", ranking={"score": 5.0, "age_hours": 1.0}
    )
    tie_older = _scored_job(
        job_url_canonical="https://b.example.com/job/2", company="B", ranking={"score": 10.0, "age_hours": 20.0}
    )
    tie_newer = _scored_job(
        job_url_canonical="https://c.example.com/job/3", company="C", ranking={"score": 10.0, "age_hours": 2.0}
    )

    result = dedup.dedupe_and_rank([low_score, tie_older, tie_newer])

    assert [r["company"] for r in result] == ["C", "B", "A"]


def test_dedupe_and_rank_bridges_two_previously_separate_groups_via_a_connecting_item():
    """An item that matches one group by URL and another group by semantic
    key must merge all three into a single group, not two separate pairs."""
    group_a = _scored_job(
        job_url_canonical="https://shared.example.com/job/1",
        company="X Corp",
        role="Engineer",
        location="Remote",
        ranking={"score": 3.0, "age_hours": 1.0},
    )
    group_b = _scored_job(
        job_url_canonical="https://b.example.com/job/2",
        company="Acme Corp",
        role="Software Engineer",
        location="Berlin, Germany",
        ranking={"score": 7.0, "age_hours": 1.0},
    )
    bridge = _scored_job(
        job_url_canonical="https://shared.example.com/job/1",  # matches group_a by URL
        company="Acme Corp",  # matches group_b by semantic key
        role="Software Engineer",
        location="Berlin, Germany",
        ranking={"score": 9.0, "age_hours": 1.0},
    )

    result = dedup.dedupe_and_rank([group_a, group_b, bridge])

    assert len(result) == 1
    assert result[0]["ranking"]["score"] == 9.0
