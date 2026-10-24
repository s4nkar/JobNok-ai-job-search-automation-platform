"""Unit tests for engine.py's HTML/contact extraction helpers and search
result parsing - all pure functions of a raw HTML/text string, no network."""

from app.modules.startup_hunt import engine


# ── JSON tree walking ────────────────────────────────────────────────────

def test_walk_json_objects_yields_every_nested_dict():
    data = {"a": {"b": 1}, "c": [{"d": 2}, {"e": {"f": 3}}]}
    objects = list(engine._walk_json_objects(data))
    assert {"a": {"b": 1}, "c": [{"d": 2}, {"e": {"f": 3}}]} in objects
    assert {"b": 1} in objects
    assert {"d": 2} in objects
    assert {"e": {"f": 3}} in objects
    assert {"f": 3} in objects


def test_walk_json_objects_empty_for_scalar():
    assert list(engine._walk_json_objects("just a string")) == []


def test_first_present_skips_empty_values():
    obj = {"a": "", "b": None, "c": [], "d": "value"}
    assert engine._first_present(obj, ["a", "b", "c", "d"]) == "value"


def test_first_present_none_when_nothing_present():
    assert engine._first_present({}, ["a", "b"]) is None


# ── directory entry dedupe ───────────────────────────────────────────────

def test_dedupe_directory_entries_prefers_longer_summary():
    entries = [
        {"company_name": "Acme", "detail_url": "https://acme.ai/startups/acme", "summary": "short"},
        {"company_name": "Acme", "detail_url": "https://acme.ai/startups/acme", "summary": "a much longer summary"},
    ]
    result = engine._dedupe_directory_entries(entries)
    assert len(result) == 1
    assert result[0]["summary"] == "a much longer summary"


def test_dedupe_directory_entries_keeps_distinct_keys():
    entries = [
        {"company_name": "Acme", "detail_url": "https://acme.ai/x"},
        {"company_name": "Other", "detail_url": "https://other.ai/y"},
    ]
    assert len(engine._dedupe_directory_entries(entries)) == 2


def test_normalize_seed_entry_fills_defaults_from_source_metadata():
    source = engine.StartupHuntSourceConfig(
        type="startup_company", name="Acme", company="Acme", url="https://acme.ai",
        metadata={"city": "Berlin", "country": "Germany", "default_stage": "seed"},
    )
    entry = engine._normalize_seed_entry({"company_name": "Acme"}, source, {"query": "AI Engineer"})
    assert entry["city"] == "Berlin"
    assert entry["country"] == "Germany"
    assert entry["stage"] == "seed"
    assert entry["target_role"] == "AI Engineer"
    assert entry["detail_url"] == "https://acme.ai"


# ── company/contact extraction ──────────────────────────────────────────

def test_company_name_from_url_titlecases_path_segment():
    assert engine._company_name_from_url("https://startupmap.one/startups/acme-ai") == "Acme Ai"


def test_company_name_from_url_strips_startup_noise_words():
    assert engine._company_name_from_url("https://x.test/startups/acme-startup") == "Acme"


def test_base_company_payload_reads_metadata_fields():
    source = engine.StartupHuntSourceConfig(
        type="startup_company", name="Acme", company="Acme", url="https://acme.ai",
        metadata={"stage": "seed", "english_friendly": True, "careers_url": "https://acme.ai/careers"},
    )
    payload = engine._base_company_payload(source)
    assert payload["stage"] == "seed"
    assert payload["english_friendly"] is True
    assert payload["company_careers_url"] == "https://acme.ai/careers"
    assert payload["company_website_url"] == "https://acme.ai"


def test_contacts_from_metadata_requires_some_identifying_field():
    metadata = {"contacts": [{"name": "", "title": "", "email": ""}, {"name": "Jane", "title": "Founder"}]}
    contacts = engine._contacts_from_metadata(metadata, "Acme")
    assert len(contacts) == 1
    assert contacts[0]["name"] == "Jane"
    assert contacts[0]["contact_type"] == "founder"


def test_contacts_from_page_extracts_email_and_linkedin():
    html = """
    <html><body>
    Contact us at jane.doe@acme.ai or visit
    <a href="https://linkedin.com/in/jane-doe">LinkedIn</a>
    </body></html>
    """
    contacts = engine._contacts_from_page(html, "https://acme.ai")
    emails = [c["email"] for c in contacts if c["email"]]
    linkedins = [c["linkedin_url"] for c in contacts if c["linkedin_url"]]
    assert "jane.doe@acme.ai" in emails
    assert "https://linkedin.com/in/jane-doe" in linkedins


def test_html_to_text_strips_tags_scripts_and_styles():
    html = "<html><head><style>.x{color:red}</style></head><body><script>alert(1)</script><p>Hello <b>World</b></p></body></html>"
    assert engine._html_to_text(html) == "Hello World"


def test_extract_careers_url_finds_careers_link():
    html = '<a href="/careers">Careers</a>'
    assert engine._extract_careers_url(html, "https://acme.ai") == "https://acme.ai/careers"


def test_extract_careers_url_none_when_absent():
    html = '<a href="/about">About</a>'
    assert engine._extract_careers_url(html, "https://acme.ai") is None


def test_extract_matching_job_url_scores_by_token_overlap():
    html = """
    <a href="https://acme.ai/jobs/1">AI Engineer</a>
    <a href="https://acme.ai/jobs/2">Office Manager</a>
    """
    result = engine._extract_matching_job_url(html, "https://acme.ai", "AI Engineer")
    assert result == "https://acme.ai/jobs/1"


def test_extract_matching_job_url_none_when_no_overlap():
    html = '<a href="https://acme.ai/jobs/1">Office Manager</a>'
    assert engine._extract_matching_job_url(html, "https://acme.ai", "AI Engineer") is None


def test_extract_company_website_url_skips_same_domain_and_social_links():
    html = """
    <a href="https://acme.ai/about">About</a>
    <a href="https://linkedin.com/company/acme">LinkedIn</a>
    <a href="https://acme-corp.com">Official site</a>
    """
    result = engine._extract_company_website_url(html, "https://acme.ai/careers")
    assert result == "https://acme-corp.com"


def test_is_probable_company_url_rejects_same_domain_as_page():
    assert engine._is_probable_company_url("https://acme.ai/jobs", "https://acme.ai") is False


def test_is_probable_company_url_rejects_social_and_infra_hosts():
    assert engine._is_probable_company_url("https://facebook.com/acme") is False
    assert engine._is_probable_company_url("https://acme.supabase.co") is False


def test_is_probable_company_url_accepts_distinct_company_domain():
    assert engine._is_probable_company_url("https://acme.ai", "https://startupmap.one/startups/acme") is True


def test_infer_contact_type_classifies_founder_ceo_recruiter_ai_lead():
    assert engine._infer_contact_type("Co-Founder") == "founder"
    assert engine._infer_contact_type("CEO") == "ceo"
    assert engine._infer_contact_type("Talent Partner") == "recruiter"
    assert engine._infer_contact_type("Head of AI") == "ai_lead"
    assert engine._infer_contact_type("Office Manager") == "hiring_manager"


def test_merge_contacts_dedupes_by_email_linkedin_name_and_caps_at_ten():
    primary = [{"email": "a@acme.ai", "linkedin_url": None, "name": "A"}]
    secondary = [{"email": "a@acme.ai", "linkedin_url": None, "name": "A"}, {"email": "b@acme.ai", "linkedin_url": None, "name": "B"}]
    merged = engine._merge_contacts(primary, secondary)
    assert len(merged) == 2
    emails = {c["email"] for c in merged}
    assert emails == {"a@acme.ai", "b@acme.ai"}


def test_merge_contacts_caps_at_ten():
    primary = [{"email": f"{i}@acme.ai", "linkedin_url": None, "name": str(i)} for i in range(15)]
    assert len(engine._merge_contacts(primary, [])) == 10


# ── search result HTML parsing ───────────────────────────────────────────

def test_resolve_search_result_url_unwraps_duckduckgo_redirect():
    href = "/l/?uddg=https%3A%2F%2Facme.ai%2Fjobs%2F1&rut=abc"
    assert engine._resolve_search_result_url(href) == "https://acme.ai/jobs/1"


def test_resolve_search_result_url_passes_through_absolute_urls():
    assert engine._resolve_search_result_url("https://acme.ai/jobs/1") == "https://acme.ai/jobs/1"


def test_resolve_search_result_url_adds_scheme_for_protocol_relative():
    assert engine._resolve_search_result_url("//acme.ai/jobs/1") == "https://acme.ai/jobs/1"


def test_resolve_search_result_url_none_for_internal_search_links():
    assert engine._resolve_search_result_url("/search?q=x") is None
    assert engine._resolve_search_result_url("") is None


def test_filter_search_matches_removes_search_engine_domains():
    matches = [{"url": "https://duckduckgo.com/y", "title": "careers"}]
    assert engine._filter_search_matches(matches, mode="web") == []


def test_filter_search_matches_ats_mode_requires_known_ats_host():
    matches = [
        {"url": "https://boards.greenhouse.io/acme", "title": "AI Engineer"},
        {"url": "https://acme.ai/about", "title": "AI Engineer"},
    ]
    result = engine._filter_search_matches(matches, mode="ats")
    assert len(result) == 1
    assert result[0]["url"] == "https://boards.greenhouse.io/acme"


def test_filter_search_matches_web_mode_requires_career_signal():
    matches = [
        {"url": "https://acme.ai/careers/ai-engineer", "title": "AI Engineer"},
        {"url": "https://acme.ai/blog/post", "title": "Company blog post"},
    ]
    result = engine._filter_search_matches(matches, mode="web")
    assert len(result) == 1
    assert "/careers/" in result[0]["url"]


def test_filter_search_matches_deduplicates_by_url():
    matches = [
        {"url": "https://acme.ai/careers", "title": "careers"},
        {"url": "https://acme.ai/careers", "title": "careers again"},
    ]
    assert len(engine._filter_search_matches(matches, mode="web")) == 1


def test_parse_search_results_extracts_duckduckgo_style_results():
    html = (
        '<a class="result__a" href="https://acme.ai/jobs/1">AI Engineer at Acme</a>'
        '<a class="result__snippet" href="https://acme.ai/jobs/1">Join our AI team</a>'
    )
    results = engine._parse_search_results(html)
    assert any(r["url"] == "https://acme.ai/jobs/1" for r in results)


# ── query builders ───────────────────────────────────────────────────────

def test_location_query_clause_single_location():
    assert engine._location_query_clause({"location": "Berlin"}) == "Berlin"


def test_location_query_clause_multiple_locations_joined_with_or():
    result = engine._location_query_clause({"location": "Berlin, Munich"})
    assert result == '("Berlin" OR "Munich")'


def test_build_web_query_includes_role_and_location_and_startup_signal():
    query = engine._build_web_query({"query": "AI Engineer", "location": "Berlin", "country": "Germany"}, {})
    assert "Berlin" in query
    assert "startup" in query.lower()


def test_build_ats_query_includes_known_ats_site_filters():
    query = engine._build_ats_query({"query": "AI Engineer", "location": "Berlin", "country": "Germany"}, {})
    assert "site:boards.greenhouse.io" in query
    assert "site:jobs.lever.co" in query
