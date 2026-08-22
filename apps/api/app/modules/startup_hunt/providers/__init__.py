"""Startup Hunt provider modules - one file per external discovery source.

Unlike job_search's providers (one uniform fetch(payload) signature), these
mirror engine.py's existing per-source-type dispatch shape instead of
forcing a shared ProviderSpec abstraction that doesn't actually fit: ATS
providers (greenhouse/lever/ashby) fetch one configured company board at a
time (fetch(client, source)), while theirstack/google_web run one broad
search per hunt (fetch(client, source, payload, strategy)). engine.py's
_fetch_source() dispatch table calls into these directly, keyed by
source.type, exactly as it did with the old inline functions - only the
function bodies moved, not the dispatch shape.

Each module exposes is_available() -> bool, a config-driven kill switch
(server-side only - there is no per-request "provider enabled" toggle
anymore, unlike the old per-search bucket bools).

Deliberately not ported here (left untouched in engine.py, or dropped
entirely) - see docs/ for the reasoning:
- apify_actor, indeed_search: run via third-party Apify actors; Indeed's own
  ToS explicitly prohibits scraping, and the general "startup discovery"
  actor's underlying behavior isn't verifiable from here. Not carried
  forward even as disabled files.
- web_search, ats_discovery: both fall back to scraping a search engine's
  raw HTML results page when Google CSE isn't configured - the CSE-based
  logic they'd otherwise share with google_web.py was extracted into that
  file; the scrape-fallback was dropped, not ported.
- startup_company, startup_directory (crawler/StartupMap buckets): not
  "providers" in this sense at all - they consume user-curated
  StartupHuntSource DB rows rather than calling a discrete external API.
"""
