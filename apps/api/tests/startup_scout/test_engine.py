"""Unit tests for startup_scout.engine.

Mirrors resume_tailor/test_matcher.py's style: deterministic/pure parsing
and filtering logic is tested directly with hand-built fixtures (no I/O).
The async orchestration functions (search_startups, web_search_contacts,
verify_contact, enrich_linkedin_url, apollo_search_contacts) are tested with
the DDG/httpx boundary monkeypatched, exactly like test_ai_provider.py mocks
httpx.AsyncClient.post — no real network access, no Redis/Upstash (this
module's own circuit_is_open/record_provider_result are monkeypatched to
no-ops the same way test_ai_provider.py's _patch_cache_bypass neutralizes
provider.py's).
"""

import httpx

from app.core.config import settings
from app.modules.startup_scout import engine


def _noop_sleep(monkeypatch):
    """engine.asyncio IS the real asyncio module — tests that exercise
    search_startups/web_search_contacts/enrich_linkedin_url would otherwise
    pay the real inter-query backoff (1-2s each, several queries per call).
    monkeypatch restores asyncio.sleep automatically after each test."""
    async def fake_sleep(seconds):
        return None
    monkeypatch.setattr(engine.asyncio, "sleep", fake_sleep)


def _apollo_response(status_code: int, json_body: dict) -> httpx.Response:
    # httpx.Response.raise_for_status() requires `.request` to be set even
    # for a 200 — unlike a bare httpx.Response(200, json=...) construction.
    r = httpx.Response(status_code, json=json_body)
    r.request = httpx.Request("POST", engine.APOLLO_PEOPLE_URL)
    return r


# ── _extract_domain ───────────────────────────────────────────────────────

def test_extract_domain_returns_apex_domain_for_subdomain():
    assert engine._extract_domain("https://lb.crunchbase.com/organization/foo") == "crunchbase.com"


def test_extract_domain_keeps_three_labels_for_two_part_tld():
    assert engine._extract_domain("https://example.co.uk/page") == "example.co.uk"


def test_extract_domain_strips_port():
    assert engine._extract_domain("https://example.com:8080/page") == "example.com"


def test_extract_domain_returns_none_for_non_url():
    assert engine._extract_domain("not-a-url") is None


# ── _normalize_description ────────────────────────────────────────────────

def test_normalize_description_empty_string():
    assert engine._normalize_description("") == ""


def test_normalize_description_capitalizes_first_letter():
    assert engine._normalize_description("hello world.") == "Hello world."


def test_normalize_description_collapses_whitespace():
    assert engine._normalize_description("  multiple   spaces  here.  ") == "Multiple spaces here."


# ── Platform.query / _select_platforms ───────────────────────────────────

def test_platform_query_uses_site_path_when_set():
    p = engine.Platform(
        domain="example.com", location_keywords=[], stages=[],
        query_tpl="{industry} startup {location} {stage}", site_path="companies",
    )
    assert p.query("Berlin", "ai", "seed") == "site:example.com/companies ai startup Berlin seed"


def test_platform_query_without_site_path():
    p = engine.Platform(
        domain="example.com", location_keywords=[], stages=[],
        query_tpl="{industry} startup {location} {stage}",
    )
    # Blank industry/stage fall back to the "startup" default baked into query_tpl's format args.
    assert p.query("Berlin", "", "") == "site:example.com startup startup Berlin startup"


def test_select_platforms_caps_at_max_platforms_and_sorts_by_priority():
    selected = engine._select_platforms("berlin, germany", ["seed"])
    assert len(selected) <= engine.MAX_PLATFORMS
    assert [p.priority for p in selected] == sorted(p.priority for p in selected)


def test_select_platforms_filters_out_platform_whose_stages_dont_match():
    # antler.co only serves pre-seed/seed; singapore has few enough matching
    # platforms that it isn't masked by the MAX_PLATFORMS cap either way.
    seed_domains = [p.domain for p in engine._select_platforms("singapore", ["seed"])]
    series_a_domains = [p.domain for p in engine._select_platforms("singapore", ["series-a"])]
    assert "antler.co" in seed_domains
    assert "antler.co" not in series_a_domains


def test_select_platforms_excludes_platform_with_no_matching_location_keyword():
    # inc42.com is India-specific — a Berlin search must never select it.
    domains = [p.domain for p in engine._select_platforms("berlin, germany", [])]
    assert "inc42.com" not in domains


# ── _parse_company: URL-level rejections ──────────────────────────────────

def test_parse_company_returns_none_without_href():
    assert engine._parse_company({"title": "X", "body": "Y"}) is None


def test_parse_company_rejects_skip_url_fragment():
    item = {"href": "https://www.linkedin.com/jobs/view/123", "title": "Some Job", "body": "desc"}
    assert engine._parse_company(item) is None


def test_parse_company_rejects_meta_search_engine_domain():
    item = {"href": "https://www.google.com/somepage", "title": "Google", "body": "desc"}
    assert engine._parse_company(item) is None


def test_parse_company_rejects_news_domain():
    item = {
        "href": "https://techcrunch.com/2024/01/01/some-startup-raises",
        "title": "Some Startup Raises $10M", "body": "desc",
    }
    assert engine._parse_company(item) is None


def test_parse_company_rejects_skip_url_segment():
    item = {"href": "https://example.com/blog/my-post", "title": "Some real post title here", "body": "desc"}
    assert engine._parse_company(item) is None


def test_parse_company_rejects_article_url_with_date_path():
    item = {
        "href": "https://example.com/2024/01/mirelo-raises-10m",
        "title": "Mirelo raises $10M in funding", "body": "desc",
    }
    assert engine._parse_company(item) is None


def test_parse_company_requires_directory_profile_path():
    # wellfound.com requires a /company/ path — a non-profile wellfound URL must be rejected.
    item = {"href": "https://wellfound.com/startups/acme", "title": "Acme Startup Profile", "body": "desc"}
    assert engine._parse_company(item) is None


def test_parse_company_rejects_crunchbase_subpage():
    item = {
        "href": "https://www.crunchbase.com/organization/acme-ai/recent_investments",
        "title": "Acme AI - Recent Investments", "body": "desc",
    }
    assert engine._parse_company(item) is None


def test_parse_company_rejects_dealroom_filter_page():
    item = {"href": "https://app.dealroom.co/companies/f/some-filter", "title": "Acme AI", "body": "desc"}
    assert engine._parse_company(item) is None


def test_parse_company_rejects_profile_subpage_ending():
    item = {"href": "https://wellfound.com/company/acme/jobs", "title": "Acme Jobs", "body": "desc"}
    assert engine._parse_company(item) is None


# ── _parse_company: title-level rejections ────────────────────────────────

def test_parse_company_rejects_title_too_short():
    item = {"href": "https://example.com/acme", "title": "Ab", "body": "desc"}
    assert engine._parse_company(item) is None


def test_parse_company_rejects_link_to_prefix_title():
    item = {"href": "https://example.com/acme", "title": "Link to Acme Inc", "body": "desc"}
    assert engine._parse_company(item) is None


def test_parse_company_rejects_listing_page_title():
    item = {"href": "https://example.com/acme-page", "title": "Top 10 AI Startups in Berlin", "body": "desc"}
    assert engine._parse_company(item) is None


def test_parse_company_rejects_accelerator_title():
    item = {"href": "https://example.com/acme", "title": "Acme Accelerator Program", "body": "desc"}
    assert engine._parse_company(item) is None


def test_parse_company_rejects_bare_geo_name_title():
    item = {"href": "https://example.com/berlin", "title": "Berlin", "body": "desc"}
    assert engine._parse_company(item) is None


def test_parse_company_rejects_bare_url_as_name():
    item = {"href": "https://example.com/acme", "title": "foo.com/bar", "body": "desc"}
    assert engine._parse_company(item) is None


def test_parse_company_rejects_comma_separated_tag_list_title():
    item = {
        "href": "https://example.com/acme",
        "title": "Artificial Intelligence, Deep Learning, Computer Vision", "body": "desc",
    }
    assert engine._parse_company(item) is None


def test_parse_company_rejects_generic_single_word_name():
    item = {"href": "https://example.com/acme", "title": "Startup", "body": "desc"}
    assert engine._parse_company(item) is None


# ── _parse_company: description-level rejections ──────────────────────────

def test_parse_company_rejects_venture_capital_firm_description():
    item = {
        "href": "https://example.com/acme", "title": "Acme Capital",
        "body": "Acme Capital is a venture capital firm investing in early-stage startups.",
    }
    assert engine._parse_company(item) is None


def test_parse_company_rejects_permanently_closed_company():
    item = {"href": "https://example.com/acme-ai", "title": "Acme AI", "body": "Acme AI permanently closed in 2023."}
    assert engine._parse_company(item) is None


def test_parse_company_rejects_bare_city_country_fragment_with_no_real_content():
    # Regression test for a bug found while writing this suite: the step-9
    # "thin content" guard used to swallow the first real sentence after the
    # location too (see engine.py's _name_word fix), incorrectly rejecting
    # every company whose snippet was shaped "City, Country. <description>."
    # This fixture (location only, no description at all) must still be
    # rejected — that part of the guard's intent is correct.
    item = {"href": "https://example.com/acme-ai", "title": "Acme AI", "body": "Berlin, Germany."}
    assert engine._parse_company(item) is None


# ── _parse_company: valid company passes through ───────────────────────────

def test_parse_company_accepts_valid_crunchbase_profile():
    item = {
        "href": "https://www.crunchbase.com/organization/acme-ai",
        "title": "Acme AI - Crunchbase Company Profile",
        "body": "Private. Berlin, Germany. Acme AI builds developer tools for fintech startups.",
    }
    result = engine._parse_company(item)
    assert result is not None
    assert result["name"] == "Acme AI"
    assert result["website"] == item["href"]
    assert result["domain"] == "crunchbase.com"
    # Real content survives the "thin location-only fragment" guard.
    assert "Acme AI builds developer tools" in result["description"]


def test_parse_company_accepts_valid_dealroom_profile_with_em_dash_title():
    # Dealroom titles use an em dash (—), not the en dash (–) the title-
    # stripping regex previously only accounted for.
    item = {
        "href": "https://app.dealroom.co/companies/acme-ai",
        "title": "Acme AI — Power Law company profile | Dealroom",
        "body": "Private. Berlin, Germany. Acme AI builds developer tools for fintech.",
    }
    result = engine._parse_company(item)
    assert result is not None
    assert result["name"] == "Acme AI"
    assert result["domain"] == "dealroom.co"


def test_parse_company_extracts_stage_and_employee_range_from_crunchbase_header():
    item = {
        "href": "https://www.crunchbase.com/organization/acme-ai",
        "title": "Acme AI - Crunchbase Company Profile",
        "body": "Private Seed Berlin, Germany 11-50 acme.ai",
    }
    result = engine._parse_company(item)
    assert result is not None
    assert result["_raw_stage"] == "Seed"
    assert result["_raw_size"] == "11-50"


def test_parse_company_real_content_survives_thin_location_guard_across_sentence():
    item = {
        "href": "https://example.com/acme-ai", "title": "Acme AI",
        "body": "Berlin, Germany. Investor Name. Seed round.",
    }
    result = engine._parse_company(item)
    assert result is not None
    assert "Investor Name" in result["description"]


# ── _is_valid_person_name ───────────────────────────────────────────────────

def test_is_valid_person_name_allows_lowercase_particles():
    assert engine._is_valid_person_name("Jan van der Berg") is True


def test_is_valid_person_name_rejects_stopword():
    assert engine._is_valid_person_name("The Team") is False


def test_is_valid_person_name_allows_single_initial_with_dot():
    assert engine._is_valid_person_name("J. Doe") is True


def test_is_valid_person_name_rejects_bare_single_letter_without_dot():
    assert engine._is_valid_person_name("J Doe") is False


def test_is_valid_person_name_rejects_single_word():
    assert engine._is_valid_person_name("Jane") is False


def test_is_valid_person_name_rejects_more_than_five_words():
    assert engine._is_valid_person_name("A B C D E F") is False


# ── _extract_names_from_snippet ────────────────────────────────────────────

def test_extract_names_from_snippet_finds_name_and_role():
    text = "Jane Smith is the Co-Founder of Acme Inc, which builds developer tools."
    contacts = engine._extract_names_from_snippet(text, source_url="https://example.com/x")
    assert len(contacts) == 1
    assert contacts[0]["name"] == "Jane Smith"
    assert contacts[0]["title"] == "Co-Founder"
    assert contacts[0]["source_url"] == "https://example.com/x"


def test_extract_names_from_snippet_deduplicates_repeated_mention():
    text = "Jane Smith is the Co-Founder of Acme Inc. Jane Smith is the Co-Founder of Acme Inc again."
    contacts = engine._extract_names_from_snippet(text)
    assert len(contacts) == 1


def test_extract_names_from_snippet_rejects_stopword_fragment():
    text = "The CEO announced new funding for the company today."
    contacts = engine._extract_names_from_snippet(text)
    assert contacts == []


# ── _linkedin_title_matches_name ───────────────────────────────────────────

def test_linkedin_title_matches_name_requires_last_name():
    assert engine._linkedin_title_matches_name("Jane Doe - Co-Founder at Acme | LinkedIn", "Jane Doe") is True


def test_linkedin_title_matches_name_rejects_different_person():
    assert engine._linkedin_title_matches_name("Mohamed Belja - CEO | LinkedIn", "Mauritz Andreae") is False


def test_linkedin_title_matches_name_allows_short_first_name_mismatch_in_title():
    # First names under 4 chars don't need to appear in the title, only the last name does.
    assert engine._linkedin_title_matches_name("Jo Doe - CEO | LinkedIn", "Jo Doe") is True


# ── _parse_linkedin_person ─────────────────────────────────────────────────

def test_parse_linkedin_person_parses_name_role_and_url():
    item = {
        "href": "https://www.linkedin.com/in/janedoe",
        "title": "Jane Doe - Co-Founder at Acme Inc | LinkedIn",
        "body": "Jane Doe is Co-Founder at Acme Inc leading product.",
    }
    result = engine._parse_linkedin_person(item, company_lower="acme inc")
    assert result == {
        "name": "Jane Doe", "title": "Co-Founder", "email": None,
        "linkedin_url": "https://www.linkedin.com/in/janedoe",
        "source": "web_scrape", "source_url": "https://www.linkedin.com/in/janedoe",
        "confidence": 0.75,
    }


def test_parse_linkedin_person_returns_none_for_non_linkedin_url():
    item = {"href": "https://example.com/not-linkedin", "title": "Jane Doe - CEO | LinkedIn", "body": ""}
    assert engine._parse_linkedin_person(item, company_lower="acme") is None


def test_parse_linkedin_person_rejects_role_naming_a_different_company():
    item = {
        "href": "https://www.linkedin.com/in/elliott",
        "title": "Elliott Spelman - Co Founder / CEO of Luna Medical Technology | LinkedIn",
        "body": "bio",
    }
    assert engine._parse_linkedin_person(item, company_lower="acme") is None


def test_parse_linkedin_person_rejects_job_title_mistaken_for_name():
    item = {"href": "https://www.linkedin.com/in/x", "title": "Senior Engineer Manager - CEO | LinkedIn", "body": "acme"}
    assert engine._parse_linkedin_person(item, company_lower="acme") is None


def test_parse_linkedin_person_short_company_name_requires_title_match_not_just_body():
    # "lf1" is <=4 chars — body mentions it via a sidebar widget, but the
    # profile's own title doesn't, so this must be rejected.
    item = {
        "href": "https://www.linkedin.com/in/x", "title": "John Smith - Engineer | LinkedIn",
        "body": "People also at LF1: John Smith",
    }
    assert engine._parse_linkedin_person(item, company_lower="lf1") is None


def test_parse_linkedin_person_short_company_name_accepted_when_in_title():
    item = {"href": "https://www.linkedin.com/in/x", "title": "John Smith - CTO at LF1 | LinkedIn", "body": "no mention"}
    result = engine._parse_linkedin_person(item, company_lower="lf1")
    assert result is not None
    assert result["name"] == "John Smith"


def test_parse_linkedin_person_strips_multi_profile_concatenation():
    # DDG occasionally fuses "People also viewed" entries into one title —
    # only the first profile's segment must be kept.
    item = {
        "href": "https://www.linkedin.com/in/selink",
        "title": "Selin K - COO | LinkedInArvind Jain - CEO",
        "body": "Selin K leads product at Acme Inc.",
    }
    result = engine._parse_linkedin_person(item, company_lower="acme inc")
    assert result is not None
    assert result["name"] == "Selin K"


# ── _ddg_search ──────────────────────────────────────────────────────────

async def test_ddg_search_returns_empty_list_on_exception(monkeypatch):
    async def fake_ddg_search_raw(query, max_results=15):
        raise RuntimeError("DDG blew up")
    monkeypatch.setattr(engine, "_ddg_search_raw", fake_ddg_search_raw)
    assert await engine._ddg_search("anything") == []


async def test_ddg_search_passes_through_results_on_success(monkeypatch):
    async def fake_ddg_search_raw(query, max_results=15):
        return [{"href": "https://example.com", "title": "X", "body": "Y"}]
    monkeypatch.setattr(engine, "_ddg_search_raw", fake_ddg_search_raw)
    assert await engine._ddg_search("anything") == [{"href": "https://example.com", "title": "X", "body": "Y"}]


# ── search_startups ──────────────────────────────────────────────────────

def _patch_search_infra(monkeypatch, *, circuit_open: bool = False):
    _noop_sleep(monkeypatch)

    async def fake_circuit_is_open(scope, provider_name):
        return circuit_open

    async def fake_record_provider_result(scope, provider_name, *, ok):
        return None

    monkeypatch.setattr(engine, "circuit_is_open", fake_circuit_is_open)
    monkeypatch.setattr(engine, "record_provider_result", fake_record_provider_result)


async def test_search_startups_clamps_limit_to_minimum_of_ten(monkeypatch):
    _patch_search_infra(monkeypatch)

    async def fake_ddg_search_raw(query, max_results=15):
        return []
    monkeypatch.setattr(engine, "_ddg_search_raw", fake_ddg_search_raw)

    result = await engine.search_startups(location="Berlin", funding_stages=[], industry="", limit=5)
    assert result["meta"]["limit"] == 10


async def test_search_startups_clamps_limit_to_maximum_of_two_hundred(monkeypatch):
    _patch_search_infra(monkeypatch)

    async def fake_ddg_search_raw(query, max_results=15):
        return []
    monkeypatch.setattr(engine, "_ddg_search_raw", fake_ddg_search_raw)

    result = await engine.search_startups(location="Berlin", funding_stages=[], industry="", limit=500)
    assert result["meta"]["limit"] == 200


async def test_search_startups_skips_remaining_queries_when_circuit_open(monkeypatch):
    _patch_search_infra(monkeypatch, circuit_open=True)

    calls = []

    async def fake_ddg_search_raw(query, max_results=15):
        calls.append(query)
        return []
    monkeypatch.setattr(engine, "_ddg_search_raw", fake_ddg_search_raw)

    result = await engine.search_startups(location="Berlin", funding_stages=[], industry="", limit=10)
    assert result["meta"]["queries_run"] == 0
    assert calls == []


async def test_search_startups_dedupes_stage_filters_and_buckets_unconfirmed(monkeypatch):
    """A company whose snippet has no detectable stage goes to `unconfirmed`
    (not dropped, not treated as a match); a company with a stage that
    doesn't match the requested filter is dropped entirely; a matching
    company is kept. The same three items are returned for every query, so
    this also exercises the url/name dedup in _ingest."""
    _patch_search_infra(monkeypatch)

    items = [
        {
            "href": "https://www.crunchbase.com/organization/foo-seed",
            "title": "FooSeed - Crunchbase Company Profile",
            "body": "Private. Berlin, Germany. FooSeed builds developer tools for fintech. Seed round raised.",
        },
        {
            "href": "https://www.crunchbase.com/organization/bar-seriesa",
            "title": "BarSeriesA - Crunchbase Company Profile",
            "body": "Private. Berlin, Germany. BarSeriesA builds analytics tools. Series A funding raised.",
        },
        {
            "href": "https://www.crunchbase.com/organization/baz-co",
            "title": "BazCo - Crunchbase Company Profile",
            "body": "Private. Munich, Germany. BazCo builds analytics dashboards for retailers.",
        },
    ]

    async def fake_ddg_search_raw(query, max_results=15):
        return items
    monkeypatch.setattr(engine, "_ddg_search_raw", fake_ddg_search_raw)

    result = await engine.search_startups(location="Berlin, Germany", funding_stages=["seed"], industry="ai", limit=10)

    assert [c["name"] for c in result["companies"]] == ["FooSeed"]
    assert [c["name"] for c in result["unconfirmed"]] == ["BazCo"]
    assert result["meta"]["sources"] == {"Crunchbase": 1}


# ── web_search_contacts ────────────────────────────────────────────────────

async def test_web_search_contacts_combines_general_linkedin_and_crunchbase_sources(monkeypatch):
    _noop_sleep(monkeypatch)

    async def fake_ddg_search(query, max_results=10):
        if "site:linkedin.com/in" in query:
            return [{
                "href": "https://www.linkedin.com/in/janedoe",
                "title": "Jane Doe - Co-Founder at Acme Inc | LinkedIn",
                "body": "Jane Doe is Co-Founder at Acme Inc leading product.",
            }]
        if "site:crunchbase.com" in query:
            return [{"href": "https://crunchbase.com/x", "title": "Acme Inc team", "body": "John Roe is the CEO of Acme Inc."}]
        return [
            {
                "href": "https://example.com/article", "title": "Acme Inc overview",
                "body": "Jane Smith is the Co-Founder of Acme Inc, which builds developer tools.",
            },
            {
                "href": "https://example.com/unrelated", "title": "Unrelated article",
                "body": "Some unrelated person is CEO of a different company.",
            },
        ]
    monkeypatch.setattr(engine, "_ddg_search", fake_ddg_search)

    contacts = await engine.web_search_contacts("Acme Inc")
    names = {c["name"] for c in contacts}
    assert names == {"Jane Smith", "Jane Doe", "John Roe"}


async def test_web_search_contacts_rejects_general_result_missing_company_mention(monkeypatch):
    _noop_sleep(monkeypatch)

    async def fake_ddg_search(query, max_results=10):
        if "site:linkedin.com/in" in query or "site:crunchbase.com" in query:
            return []
        return [{
            "href": "https://example.com/unrelated", "title": "Unrelated article",
            "body": "Some unrelated person is CEO of a different company.",
        }]
    monkeypatch.setattr(engine, "_ddg_search", fake_ddg_search)

    contacts = await engine.web_search_contacts("Acme Inc")
    assert contacts == []


# ── verify_contact ──────────────────────────────────────────────────────────

async def test_verify_contact_confirms_via_independent_reliable_source(monkeypatch):
    _noop_sleep(monkeypatch)

    async def fake_ddg_search(query, max_results=8):
        return [
            {"href": "https://example.com/original", "title": "x", "body": "no match here"},
            {"href": "https://reddit.com/r/startups/post", "title": "Jane Doe Acme Inc", "body": "Jane Doe Acme Inc mentioned"},
            {"href": "https://news.example.com/article", "title": "Jane Doe joins Acme Inc", "body": "Jane Doe is now at Acme Inc as CTO."},
        ]
    monkeypatch.setattr(engine, "_ddg_search", fake_ddg_search)

    is_verified, url = await engine.verify_contact(
        "Jane Doe", "Acme Inc", original_source_url="https://example.com/original",
    )
    assert is_verified is True
    assert url == "https://news.example.com/article"


async def test_verify_contact_rejects_unreliable_domain_as_sole_source(monkeypatch):
    _noop_sleep(monkeypatch)

    async def fake_ddg_search(query, max_results=8):
        return [{"href": "https://reddit.com/x", "title": "y", "body": "Jane Doe Acme Inc"}]
    monkeypatch.setattr(engine, "_ddg_search", fake_ddg_search)

    is_verified, url = await engine.verify_contact("Jane Doe", "Acme Inc")
    assert (is_verified, url) == (False, None)


async def test_verify_contact_skips_ddg_entirely_for_empty_input():
    called = False

    async def fake_ddg_search(query, max_results=8):
        nonlocal called
        called = True
        return []

    import app.modules.startup_scout.engine as engine_module
    original = engine_module._ddg_search
    engine_module._ddg_search = fake_ddg_search
    try:
        result = await engine.verify_contact("", "Acme Inc")
    finally:
        engine_module._ddg_search = original

    assert result == (False, None)
    assert called is False


# ── enrich_linkedin_url ──────────────────────────────────────────────────────

async def test_enrich_linkedin_url_found_on_first_query(monkeypatch):
    _noop_sleep(monkeypatch)

    async def fake_ddg_search(query, max_results=5):
        return [{"href": "https://www.linkedin.com/in/janedoe", "title": "Jane Doe - CTO | LinkedIn"}]
    monkeypatch.setattr(engine, "_ddg_search", fake_ddg_search)

    assert await engine.enrich_linkedin_url("Jane Doe", "Acme Inc") == "https://www.linkedin.com/in/janedoe"


async def test_enrich_linkedin_url_falls_back_to_name_only_query(monkeypatch):
    _noop_sleep(monkeypatch)
    calls = []

    async def fake_ddg_search(query, max_results=5):
        calls.append(query)
        if len(calls) == 1:
            return []
        return [{"href": "https://www.linkedin.com/in/janedoe", "title": "Jane Doe - CTO | LinkedIn"}]
    monkeypatch.setattr(engine, "_ddg_search", fake_ddg_search)

    result = await engine.enrich_linkedin_url("Jane Doe", "Acme Inc")
    assert result == "https://www.linkedin.com/in/janedoe"
    assert len(calls) == 2


async def test_enrich_linkedin_url_returns_none_when_no_title_matches(monkeypatch):
    _noop_sleep(monkeypatch)

    async def fake_ddg_search(query, max_results=5):
        return [{"href": "https://www.linkedin.com/in/other", "title": "John Smith - CEO | LinkedIn"}]
    monkeypatch.setattr(engine, "_ddg_search", fake_ddg_search)

    assert await engine.enrich_linkedin_url("Jane Doe", "Acme Inc") is None


# ── apollo_search_contacts ──────────────────────────────────────────────────

async def test_apollo_search_contacts_returns_empty_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "apollo_api_key", "")
    assert await engine.apollo_search_contacts("Acme Inc") == []


async def test_apollo_search_contacts_parses_people_and_confidence(monkeypatch):
    monkeypatch.setattr(settings, "apollo_api_key", "test-key")

    async def fake_post(self, url, json=None, headers=None):
        return _apollo_response(200, {"people": [
            {"first_name": "Jane", "last_name": "Doe", "title": "CEO",
             "email": "jane@acme.com", "linkedin_url": "https://linkedin.com/in/janedoe"},
            {"first_name": "John", "last_name": "Roe", "title": "CTO", "email": "", "linkedin_url": None},
        ]})
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    contacts = await engine.apollo_search_contacts("Acme Inc")
    assert contacts == [
        {"name": "Jane Doe", "title": "CEO", "email": "jane@acme.com",
         "linkedin_url": "https://linkedin.com/in/janedoe", "source": "apollo", "confidence": 0.8},
        {"name": "John Roe", "title": "CTO", "email": None, "linkedin_url": None, "source": "apollo", "confidence": 0.5},
    ]


async def test_apollo_search_contacts_returns_empty_on_request_failure(monkeypatch):
    monkeypatch.setattr(settings, "apollo_api_key", "test-key")

    async def fake_post(self, url, json=None, headers=None):
        raise httpx.ConnectError("boom")
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    assert await engine.apollo_search_contacts("Acme Inc") == []
