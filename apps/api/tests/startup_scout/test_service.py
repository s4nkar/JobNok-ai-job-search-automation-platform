"""Unit tests for the pure, DB-free helpers in startup_scout.service.

Everything else in service.py (search_startups_stream, save_company,
list_companies, run_crawl, ...) needs a real AsyncSession / DB and is out of
scope here — there is no app-level DB fixture in this repo yet.
"""

from app.modules.startup_scout import service


def test_response_cache_key_is_order_insensitive_for_funding_stages():
    key_a = service._response_cache_key("Berlin", ["seed", "angel"], "ai", 50)
    key_b = service._response_cache_key("Berlin", ["angel", "seed"], "ai", 50)
    assert key_a == key_b


def test_response_cache_key_is_case_insensitive():
    key_a = service._response_cache_key("Berlin", ["Seed"], "AI", 50)
    key_b = service._response_cache_key("berlin", ["seed"], "ai", 50)
    assert key_a == key_b


def test_response_cache_key_differs_on_limit():
    key_a = service._response_cache_key("Berlin", ["seed"], "ai", 50)
    key_b = service._response_cache_key("Berlin", ["seed"], "ai", 100)
    assert key_a != key_b


def test_response_cache_key_differs_on_location():
    key_a = service._response_cache_key("Berlin", ["seed"], "ai", 50)
    key_b = service._response_cache_key("Munich", ["seed"], "ai", 50)
    assert key_a != key_b


def test_response_cache_key_has_fixed_prefix():
    key = service._response_cache_key("Berlin", [], "", 50)
    assert key.startswith("startup_scout:")


def test_dedupe_key_prefers_real_registrable_domain():
    company = {"domain": "acme.com", "website": "https://acme.com/about", "name": "Acme"}
    assert service._dedupe_key(company) == "acme.com"


def test_dedupe_key_falls_back_to_website_for_directory_domain():
    # crunchbase.com is a known startup-directory host (see
    # engine._DIRECTORY_PROFILE_PATHS) — every company scraped from it shares
    # that one bare domain, so the dedupe key must be the full profile URL
    # instead, or distinct companies collapse into "duplicates" of each other.
    company_a = {
        "domain": "crunchbase.com",
        "website": "https://www.crunchbase.com/organization/foo",
        "name": "Foo",
    }
    company_b = {
        "domain": "crunchbase.com",
        "website": "https://www.crunchbase.com/organization/bar",
        "name": "Bar",
    }
    assert service._dedupe_key(company_a) != service._dedupe_key(company_b)
    assert service._dedupe_key(company_a) == "https://www.crunchbase.com/organization/foo"


def test_dedupe_key_falls_back_to_name_when_no_domain_or_website():
    company = {"domain": "", "website": "", "name": "Acme Inc"}
    assert service._dedupe_key(company) == "acme inc"
