# Recent Job Search — Production Hardening Playbook

**Status:** Production-ready (2026-08-21)

This documents what took Recent Job Search from "working" to production-grade,
organized by category so the same checklist can be applied to other tools
(Startup Hunt, Startup Scout, LinkedIn Fill, Bulk Email, etc). Each section
says what was done, why, where in the code, and how it was verified — live
verification, not just "should work," since several of these fixes were only
found by testing against real external APIs and the real DB/Redis instances.

---

## Quick checklist for hardening another tool

- [ ] Every external API call wrapped so one provider's failure can't take down the others
- [ ] Every external API call has a real timeout, not just relying on defaults
- [ ] A circuit breaker (or equivalent) for a provider that starts hard-failing repeatedly
- [ ] If there's more than one data source, is dedup actually correct across sources (not just within one)?
- [ ] Every cache layer's key includes exactly the fields that vary the result — no more, no less
- [ ] Every text field has both a length bound and (where relevant) a value-range check, backend AND frontend
- [ ] Every DB query pattern has a matching index — check `EXPLAIN`, not just "there's an index somewhere"
- [ ] Rate limiting fails in the correct direction for the operation's cost (see "Rate limiting" below)
- [ ] A cold cache under concurrent identical requests doesn't fan out N times (single-flight)
- [ ] If a data source has a metered/paid quota, cheaper sources are tried first
- [ ] AI calls use the right model tier for the task — a reasoning model on a tight token budget silently returns empty output instead of failing loudly (see "AI provider layer")
- [ ] Mobile viewport tested at 375px, not just resized from desktop

---

## 1. Multi-provider architecture

**Pattern**: `providers/` folder, one file per external data source, a shared
`ProviderSpec` registry (`providers/__init__.py`) instead of hardcoding
per-provider branches into the service layer.

```
job_search/providers/
  base.py           # shared RawJobListing contract, ProviderError, canonicalize_job_url
  adzuna.py         # fetch(), is_available(), supports_country()
  bundesagentur.py  # same shape
  arbeitnow.py      # same shape
  __init__.py       # ProviderSpec dataclass, PROVIDERS list, applicable_providers()
```

Adding a 4th provider means writing one file matching the same three-function
contract and adding one `ProviderSpec` entry — nothing in `service.py`,
`scoring.py`, or `dedup.py` changes. This paid off directly: Arbeitnow was
added without touching the scoring/caching/dedup layers at all.

## 2. Failure isolation

`asyncio.gather()` **propagates the first exception from any task and
cancels the others** — so without a wrapper, one provider returning
malformed JSON would take down a search that had perfectly good results from
every other provider. Fix: `_fetch_provider_safe()` catches broadly
(`except Exception`, not just the provider's own `ProviderError`), because a
provider's `fetch()` wraps its *anticipated* failures but not e.g. an
unexpected field shape in `response.json()`.

**Verified**: simulated a provider raising a bare `KeyError` mid-fan-out —
confirmed the other providers' results still came back.

## 3. Circuit breaker per provider

If a provider starts hard-failing (an unofficial API changing shape, like
Bundesagentur's `/pc/v4` → `/pc/v6` move mid-session), every affected search
would otherwise still pay the full request timeout on a call that's
essentially guaranteed to fail, until someone notices and flips a kill
switch by hand.

Redis-backed, fails open on a Redis error (a broken breaker must never block
a provider that might be healthy):
- 3 failures within a 5-minute window trips it
- once tripped, skip live calls for 3 minutes
- one success immediately resets the failure count

Code: `providers/__init__.py::circuit_is_open()` / `record_provider_result()`,
called from `service.py::_fetch_provider_safe()`.

**Verified**: forced 3 failures, confirmed the 4th call never touched the network.

## 4. Cross-provider deduplication

A single fingerprint (canonical URL) works with one provider; breaks with
more than one, since each provider hands out its own redirect/tracking URL
for the same real posting. Fix (`dedup.py`): union-find over **multiple**
fingerprint keys per item — canonical URL *and* a normalized
company+role+location semantic key — so a job matched via one provider's URL
and another's semantic key still merges into one group. Guards against
generic placeholder company names (`"unknown company"`, `"confidential"`)
feeding the semantic key, which would otherwise merge unrelated postings.

This mirrors `startup_hunt/engine.py`'s already-proven `_dedupe_opportunities`
— don't re-invent this pattern per tool, reuse the shape.

## 5. Cost-aware fetch ordering

Metered providers (Adzuna, in this case) were being called on *every*
shortfall regardless of whether a free provider alone would have covered it
— real, unnecessary cost with no protection against quota exhaustion.

Fix: `ProviderSpec.is_metered: bool`. On a shortfall, free providers are
fetched and scored first; metered providers are only called for whatever
shortfall remains after that.

**Verified**: with a free provider returning enough results, confirmed the
metered provider was never invoked.

**Apply elsewhere**: check every tool that fans out to multiple external
APIs for this same blind spot — it's easy to miss because it doesn't fail
loudly, it just quietly burns quota.

## 6. Two-layer caching

1. **Redis response cache** — exact-match on the full search signature
   (`query|location|country|posted_within_hours|remote_only|result_limit`,
   hashed), short TTL (15 min). Cheapest possible hit.
2. **Postgres `jobs` table** — broader candidate pool (country + keyword
   filtered), DB-first: only call live providers for the shortfall after
   scoring DB candidates. 14-day TTL, shared across Job Search *and*
   Startup Hunt (same table, `origin_tool` column distinguishes writers).

Getting the cache key right matters as much as having a cache: it must
include every field that changes the result and *nothing* that doesn't. A
free-text field like `preferences_prompt` was deliberately kept **out** of
the response-cache key — it only affects post-fetch scoring/ranking, not
which raw jobs exist, so including it would have fragmented the cache for no
benefit.

## 7. Prompt-parse caching (shared across tools)

Separate from the job cache: `preferences_prompt`/`strategy_prompt` free-text
fields get parsed into structured JSON via an LLM call on every request, with
no caching at all — found by tracing why this cost showed up on every
identical repeated search. Fixed with a **shared** helper
(`app/services/cache.py::cached_prompt_parse()`) rather than a one-off in
`job_search`, because `startup_hunt/engine.py::parse_strategy_prompt` had the
exact same shape (same JSON-extraction pattern, same missing cache). Hashed
by `namespace + prompt text`, so two tools' prompts never collide.

**Verified**: repeat call with identical prompt text went from ~1.2s
(LLM round trip) to ~0.25s (cache hit), byte-identical result.

**Apply elsewhere**: grep for other `ai_provider.generate_text(...)` call
sites that parse a free-text field into structured JSON before this doc gets
out of date — this exact pattern is easy to copy-paste into a new tool
without the caching.

## 8. Single-flight lock (thundering herd protection)

Without this, N concurrent identical searches on a cold cache each
independently fan out to every provider — wasteful, and worse under a
popular query at real traffic.

Redis `SET NX EX` lock around the cache-miss path. Only the lock-holder does
the real DB+provider work; followers poll briefly (0.5s interval, 10s max
wait) for the leader's result to land in the response cache and reuse it. No
explicit unlock — it just expires (Upstash's REST API doesn't offer a clean
compare-and-delete, and a slightly longer free-up window is a fine trade for
avoiding a release-that-isn't-mine race). Fails open (acts as leader) on a
Redis error; a follower that times out waiting falls through to doing its
own fetch rather than hanging forever on a stuck leader.

**Verified**: 5 concurrent identical searches → exactly 1 live provider call,
all 5 got correct results.

## 9. DB indexing for the actual query pattern

`query_job_cache_candidates` filters with `title.ilike('%token%')` —
a **leading-wildcard** ILIKE can't use a plain B-tree index at all (a B-tree
is sorted; "could be anywhere in the string" has no sorted position to jump
to), so it was a full table scan waiting to happen once `jobs` had real
volume. Confirmed live: no `pg_trgm` extension was even installed.

Fix: `pg_trgm` extension + GIN trigram indexes on `title`/`description`
(migration `a22ae866fa45`). Declared identically in the SQLAlchemy model's
`__table_args__` too — otherwise a future `alembic revision --autogenerate`
would propose dropping an index it doesn't know about.

**Apply elsewhere**: any tool doing `ILIKE '%...%'` against a growing table
needs this same check. A B-tree "index exists" is not the same as "this
query pattern can use it."

## 10. AI provider layer (shared, not job-search-specific — but found here)

- **`generate_text`/`stream_text` gained a `tier` parameter** (`"heavy"` /
  `"light"`). A reasoning model (Groq's `openai/gpt-oss-20b`) spends its
  `max_tokens` budget on invisible chain-of-thought before writing an
  answer — on a tight budget (a 250-token JSON extraction call), it can
  return **empty** and *still count as a successful response* unless you
  check for it. `tier="light"` routes small extraction/classification tasks
  to a non-reasoning model instead (currently `allam-2-7b` on Groq).
- **Empty completions are now treated as failures**, not successes — retries
  the next provider in the fallback chain, matching how `stream_text`
  already handled an empty stream.
- **Any 4xx (not just 429) now retries the next provider.** The prior
  assumption ("a 4xx means the request itself is bad, don't retry elsewhere")
  doesn't hold when every call site always sends a well-formed payload — in
  practice a 4xx here always meant a provider-specific config problem (stale
  model ID, no access), which is exactly the case where the next provider
  *would* help. Caught live: a Groq `model_not_found` 404 was silently
  skipping the entire fallback chain.
- **Provider fallback chain simplified**: Groq (primary) → OpenRouter (sole
  fallback), Cerebras and HuggingFace dropped. Verified every model ID
  against the actual live account/catalog rather than trusting
  docs/memory — caught two stale model IDs (Groq's assumed light model,
  Cerebras's configured model) and one free-tier model that was globally
  congested on OpenRouter at test time (`gemma-4-31b-it:free` → swapped to
  `nemotron-3-super-120b-a12b:free` after live-comparing both).

**Apply elsewhere**: any tool calling `ai_provider.generate_text()` with a
small `max_tokens` on the default (heavy) tier should pass `tier="light"` if
the task is extraction/classification, not prose generation.

## 11. Rate limiting — a design question, not fully resolved

`_check_rate_limit_fail_open()` runs **before** the cache-key check, so a
search fully served by cache (near-zero cost) counts against the user's
daily quota the same as a fully fresh, expensive search. Left as-is —
could be intentional (quota as a UX promise, not a cost-tracking mechanism)
or an oversight. **Flagging for whoever hardens the next tool**: decide this
deliberately, don't just copy the pattern without thinking about it.

## 12. Input validation

Every field in `schemas.py` has both a length bound and a value-range check
(`result_limit` 1-50, `posted_within_hours` 1-720, `preferences_prompt`
≤500 chars, JSON payload byte caps on free-form fields). Matches CLAUDE.md's
"input length limits" rule. This was already solid when audited — nothing to
fix, but worth using as the reference shape for other tools' schemas.

## 13. UI/UX production polish

- **Mobile sidebar**: converted from always-visible to a responsive
  drawer — hamburger + small logo bar under `md:`, sticky/normal-flow
  above it. Bug found: an icon-only collapsed state was rendering *while*
  the mobile drawer was also open, traced to a missing `&& !mobileOpen`
  guard.
- **CSS `@layer` bug**: a component class was declared in Tailwind's
  `utilities` layer instead of `components` — same layer as Tailwind's own
  `hidden`/`sm:flex` utilities, so override behavior became
  source-order-dependent instead of "utilities always win." Symptom looked
  like a JSX/markup bug; root cause was the CSS cascade layer.
- **Sticky filter panel clipping**: a `position: sticky` element only
  "unsticks" once its *containing block's* bottom edge nears the viewport —
  a filter panel taller than the viewport, inside a grid cell stretched to
  match a tall results column, had its submit button permanently
  off-screen. Fixed with `max-h-[calc(100vh-2rem)]` + internal
  `overflow-y-auto`.
- **Breakpoint mismatch**: nested content's own `sm:`/`md:` classes respond
  to *viewport* width, not the parent container's actual rendered width —
  broke on iPad-portrait when a two-column grid switched at `md:` (768px)
  while content inside assumed full-viewport space at its own `sm:` (640px).
  Fixed by moving the whole grid switch to `lg:` (1024px).
- **Toast redesign**: `TOAST_REMOVE_DELAY` was a leftover shadcn-template
  default of 300000ms (5 minutes) — fixed to 600ms, plus a full visual
  redesign (top-right, thin accent-bar card, small-distance slide+fade).

**Apply elsewhere**: the CSS layer bug and the sticky-container bug are both
the kind of thing that "looks like a markup bug" but isn't — check the
actual cascade/containing-block mechanics before assuming the JSX is wrong.

---

## What's explicitly *not* done (accepted tradeoffs)

- No per-tool cost dashboard/budget alerting — provider quota exhaustion is
  still discovered by a request failing, not proactively flagged.
- OpenRouter's free-tier model has no uptime/SLA guarantee (documented gap
  in OpenRouter's own docs) — acceptable for a rarely-invoked fallback, not
  acceptable if traffic patterns change and it becomes load-bearing.
- Rate-limit-counts-cache-hits (see §11) — deliberately left as an open
  question, not a resolved decision.
