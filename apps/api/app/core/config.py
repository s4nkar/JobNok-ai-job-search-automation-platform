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
    # Primary provider. Supported: groq | cerebras | anthropic | huggingface
    ai_provider: str = "groq"
    # Model for the primary provider (Anthropic-style id when ai_provider=anthropic,
    # otherwise ignored — provider-specific *_model fields below are authoritative).
    ai_model: str = "claude-sonnet-4-6"
    # Comma-separated fallback chain tried in order on rate-limit/5xx/timeouts.
    # Example: "cerebras,huggingface". Leave empty to disable fallback.
    ai_fallback_chain: str = "cerebras,huggingface"
    # Per-call timeout (seconds) — applies to non-streaming generate_text only.
    ai_request_timeout_seconds: int = 60

    # Groq (OpenAI-compatible)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Cerebras (OpenAI-compatible)
    cerebras_api_key: str = ""
    cerebras_model: str = "llama-3.3-70b"
    cerebras_base_url: str = "https://api.cerebras.ai/v1"

    # Anthropic (paid fallback / explicit opt-in)
    anthropic_api_key: str = ""

    # HuggingFace Inference (last-resort fallback)
    huggingface_api_key: str = ""
    huggingface_model: str = "Qwen/Qwen2.5-7B-Instruct"
    huggingface_max_tokens: int = 2048

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
    rate_limit_startup_hunt_per_day: int = 8
    rate_limit_bulk_email_per_campaign: int = 500
    rate_limit_bulk_email_per_month: int = 3000

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

    # ── Job Search (Adzuna) ────────────────────────────────────────────────
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_base_url: str = "https://api.adzuna.com/v1/api"
    job_search_timeout_seconds: int = 12
    # Postgres `jobs` cache row TTL — how long a cached listing is considered fresh.
    job_search_cache_ttl_days: int = 14
    # Redis response cache TTL for identical (query, location, country, ...) searches.
    job_search_response_cache_ttl_seconds: int = 900

    # Startup Hunt v2 seeded sources (global curated + per-user custom) now live in
    # the startup_hunt_sources table (see app/modules/startup_hunt/models.py) —
    # migrated off this env var by alembic/versions/*_add_startup_hunt_sources_table.py.
    startup_hunt_timeout_seconds: int = 20
    startup_hunt_apify_poll_seconds: int = 60
    startup_hunt_total_budget_seconds: int = 30
    google_cse_api_key: str = ""
    google_cse_cx: str = ""
    apify_api_token: str = ""
    apify_base_url: str = "https://api.apify.com/v2"
    apify_startup_hunt_actor_id: str = ""
    apify_indeed_actor_id: str = ""
    theirstack_api_key: str = ""
    theirstack_base_url: str = "https://api.theirstack.com"
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
            "anthropic": ("ANTHROPIC_API_KEY", self.anthropic_api_key),
            "groq": ("GROQ_API_KEY", self.groq_api_key),
            "cerebras": ("CEREBRAS_API_KEY", self.cerebras_api_key),
            # huggingface allows anonymous calls — key optional
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
