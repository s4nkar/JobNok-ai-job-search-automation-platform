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
    # Set AI_PROVIDER=anthropic or AI_PROVIDER=huggingface in .env
    ai_provider: str = "anthropic"
    # Set AI_MODEL=claude-sonnet-4-6 or any HuggingFace model ID
    ai_model: str = "claude-sonnet-4-6"
    # Required when AI_PROVIDER=anthropic
    anthropic_api_key: str = ""
    # Optional — anonymous free HF inference used when empty
    huggingface_api_key: str = ""
    huggingface_model: str = "mistralai/Mistral-7B-Instruct-v0.3"
    huggingface_max_tokens: int = 2048

    # ── Rate Limits (enforced via Redis sliding window) ──────────────────────
    # All limits are per-user per-day unless stated otherwise
    rate_limit_linkedin_per_day: int = 10
    rate_limit_resume_per_day: int = 5
    rate_limit_cover_letter_per_day: int = 5
    rate_limit_interview_per_day: int = 10
    rate_limit_salary_per_day: int = 5
    rate_limit_bulk_email_per_campaign: int = 500
    rate_limit_bulk_email_per_month: int = 3000

    # ── LinkedIn Scraping ────────────────────────────────────────────────────
    # Primary scraper — RAPIDAPI_KEY from RapidAPI dashboard
    rapidapi_key: str = ""
    rapidapi_linkedin_host: str = "linkedin-api8.p.rapidapi.com"
    # Fallback scraper — PHANTOMBUSTER_API_KEY from PhantomBuster dashboard
    phantombuster_api_key: str = ""
    # Shared LinkedIn profile cache TTL (days)
    linkedin_cache_ttl_days: int = 7

    # ── Bulk Email ───────────────────────────────────────────────────────────
    # Minimum delay between individual emails to avoid spam flags (seconds)
    bulk_email_min_delay_seconds: int = 20

    # ── Supabase ─────────────────────────────────────────────────────────────
    # All three required — get from Supabase project Settings > API
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

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

        # AI provider key
        if self.ai_provider == "anthropic" and not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY (required when AI_PROVIDER=anthropic)")

        # Supabase — always required
        if not self.supabase_url:
            missing.append("SUPABASE_URL")
        if not self.supabase_service_role_key:
            missing.append("SUPABASE_SERVICE_ROLE_KEY")
        if not self.supabase_jwt_secret:
            missing.append("SUPABASE_JWT_SECRET")

        # Upstash Redis — always required
        if not self.upstash_redis_rest_url:
            missing.append("UPSTASH_REDIS_REST_URL")
        if not self.upstash_redis_rest_token:
            missing.append("UPSTASH_REDIS_REST_TOKEN")

        if missing:
            formatted = "\n  - ".join(missing)
            raise ValueError(
                f"\n\nMissing required environment variables:\n  - {formatted}\n\n"
                "Add them to your .env file (backend/.env) or set them as OS env vars.\n"
                "See backend/.env.example for the full variable reference.\n"
            )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
