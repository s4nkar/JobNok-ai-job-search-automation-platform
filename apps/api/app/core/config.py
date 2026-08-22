"""Single source of truth for all backend configuration.

Every field is populated from an environment variable of the same name
(upper-cased). pydantic-settings reads them from the OS environment first,
then falls back to the .env file. The Python default (e.g. "") is ONLY used
if the variable is absent from both sources — it is never the live value in
a real deployment.

Example: `clerk_issuer` ← CLERK_ISSUER in .env or OS env
"""

from pydantic_settings import BaseSettings
from pydantic import model_validator
from functools import lru_cache
from typing import Self


class Settings(BaseSettings):
    # ── AI Provider ──────────────────────────────────────────────────────────
    # Primary provider. Supported: groq | openrouter
    ai_provider: str = "groq"
    # Comma-separated fallback chain tried in order on rate-limit/5xx/timeouts.
    # Example: "openrouter". Leave empty to disable fallback.
    ai_fallback_chain: str = "openrouter"
    # Per-call timeout (seconds) — applies to non-streaming generate_text only.
    ai_request_timeout_seconds: int = 60
    # Shared cache for free-text-prompt-to-structured-JSON parsing (e.g. job_search's
    # preferences_prompt, startup_hunt's strategy_prompt) — same input text always
    # extracts to the same structured filters, so no need to re-hit the LLM per request.
    prompt_parse_cache_ttl_seconds: int = 3600

    # Groq (OpenAI-compatible)
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    # Fast, non-reasoning model for small "light" tier calls (e.g. free-text-prompt
    # extraction) — the heavy model above may be a reasoning model that spends
    # max_tokens on invisible chain-of-thought before writing any answer, which
    # starves short extraction tasks of output entirely. See generate_text(tier=).
    groq_light_model: str = "allam-2-7b"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # OpenRouter (OpenAI-compatible) — sole fallback, used for both tiers since
    # it's rarely invoked (only on a Groq failure). nemotron-3-super is a
    # non-reasoning instruct model - live-tested clean on both a trivial task
    # and the actual JSON-extraction shape. The smaller/more popular free
    # models (gemma-4-31b-it:free, glm-5.2:free) were hitting instant 429s
    # from upstream congestion on OpenRouter's shared free pool at the time
    # of testing - this one wasn't, so it's the more reliable pick for a
    # fallback specifically (rarely used, but must work when it's used).
    openrouter_api_key: str = ""
    openrouter_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # ── Embedding Providers ──────────────────────────────────────────────────
    # Primary embedding provider. Supported: jina | cohere
    # Used by resume↔JD semantic matching. Resume embeddings are cached per
    # resume_hash, so cost is ~600 tokens per tailoring run after the first
    # upload of a given resume.
    embedding_provider: str = "jina"
    embedding_fallback_chain: str = "cohere"
    embedding_request_timeout_seconds: int = 30

    # Jina AI (free tier: 1M tokens/month, no card required)
    jina_api_key: str = ""
    jina_model: str = "jina-embeddings-v3"
    jina_base_url: str = "https://api.jina.ai/v1"

    # Cohere (free tier with rate limits)
    cohere_api_key: str = ""
    cohere_embedding_model: str = "embed-english-v3.0"
    cohere_base_url: str = "https://api.cohere.com/v2"

    # ── Rate Limits (enforced via a Redis fixed window counter, reset at midnight UTC) ──
    # All limits are per-user per-day unless stated otherwise
    rate_limit_linkedin_per_day: int = 10
    rate_limit_resume_per_day: int = 5
    rate_limit_cover_letter_per_day: int = 5
    rate_limit_interview_per_day: int = 10
    rate_limit_salary_per_day: int = 5
    rate_limit_job_search_per_day: int = 10
    rate_limit_job_search_applications_per_day: int = 200
    rate_limit_startup_hunt_per_day: int = 8
    rate_limit_bulk_email_per_campaign: int = 500
    rate_limit_bulk_email_per_month: int = 3000
    # Short-window burst limit, separate from the daily quotas above - caps
    # rapid-fire requests (double-click, retry loop, no search-box debounce)
    # within the same day's allowance. Same limit/window pair reused across
    # tools unless one needs its own.
    rate_limit_burst_limit: int = 3
    rate_limit_burst_window_seconds: int = 10

    # ── LinkedIn Scraping ────────────────────────────────────────────────────
    # Primary scraper — RAPIDAPI_KEY from RapidAPI dashboard
    rapidapi_key: str = ""
    rapidapi_linkedin_host: str = "linkedin-api8.p.rapidapi.com"
    # Fallback scraper — PHANTOMBUSTER_API_KEY from PhantomBuster dashboard
    phantombuster_api_key: str = ""
    phantombuster_agent_id: str = ""
    linkedin_session_cookie: str = ""
    # Shared LinkedIn profile cache TTL (days)
    linkedin_cache_ttl_days: int = 7 

    # ── Job Search ─ providers ──────────────────────────────────────────────
    # Per-provider kill switch, independent of whether credentials are
    # configured - flip to false to pull a provider out of search immediately
    # (e.g. an unofficial API breaking) without touching code or removing keys.
    job_search_adzuna_enabled: bool = True 
    job_search_bundesagentur_enabled: bool = True
    # Arbeitnow has no country field, so it can never reliably participate in
    # the main location-filtered/ranked results - it's shown separately as
    # "bonus" finds instead (title-matched only, location unverified). This
    # toggle still fully disables that section.
    job_search_arbeitnow_enabled: bool = True
    # How many bonus finds to surface per search - deliberately small and
    # randomly sampled from everything that passes the title match (not the
    # top-N by score), since there's no reliable ranking signal without
    # location data to weight against.
    job_search_bonus_jobs_limit: int = 12
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_base_url: str = "https://api.adzuna.com/v1/api"
    # PLACEHOLDER - confirm against the actual Adzuna account's plan quota
    # (dashboard or contract), then set the real number. This is a global
    # budget shared across every user, not a per-user limit - it exists to
    # stop the app's aggregate usage from exhausting Adzuna's own account-level
    # daily quota even when every individual user is well under their own
    # per-day cap (the same failure shape as the Upstash Redis quota
    # exhaustion hit earlier - a shared external resource exhausted by
    # aggregate legitimate use, not abuse). Deliberately set a bit under
    # whatever the real quota is once known, to leave safety margin.
    adzuna_daily_call_budget: int = 200
    # PLACEHOLDER - Bundesagentur is an unofficial/reverse-engineered endpoint
    # (no developer program, no published rate limit) - conservative estimate
    # until either confirmed live or an actual block/429 pattern is observed.
    bundesagentur_daily_call_budget: int = 300
    # Combined external-provider call budget for the whole Job Search tool,
    # across every provider - a cost-governance ceiling distinct from any
    # single provider's own quota. Catches aggregate cost growth that no
    # per-provider budget would (e.g. a provider with no hard external quota
    # of its own still costs real bandwidth/DB writes/compute at volume).
    # Arbeitnow isn't counted here - its own 30-min page cache already bounds
    # it far tighter (~48 real fetches/day) than any budget number would add.
    # PLACEHOLDER - tune from real usage/cost data once available; currently
    # set below the sum of the two per-provider budgets above (500) as a
    # deliberately stricter overall ceiling.
    job_search_tool_daily_budget: int = 400
    job_search_timeout_seconds: int = 12
    # Postgres `jobs` cache row TTL, how long a cached listing is considered fresh.
    job_search_cache_ttl_days: int = 14
    # Redis response cache TTL for identical (query, location, country, ...) searches.
    job_search_response_cache_ttl_seconds: int = 900
    # Caps how much of a user's own job_search_applications history is loaded per
    # request (search's "already applied" lookup, and the applications list endpoint).
    job_search_max_tracked_history: int = 2000
    job_search_applications_page_size_default: int = 50
    job_search_applications_page_size_max: int = 200

    # Startup Hunt v2 seeded sources (global curated + per-user custom) now live in
    # the startup_hunt_sources table (see app/modules/startup_hunt/models.py) —
    # migrated off this env var by alembic/versions/*_add_startup_hunt_sources_table.py.
    startup_hunt_timeout_seconds: int = 20
    startup_hunt_apify_poll_seconds: int = 60
    startup_hunt_total_budget_seconds: int = 30

    # ── Startup Hunt — providers ─────────────────────────────────────────────
    # Per-provider kill switch, server-side only - there is no per-request
    # "provider enabled" toggle anymore (removed from StartupHuntSearchRequest
    # along with the old "Provider controls" UI section). Greenhouse/Lever/Ashby
    # need no credentials (public ATS APIs); TheirStack/Google-web also need
    # their respective keys configured below to actually run even if enabled.
    startup_hunt_greenhouse_enabled: bool = True
    startup_hunt_lever_enabled: bool = True
    startup_hunt_ashby_enabled: bool = True
    # Combined result cap across greenhouse+lever+ashby for one hunt - mirrors
    # the old request-level ats_limit's default (15), now fixed server-side.
    startup_hunt_ats_result_limit: int = 15
    startup_hunt_theirstack_enabled: bool = True
    # Mirrors the old request-level theirstack_limit's default (15).
    startup_hunt_theirstack_result_limit: int = 15
    # Off by default - CSE-only web discovery (see providers/google_web.py for
    # why the scrape-fallback other web-discovery code paths have was dropped
    # rather than ported). Flip on once Google CSE credentials are configured
    # and you actually want this source contributing results.
    startup_hunt_google_web_enabled: bool = False
    startup_hunt_google_web_result_limit: int = 15

    google_cse_api_key: str = ""
    google_cse_cx: str = ""
    apify_api_token: str = ""
    apify_base_url: str = "https://api.apify.com/v2"
    apify_startup_hunt_actor_id: str = ""
    apify_indeed_actor_id: str = ""
    theirstack_api_key: str = ""
    theirstack_base_url: str = "https://api.theirstack.com"
    # TheirStack's free plan hard-caps `limit` at 25 results/page (HTTP 403,
    # error code E-020, "Premium functionality limitation") — any request
    # above this is rejected outright, zeroing the whole bucket. Configurable
    # so upgrading the TheirStack plan doesn't require a code change.
    theirstack_max_page_size: int = 25
    startup_hunt_contact_enrichment_provider: str = ""
    apollo_api_key: str = ""
    people_data_labs_api_key: str = ""
    # Crunchbase Basic API (free tier: 200 searches/month).
    # Used by Startup Scout Phase A for structured EU company discovery.
    # Get from: https://www.crunchbase.com/api
    crunchbase_api_key: str = ""

    # ── Bulk Email ───────────────────────────────────────────────────────────
    # Minimum delay between individual emails to avoid spam flags (seconds)
    bulk_email_min_delay_seconds: int = 20
    # Worker-side token-bucket cap on Resend sends across all campaigns combined
    bulk_email_sends_per_second: int = 5

    # ── Cloudinary (CV photo storage) ───────────────────────────────────────
    # Get from Cloudinary dashboard's Account Details page.
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""

    # ── Clerk (Auth) ─────────────────────────────────────────────────────────
    # JWKS endpoint + issuer for verifying Clerk session tokens (RS256) —
    # both come from the Clerk dashboard's API Keys page. Dev instances serve
    # JWKS at https://<subdomain>.clerk.accounts.dev/.well-known/jwks.json.
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""
    # Svix signing secret for verifying inbound webhooks (app/modules/auth/routes.py).
    clerk_webhook_secret: str = ""

    # ── Database (SQLAlchemy) ────────────────────────────────────────────────
    # Direct Postgres connection string to the same Supabase project, e.g.
    # postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres
    # Use a role that bypasses RLS (table owner or a role with BYPASSRLS) —
    # equivalent posture to the service-role key above. Every query MUST still
    # filter by user_id explicitly via UserScopedRepository (app/shared/repository.py);
    # RLS is not the enforcement layer here.
    database_url: str = ""

    # Session-pooler / direct connection to the same Supabase project (port 5432,
    # not the transaction pooler's 6543). DDL (CREATE INDEX, ALTER TABLE, etc.) is
    # unreliable through the transaction pooler, so Alembic needs this instead.
    migrations_database_url: str = ""

    @property
    def database_url_async(self) -> str:
        """asyncpg driver — used by the FastAPI app and ARQ worker (app/core/database.py)."""
        return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    @property
    def migrations_database_url_sync(self) -> str:
        """psycopg driver over the session-pooler/direct URL — used by Alembic only."""
        return self.migrations_database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    # ── Upstash Redis ────────────────────────────────────────────────────────
    # REST-based Redis for rate limiting — get from Upstash console
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""
    # TCP Redis URL for the ARQ broker (can reuse Upstash rediss:// URL)
    redis_url: str = "redis://localhost:6379/0"

    # ── Resend ───────────────────────────────────────────────────────────────
    resend_api_key: str = ""
    resend_from_email: str = "noreply@jobnok.app"
    resend_from_name: str = "JobNok"

    # ── App ──────────────────────────────────────────────────────────────────
    app_url: str = "http://localhost:3000"
    # Shared secret header sent from Next.js → FastAPI on every request
    backend_api_secret: str = ""

    # ── Sentry (optional) ────────────────────────────────────────────────────
    sentry_dsn: str = ""

    # pydantic-settings: reads .env file + OS env vars automatically
    model_config = {"env_file": ".env", "case_sensitive": False}

    @model_validator(mode="after")
    def _validate_required_keys(self) -> Self:
        """Fail fast at startup if critical environment variables are missing."""
        missing: list[str] = []

        # AI provider key — validate the primary provider has its credential.
        # Fallback providers are best-effort; missing keys just skip them at runtime.
        provider_key_map = {
            "groq": ("GROQ_API_KEY", self.groq_api_key),
            "openrouter": ("OPENROUTER_API_KEY", self.openrouter_api_key),
        }
        primary = self.ai_provider.lower()
        if primary in provider_key_map:
            env_name, value = provider_key_map[primary]
            if not value:
                missing.append(f"{env_name} (required when AI_PROVIDER={primary})")

        # Cloudinary — always required
        if not self.cloudinary_cloud_name:
            missing.append("CLOUDINARY_CLOUD_NAME")
        if not self.cloudinary_api_key:
            missing.append("CLOUDINARY_API_KEY")
        if not self.cloudinary_api_secret:
            missing.append("CLOUDINARY_API_SECRET")

        # Clerk — always required
        if not self.clerk_jwks_url:
            missing.append("CLERK_JWKS_URL")
        if not self.clerk_issuer:
            missing.append("CLERK_ISSUER")
        if not self.clerk_webhook_secret:
            missing.append("CLERK_WEBHOOK_SECRET")

        # Upstash Redis — always required
        if not self.upstash_redis_rest_url:
            missing.append("UPSTASH_REDIS_REST_URL")
        if not self.upstash_redis_rest_token:
            missing.append("UPSTASH_REDIS_REST_TOKEN")

        if missing:
            formatted = "\n  - ".join(missing)
            raise ValueError(
                f"\n\nMissing required environment variables:\n  - {formatted}\n\n"
                "Add them to your .env file (apps/api/.env) or set them as OS env vars.\n"
                "See apps/api/.env.example for the full variable reference.\n"
            )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
