"""Single source of truth for all backend configuration.

Every field is populated from an environment variable of the same name
(upper-cased). pydantic-settings reads them from the OS environment first,
then falls back to the .env file. The Python default (e.g. "") is ONLY used
if the variable is absent from both sources — it is never the live value in
a real deployment.

Example: `supabase_url` ← SUPABASE_URL in .env or OS env
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

    # ── Rate Limits (enforced via Redis sliding window) ──────────────────────
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

    # ── Job Search ──────────────────────────────────────────────────────────
    # JSON array of ATS sources to search, e.g.
    # [{"type":"greenhouse","name":"Acme","slug":"acme","company":"Acme","metadata":{"stage":"seed","languages":["english"]}}]
    job_search_sources_json: str = "[]"
    job_search_timeout_seconds: int = 12

    # Startup Hunt v2 sources support ATS feeds plus startup/company lead sources.
    # Example:
    # [{"type":"startup_company","name":"Acme","company":"Acme","url":"https://acme.com","metadata":{"country":"germany","city":"berlin","stage":"seed","careers_url":"https://acme.com/careers","contacts":[{"name":"Jane Doe","title":"Founder","email":"jane@acme.com"}]}}]
    startup_hunt_sources_json: str = "[]"
    startup_hunt_timeout_seconds: int = 90
    startup_hunt_apify_poll_seconds: int = 60
    startup_hunt_total_budget_seconds: int = 150
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

    # ── Supabase ─────────────────────────────────────────────────────────────
    # Auth has moved to Clerk (see below) — these two remain solely for
    # Supabase Storage (CV photo uploads, app/modules/profile/routes.py) until
    # that moves to Cloudinary. Get from Supabase project Settings > API.
    supabase_url: str = ""
    supabase_service_role_key: str = ""

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
        """asyncpg driver — used by the FastAPI app (app/core/database.py)."""
        return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    @property
    def database_url_sync(self) -> str:
        """psycopg driver — used by Celery tasks (no event loop)."""
        return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    @property
    def migrations_database_url_sync(self) -> str:
        """psycopg driver over the session-pooler/direct URL — used by Alembic only."""
        return self.migrations_database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    # ── Upstash Redis ────────────────────────────────────────────────────────
    # REST-based Redis for rate limiting — get from Upstash console
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""
    # TCP Redis URL for Celery broker/backend (can reuse Upstash rediss:// URL)
    redis_url: str = "redis://localhost:6379/0"

    # ── Resend ───────────────────────────────────────────────────────────────
    resend_api_key: str = ""
    resend_from_email: str = "noreply@quickjob.app"
    resend_from_name: str = "QuickJob"

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

        # Supabase Storage — always required (until Cloudinary migration)
        if not self.supabase_url:
            missing.append("SUPABASE_URL")
        if not self.supabase_service_role_key:
            missing.append("SUPABASE_SERVICE_ROLE_KEY")

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
