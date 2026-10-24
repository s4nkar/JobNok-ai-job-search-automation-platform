"""Unit tests for engine.py's misc pure helpers: seeded-source parsing,
location splitting, error scrubbing, actor/provider gating, and the small
humanizer/date-formatting functions used across providers."""

from app.modules.startup_hunt import engine


# ── build_seeded_sources / source host ─────────────────────────────────

def test_build_seeded_sources_keeps_only_allowed_types():
    rows = [
        {"type": "greenhouse", "name": "Acme", "company": "Acme"},
        {"type": "not_a_real_type", "name": "Bogus", "company": "Bogus"},
    ]
    sources = engine.build_seeded_sources(rows)
    assert len(sources) == 1
    assert sources[0].type == "greenhouse"


def test_build_seeded_sources_requires_a_name():
    rows = [{"type": "greenhouse", "name": "", "company": "Acme"}]
    assert engine.build_seeded_sources(rows) == []


def test_build_seeded_sources_defaults_company_to_name():
    rows = [{"type": "greenhouse", "name": "Acme"}]
    sources = engine.build_seeded_sources(rows)
    assert sources[0].company == "Acme"


def test_source_host_empty_when_no_url():
    source = engine.StartupHuntSourceConfig(type="greenhouse", name="Acme", company="Acme")
    assert engine._source_host(source) == ""


def test_source_host_extracts_lowercased_netloc():
    source = engine.StartupHuntSourceConfig(type="greenhouse", name="Acme", company="Acme", url="https://Boards.Greenhouse.io/acme")
    assert engine._source_host(source) == "boards.greenhouse.io"


# ── location splitting ──────────────────────────────────────────────────

def test_split_locations_splits_on_commas_and_connectors():
    locations = engine._split_locations({"location": "Berlin, Munich and Hamburg"})
    assert locations == ["Berlin", "Munich", "Hamburg"]


def test_split_locations_deduplicates_case_insensitively():
    locations = engine._split_locations({"location": "Berlin, berlin"})
    assert locations == ["Berlin"]


def test_split_locations_empty_when_blank():
    assert engine._split_locations({"location": ""}) == []


def test_location_search_targets_caps_at_max_count():
    payload = {"location": "A, B, C, D, E, F, G"}
    assert engine._location_search_targets(payload, max_count=3) == ["A", "B", "C"]


def test_location_search_targets_falls_back_to_germany():
    assert engine._location_search_targets({"location": ""}) == ["Germany"]


# ── relax payload ────────────────────────────────────────────────────────

def test_relax_search_payload_clears_restrictive_filters():
    payload = {
        "company_stage": "seed",
        "english_friendly_only": True,
        "direct_links_only": True,
        "remote_only": True,
        "posted_within_hours": 24,
        "query": "AI Engineer",
    }
    relaxed = engine._relax_search_payload(payload)
    assert relaxed["company_stage"] is None
    assert relaxed["english_friendly_only"] is False
    assert relaxed["direct_links_only"] is False
    assert relaxed["remote_only"] is False
    assert relaxed["posted_within_hours"] is None
    assert relaxed["query"] == "AI Engineer"  # untouched


# ── URL/error scrubbing ────────────────────────────────────────────────

def test_scrub_url_masks_secret_query_params():
    url = "https://api.example.com/x?token=abc123&page=2"
    assert engine._scrub_url(url) == "https://api.example.com/x?token=%2A%2A%2A&page=2"


def test_scrub_url_returns_unchanged_when_no_query():
    url = "https://api.example.com/x"
    assert engine._scrub_url(url) == url


def test_scrub_error_message_masks_urls_and_tokens():
    message = "Request to https://api.example.com/x?token=secret123 failed with apikey=abc"
    scrubbed = engine._scrub_error_message(message)
    assert "secret123" not in scrubbed
    assert "apikey=***" in scrubbed


def test_scrub_error_message_masks_apify_tokens():
    message = "auth failed for apify_api_ABCDEF123456"
    assert "apify_api_***" in engine._scrub_error_message(message)


# ── bucket-fatal classification ─────────────────────────────────────────

def test_classify_bucket_fatal_maps_known_statuses():
    import httpx
    response = httpx.Response(402, request=httpx.Request("GET", "https://x.test"))
    exc = httpx.HTTPStatusError("payment required", request=response.request, response=response)
    status, reason = engine._classify_bucket_fatal(exc)
    assert status == 402
    assert "usage limit" in reason


def test_classify_bucket_fatal_ignores_non_fatal_statuses():
    import httpx
    response = httpx.Response(500, request=httpx.Request("GET", "https://x.test"))
    exc = httpx.HTTPStatusError("server error", request=response.request, response=response)
    status, reason = engine._classify_bucket_fatal(exc)
    assert status is None
    assert reason is None


def test_classify_bucket_fatal_ignores_non_http_errors():
    status, reason = engine._classify_bucket_fatal(ValueError("boom"))
    assert status is None
    assert reason is None


# ── provider budget / actor support ─────────────────────────────────────

def test_provider_daily_budget_only_meters_theirstack(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "startup_hunt_theirstack_daily_budget", 42)
    assert engine._provider_daily_budget("theirstack_search") == 42
    assert engine._provider_daily_budget("greenhouse") is None


def test_is_supported_startup_actor_requires_owner_slash_name():
    assert engine._is_supported_startup_actor(None) is False
    assert engine._is_supported_startup_actor("") is False
    assert engine._is_supported_startup_actor("no-slash-here") is False


def test_is_supported_startup_actor_rejects_generic_browsing_actor():
    assert engine._is_supported_startup_actor("apify/rag-web-browser") is False


def test_is_supported_startup_actor_rejects_linkedin_scraper():
    assert engine._is_supported_startup_actor("someone/linkedin-jobs-scraper") is False


def test_is_supported_startup_actor_accepts_valid_actor_id():
    assert engine._is_supported_startup_actor("brilliant_gum/startup-jobs-intelligence") is True


def test_normalize_apify_actor_id_converts_slash_to_tilde():
    assert engine._normalize_apify_actor_id("owner/name") == "owner~name"


def test_normalize_apify_actor_id_leaves_tilde_form_unchanged():
    assert engine._normalize_apify_actor_id("owner~name") == "owner~name"


# ── humanizers ───────────────────────────────────────────────────────────

def test_humanize_theirstack_stage_maps_known_values():
    assert engine._humanize_theirstack_stage("series_a") == "Series A"
    assert engine._humanize_theirstack_stage(None) is None


def test_humanize_theirstack_stage_titlecases_unknown_values():
    assert engine._humanize_theirstack_stage("future_round") == "Future Round"


def test_humanize_employee_count_buckets_numeric_values():
    assert engine._humanize_employee_count(5) == "1 to 10"
    assert engine._humanize_employee_count(300) == "201 to 500"
    assert engine._humanize_employee_count(50000) == "10,000+"


def test_humanize_employee_count_passes_through_strings():
    assert engine._humanize_employee_count("Series A startup") == "Series A startup"


def test_humanize_employee_count_none_for_blank_or_invalid():
    assert engine._humanize_employee_count(None) is None
    assert engine._humanize_employee_count("") is None
    assert engine._humanize_employee_count([1, 2]) is None


def test_safe_company_website_url_rejects_social_and_infra_hosts():
    assert engine._safe_company_website_url("https://linkedin.com/company/acme") is None
    assert engine._safe_company_website_url("https://acme.vercel.app") is None


def test_safe_company_website_url_accepts_plain_company_domain():
    assert engine._safe_company_website_url("https://acme.ai") == "https://acme.ai"


def test_is_ats_url_true_for_known_ats_hosts():
    assert engine._is_ats_url("https://boards.greenhouse.io/acme") is True
    assert engine._is_ats_url("https://acme.com") is False
    assert engine._is_ats_url(None) is False


# ── country / date helpers ──────────────────────────────────────────────

def test_country_code_for_indeed_uses_override_table():
    assert engine._country_code_for_indeed("United Kingdom") == "gb"


def test_country_code_for_indeed_passes_through_valid_two_letter_code():
    assert engine._country_code_for_indeed("fr") == "fr"


def test_country_code_for_indeed_defaults_to_de():
    assert engine._country_code_for_indeed(None) == "de"
    assert engine._country_code_for_indeed("Atlantis") == "de"


def test_google_date_restrict_buckets_by_hours():
    assert engine._google_date_restrict(None) is None
    assert engine._google_date_restrict(12) == "d1"
    assert engine._google_date_restrict(48) == "d2"
    assert engine._google_date_restrict(24 * 14) == "w2"


def test_indeed_date_posted_buckets_by_hours():
    assert engine._indeed_date_posted(None) is None
    assert engine._indeed_date_posted(12) == "1"
    assert engine._indeed_date_posted(60) == "3"
    assert engine._indeed_date_posted(24 * 6) == "7"
    assert engine._indeed_date_posted(24 * 10) == "14"


def test_slugify_location_normalizes_and_hyphenates():
    assert engine._slugify_location("San Francisco / Bay Area") == "san-francisco-bay-area"
    assert engine._slugify_location(None) == ""


def test_build_startupmap_url_defaults_to_germany_root():
    assert engine._build_startupmap_url(None, "Germany") == "https://startupmap.one/startups"
    assert engine._build_startupmap_url(None, None) == "https://startupmap.one/startups"


def test_build_startupmap_url_uses_city_slug_when_given():
    assert engine._build_startupmap_url("Berlin", "Germany") == "https://startupmap.one/startups/berlin"


def test_build_startupmap_url_uses_country_slug_for_non_germany():
    assert engine._build_startupmap_url(None, "France") == "https://startupmap.one/startups/france"


# ── misc search/role helpers ─────────────────────────────────────────────

def test_root_url_rejects_shortener_and_ats_hosts():
    assert engine._root_url("https://bit.ly/xyz") is None
    assert engine._root_url("https://boards.greenhouse.io/acme") is None


def test_root_url_returns_scheme_and_netloc_for_normal_site():
    assert engine._root_url("https://acme.ai/careers/123") == "https://acme.ai"


def test_root_url_none_for_malformed_url():
    assert engine._root_url("not a url") is None
    assert engine._root_url("") is None


def test_search_query_variant_joins_variants_with_or():
    result = engine._search_query_variant("AI Engineer", mode="web")
    assert "OR" in result
    assert '"AI Engineer"' in result


def test_role_title_from_search_result_prefers_segment_with_role_keyword():
    title = "Jobs at Acme | AI Engineer | Berlin"
    assert engine._role_title_from_search_result(title, "AI Engineer") == "AI Engineer"


def test_role_title_from_search_result_falls_back_to_query_when_blank():
    assert engine._role_title_from_search_result("", "AI Engineer") == "AI Engineer"


def test_infer_company_from_search_result_extracts_last_segment():
    assert engine._infer_company_from_search_result("AI Engineer - Acme Startup", "https://acme.ai") == "Acme Startup"


def test_infer_company_from_search_result_falls_back_to_url_when_no_separator():
    assert engine._infer_company_from_search_result("AI Engineer Role", "https://acme.ai") == "acme.ai"


def test_is_startup_jobs_intelligence_actor_detects_known_actor():
    assert engine._is_startup_jobs_intelligence_actor("brilliant_gum/startup-jobs-intelligence") is True
    assert engine._is_startup_jobs_intelligence_actor("brilliant_gum~startup-jobs-intelligence") is True
    assert engine._is_startup_jobs_intelligence_actor("someone/other-actor") is False


def test_startup_jobs_intelligence_seniority_maps_internal_values():
    assert engine._startup_jobs_intelligence_seniority({"seniority_preference": "staff_plus"}) == "staff"
    assert engine._startup_jobs_intelligence_seniority({"seniority_preference": "junior"}) == "entry"
    assert engine._startup_jobs_intelligence_seniority({}) is None


def test_theirstack_funding_stages_maps_stage_keywords():
    payload = {"company_stage": "Seed"}
    strategy = {}
    assert engine._theirstack_funding_stages(payload, strategy) == ["seed"]


def test_theirstack_funding_stages_defaults_for_startup_focused_hunt():
    payload = {"strategy_prompt": "hidden gems only"}
    strategy = {}
    stages = engine._theirstack_funding_stages(payload, strategy)
    assert stages == ["pre_seed", "seed", "series_a", "series_b"]


def test_theirstack_funding_stages_empty_when_not_startup_focused():
    assert engine._theirstack_funding_stages({}, {}) == []
