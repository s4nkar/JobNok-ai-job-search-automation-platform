"""Unit tests for resolver.py - the "smart add" company-name-to-ATS-board
resolution behind My Sources. slugify/slug_variants/_match_ats_url are pure
functions. try_direct_resolve/try_fallback_resolve are exercised with
httpx.AsyncClient monkeypatched so no real network call happens, mirroring
test_ai_provider.py's httpx.AsyncClient.post monkeypatch style."""

import httpx

from app.modules.startup_hunt import resolver


# ── pure slug helpers ────────────────────────────────────────────────────

def test_slugify_lowercases_and_hyphenates():
    assert resolver.slugify("Acme AI Labs") == "acme-ai-labs"


def test_slugify_strips_non_alphanumeric():
    assert resolver.slugify("Acme & Co.!") == "acme-co"


def test_slugify_collapses_repeated_separators_and_trims_edges():
    assert resolver.slugify("  -Acme--Inc-  ") == "acme-inc"


def test_slug_variants_includes_base_and_no_hyphen_form():
    variants = resolver.slug_variants("Acme Labs")
    assert "acme-labs" in variants
    assert "acmelabs" in variants


def test_slug_variants_strips_known_suffixes():
    variants = resolver.slug_variants("Acme Inc")
    assert "acme" in variants


def test_slug_variants_deduplicates_and_preserves_order():
    variants = resolver.slug_variants("Acme")
    assert variants == list(dict.fromkeys(variants))
    assert variants[0] == "acme"


def test_match_ats_url_detects_greenhouse_board():
    result = resolver._match_ats_url("https://boards.greenhouse.io/acme")
    assert result.type == "greenhouse"
    assert result.slug == "acme"


def test_match_ats_url_detects_lever_board():
    result = resolver._match_ats_url("https://jobs.lever.co/acme")
    assert result.type == "lever"
    assert result.slug == "acme"


def test_match_ats_url_detects_ashby_board():
    result = resolver._match_ats_url("https://jobs.ashbyhq.com/acme")
    assert result.type == "ashby"
    assert result.slug == "acme"


def test_match_ats_url_none_for_unrelated_url():
    assert resolver._match_ats_url("https://acme.com/careers") is None


# ── async resolution paths (httpx monkeypatched, no network) ───────────

def _patch_probe_only_matches(monkeypatch, matching_type: str, matching_slug: str):
    """Make _probe_slug true only for one exact (type, slug) pair - avoids
    needing to fake provider.fetch()'s own response shape."""

    async def fake_probe_slug(client, ats_type, slug, company):
        return ats_type == matching_type and slug == matching_slug

    monkeypatch.setattr(resolver, "_probe_slug", fake_probe_slug)


async def test_try_direct_resolve_plain_name_resolves_via_slug_guess(monkeypatch):
    _patch_probe_only_matches(monkeypatch, "lever", "acme")
    result = await resolver.try_direct_resolve("Acme")
    assert result is not None
    assert result.type == "lever"
    assert result.slug == "acme"


async def test_try_direct_resolve_plain_name_returns_none_when_no_board_matches(monkeypatch):
    _patch_probe_only_matches(monkeypatch, "lever", "something-else")
    result = await resolver.try_direct_resolve("Acme")
    assert result is None


async def test_try_direct_resolve_url_input_uses_pattern_match_without_probing_other_types(monkeypatch):
    calls = []

    async def fake_probe_slug(client, ats_type, slug, company):
        calls.append((ats_type, slug))
        return True

    monkeypatch.setattr(resolver, "_probe_slug", fake_probe_slug)
    result = await resolver.try_direct_resolve("https://boards.greenhouse.io/acme")
    assert result.type == "greenhouse"
    assert result.slug == "acme"
    assert calls == [("greenhouse", "acme")]


async def test_try_direct_resolve_url_input_falls_back_to_careers_page_scan(monkeypatch):
    async def fake_get(self, url, timeout=8.0, follow_redirects=True):
        return httpx.Response(200, text='<a href="https://jobs.lever.co/acme">Jobs</a>', request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    _patch_probe_only_matches(monkeypatch, "lever", "acme")

    result = await resolver.try_direct_resolve("https://acme.com/careers")
    assert result is not None
    assert result.type == "lever"
    assert result.slug == "acme"


async def test_try_direct_resolve_url_input_none_when_careers_page_fetch_fails(monkeypatch):
    async def failing_get(self, url, timeout=8.0, follow_redirects=True):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx.AsyncClient, "get", failing_get)

    result = await resolver.try_direct_resolve("https://acme.com/careers")
    assert result is None


async def test_try_fallback_resolve_reuses_direct_resolve_result(monkeypatch):
    _patch_probe_only_matches(monkeypatch, "ashby", "acme")
    result = await resolver.try_fallback_resolve("Acme")
    assert result is not None
    assert result.type == "ashby"
    assert result.slug == "acme"


async def test_try_fallback_resolve_tries_slug_variants_when_direct_fails(monkeypatch):
    _patch_probe_only_matches(monkeypatch, "greenhouse", "acme-labs")
    result = await resolver.try_fallback_resolve("Acme Labs Inc")
    assert result is not None
    assert result.type == "greenhouse"
    assert result.slug == "acme-labs"


async def test_try_fallback_resolve_url_input_does_not_retry(monkeypatch):
    calls = []

    async def fake_probe_slug(client, ats_type, slug, company):
        calls.append((ats_type, slug))
        return False

    async def failing_get(self, url, timeout=8.0, follow_redirects=True):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(resolver, "_probe_slug", fake_probe_slug)
    monkeypatch.setattr(httpx.AsyncClient, "get", failing_get)
    result = await resolver.try_fallback_resolve("https://acme.com/careers")
    assert result is None
    # try_direct_resolve already retried the URL path in full; try_fallback_resolve
    # must not probe it again as a plain company name.
    assert calls == []
