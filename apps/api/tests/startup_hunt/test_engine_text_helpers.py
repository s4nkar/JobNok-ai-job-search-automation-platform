"""Unit tests for engine.py's pure text/URL/date normalization helpers -
no I/O, no mocking needed. These underpin dedupe keys, scoring, and source
matching, so a regression here silently corrupts everything downstream."""

from datetime import timezone

from app.modules.startup_hunt import engine


def test_canonicalize_url_lowercases_scheme_and_host():
    assert engine.canonicalize_url("HTTPS://Example.COM/path") == "https://example.com/path"


def test_canonicalize_url_strips_utm_params():
    url = "https://example.com/job?utm_source=newsletter&utm_campaign=x&id=5"
    assert engine.canonicalize_url(url) == "https://example.com/job?id=5"


def test_canonicalize_url_strips_known_tracking_params():
    url = "https://boards.greenhouse.io/acme/jobs/123?gh_jid=123&gh_src=abc"
    assert engine.canonicalize_url(url) == "https://boards.greenhouse.io/acme/jobs/123"


def test_canonicalize_url_strips_fragment():
    assert engine.canonicalize_url("https://example.com/path#section") == "https://example.com/path"


def test_canonicalize_url_preserves_other_query_params_order_independent_value():
    url = "https://example.com/path?b=2&a=1"
    result = engine.canonicalize_url(url)
    assert "a=1" in result and "b=2" in result


def test_normalize_text_collapses_whitespace_and_lowercases():
    assert engine.normalize_text("  Hello   World  ") == "hello world"


def test_tokenize_filters_single_char_tokens():
    assert engine.tokenize("A Python 3 dev") == ["python", "dev"]


def test_tokenize_lowercases_and_splits_on_non_alnum():
    assert engine.tokenize("AI/ML-Engineer") == ["ai", "ml", "engineer"]


def test_extract_domain_strips_www_and_lowercases():
    assert engine.extract_domain("https://WWW.Example.com/careers") == "example.com"


def test_extract_domain_adds_scheme_when_missing():
    assert engine.extract_domain("example.com/jobs") == "example.com"


def test_extract_domain_none_for_none_input():
    assert engine.extract_domain(None) is None


def test_parse_dt_handles_zulu_suffix():
    dt = engine.parse_dt("2024-01-01T12:00:00Z")
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    assert dt.hour == 12


def test_parse_dt_assumes_utc_when_naive():
    dt = engine.parse_dt("2024-01-01T12:00:00")
    assert dt.tzinfo == timezone.utc


def test_parse_dt_returns_none_for_invalid_string():
    assert engine.parse_dt("not-a-date") is None


def test_parse_dt_returns_none_for_empty_or_none():
    assert engine.parse_dt(None) is None
    assert engine.parse_dt("") is None


def test_now_utc_is_timezone_aware():
    assert engine.now_utc().tzinfo == timezone.utc


def test_country_aliases_expands_known_country_name_to_code_and_back():
    aliases = engine._country_aliases("Germany")
    assert "germany" in aliases
    assert "de" in aliases
    assert "deutschland" in aliases


def test_country_aliases_treats_two_letter_input_as_code():
    aliases = engine._country_aliases("gb")
    assert "gb" in aliases
    assert "united kingdom" in aliases


def test_country_aliases_empty_for_blank_input():
    assert engine._country_aliases("") == set()


def test_location_matches_direct_substring():
    assert engine._location_matches("berlin", "", "berlin, germany", {}, False) is True


def test_location_matches_by_country_alias():
    assert engine._location_matches("", "germany", "some city, de", {}, False) is True


def test_location_matches_remote_eu_role_matches_eu_country_target():
    assert engine._location_matches("", "germany", "remote, europe", {}, True) is True


def test_location_matches_remote_without_country_target_always_matches():
    assert engine._location_matches("", "", "anywhere remote", {}, True) is True


def test_location_matches_false_when_nothing_lines_up():
    assert engine._location_matches("berlin", "germany", "paris, fr", {}, False) is False


def test_normalize_role_query_aliases_expands_abbreviations():
    assert "ai engineer" in engine._normalize_role_query_aliases(" ai eng ")


def test_ai_engineer_family_variants_includes_input_and_family():
    variants = engine._ai_engineer_family_variants("ML Engineer")
    assert "ML Engineer" in variants
    assert "AI Engineer" in variants
    assert "LLM Engineer" in variants


def test_ai_engineer_family_variants_deduplicates_and_caps_at_eight():
    variants = engine._ai_engineer_family_variants("AI Engineer")
    assert len(variants) <= 8
    assert len(variants) == len(set(v.lower() for v in variants))


def test_ai_engineer_family_variants_falls_back_to_query_when_no_family_match():
    variants = engine._ai_engineer_family_variants("Barista")
    assert variants == ["Barista"]
