# Startup Scout: API Reference

**Base URL**: `/api/startup-scout` (no `/v1/` - corrected 2026-11-06; every
endpoint below was previously documented under a `/v1/` prefix that
doesn't exist in `app/main.py`'s actual router mount)  
**Authentication**: Bearer JWT Token in `Authorization` header.

---

## 1. Discover Startups (Phase A & B)

### `POST /api/startup-scout/search`

Executes multi-directory site search against DuckDuckGo HTML endpoints and extracts executive contacts.

#### Request Body (`application/json`)
```json
{
  "location": "Berlin",
  "funding_stages": ["seed", "series-a"],
  "industry": "Artificial Intelligence",
  "limit": 30
}
```

#### Response (`200 OK`)
```json
{
  "companies": [
    {
      "name": "KiteAI",
      "description": "Next-generation developer workflow automation.",
      "what_they_do": "Automates developer code reviews using LLM agents.",
      "funding_stage": "seed",
      "size_range": "11-50",
      "location": "Berlin, Germany",
      "website": "https://kiteai.dev",
      "linkedin_url": "https://linkedin.com/company/kiteai",
      "contacts": [
        {
          "name": "Sarah Jenkins",
          "title": "Co-Founder & CEO",
          "email": "sarah@kiteai.dev",
          "linkedin_url": "https://linkedin.com/in/sarahjenkins-ceo",
          "confidence": 0.9,
          "source": "apollo"
        }
      ]
    }
  ],
  "count": 1,
  "meta": {
    "cached": false,
    "directories_searched": ["crunchbase.com", "eu-startups.com"],
    "total_raw_found": 14
  }
}
```

---

## 2. Saved Scout Companies

### `POST /api/startup-scout/companies`
Saves a discovered company profile to the user's dashboard.

### `GET /api/startup-scout/companies`
Lists all saved startup company profiles for the current user. Supports
optional cursor pagination (`?limit=50&cursor=...`, see
`data_flow_and_schema.md` for the keyset shape) - omit both params for the
original unbounded behavior.

### `GET /api/startup-scout/companies/{company_id}`
Returns details for a single saved company, including enrichment
`crawl_status` (`pending`, `crawling`, `enriched`, `partial`, `failed` -
this doc previously omitted `partial`, returned when a crawl completes
with zero new contacts found rather than erroring).

### `DELETE /api/startup-scout/companies/{company_id}`
Deletes a saved company and cascades deletion to associated contacts. Also
signals cancellation (via the same Redis key `/stop` below uses) in case a
crawl is in flight for this company when it's deleted.

---

## 3. Contact Enrichment (Phase B)

> **UI status (2026-11-06): disabled, not removed.** The Tracker frontend
> no longer exposes a way to trigger these endpoints - "Start Crawl"/
> "Re-crawl"/"Stop" render as disabled items under an "Advanced crawl ·
> Currently unavailable" menu (see `tracker/page.tsx`'s Scout tab). The
> default, always-available path for finding a company's founders is now
> a client-side "Find Founders" link that opens a pre-filled Google search
> in the user's own browser - zero backend calls, zero cost, zero DDG
> rate-limit risk. The endpoints below are fully implemented and were
> verified live against the real stack in this same pass; they're just
> not reachable from the product UI right now. See
> `production_hardening_notes.md` for why (cost/shared-IP-risk vs. low
> adoption) and how to re-enable them if wanted later.

### `POST /api/startup-scout/companies/{company_id}/crawl`
Runs as a real ARQ job (`run_crawl`, 600s timeout), not a FastAPI
`BackgroundTask` - a crawl is sequential DDG + (conditionally) Apollo
calls with deliberate pacing sleeps between each, realistically 30s-2min+
for a company with several contacts. `crawl_status` is flipped to
`crawling` and committed **synchronously**, before the job is even
enqueued - a rapid second click sees the committed status and gets a
clean `409`, rather than racing a second crawl for the same company.
Rate-limited at `rate_limit_startup_scout_crawl_per_day` (default 30)
per user, plus the shared burst-window guard every endpoint in this app
gets.

Pipeline, in order (see `service.py::run_crawl`):
1. `web_search_contacts` (DDG) - general web + LinkedIn + Crunchbase
   queries, free.
2. If zero contacts found: `apollo_search_contacts` fallback - gated by a
   **whole-deployment** daily budget (`apollo_daily_call_budget`, default
   200, via `check_tool_budget`), separate from the per-user rate limit
   above, since Apollo is a paid per-call API.
3. LinkedIn-URL enrichment + independent verification per contact (DDG).
4. If fewer than `MIN_VERIFIED_CONTACTS` (2) survive verification: Apollo
   supplement, then enrich/verify **only the newly-added contacts** (not
   a full re-pass over everyone already processed).

Final `crawl_status`: `enriched` (≥1 contact saved), `partial` (ran clean,
found nothing), or `failed` (an exception was caught - network/parsing
error, not "found nothing").

Old contacts are only deleted once a new source actually returns
something to replace them with - a crawl that finds nothing leaves prior
data untouched instead of wiping it for an empty result.

### `POST /api/startup-scout/companies/{company_id}/stop`
Signals cancellation via a Redis key (`scout_crawl_cancel:{company_id}`,
~30min TTL) - `run_crawl` checks it between every contact, not an
in-process flag, so this works regardless of which worker process picked
up the job. Returns `409` if the company isn't currently `crawling`.

### `GET /api/startup-scout/companies/{company_id}/contacts`
Returns previously-saved contacts for a company (`name`, `title`, `email`,
`linkedin_url`, `is_verified`, `verification_url`), ordered by confidence
descending. Works regardless of the UI-disable above - this only reads
already-saved data, it doesn't trigger a new crawl.
