"""JobNok FastAPI Backend — modular monolith composition root.

Registers all feature-module routers, middleware, and startup hooks.
Heavy operations: LinkedIn scraping, AI generation, bulk email queue.
"""

from fastapi import FastAPI

from app.core.config import settings
from app.core.middleware import setup_middleware
from app.core.logging import setup_logging
# Registers every module's SQLAlchemy models on Base.metadata, regardless of
# whether that module's own routes/service have been migrated to SQLAlchemy
# yet — needed so cross-module FKs resolve during flush (see docstring).
from app.shared import model_registry  # noqa: F401

from app.modules.linkedin_fill.routes import router as linkedin_fill_router
from app.modules.resume_tailor.routes import router as resume_tailor_router
from app.modules.cover_letter.routes import router as cover_letter_router
from app.modules.interview_prep.routes import router as interview_prep_router
from app.modules.salary.routes import router as salary_router
from app.modules.bulk_email.routes import router as bulk_email_router
from app.modules.bulk_email.campaigns_routes import router as campaigns_router
from app.modules.tracker.routes import router as tracker_router
from app.modules.templates.routes import router as templates_router
from app.modules.job_search.routes import router as job_search_router
from app.modules.startup_hunt.routes import router as startup_hunt_router
from app.modules.startup_scout.routes import router as startup_scout_router
from app.modules.profile.routes import router as profile_router
from app.modules.auth.routes import router as auth_router

setup_logging(settings)

# ── App ───────────────────────────────────────────────────────────
_debug = settings.app_url.startswith("http://localhost")

app = FastAPI(
    title="JobNok API",
    version="1.0.0",
    docs_url="/docs" if _debug else None,
    redoc_url=None,
)

setup_middleware(app, settings)

# ── Routers ───────────────────────────────────────────────────────
app.include_router(linkedin_fill_router,   prefix="/api/scrape",       tags=["linkedin-fill"])
app.include_router(resume_tailor_router,   prefix="/api/ai",           tags=["resume-tailor"])
app.include_router(cover_letter_router,    prefix="/api/ai",           tags=["cover-letter"])
app.include_router(interview_prep_router,  prefix="/api/ai",           tags=["interview-prep"])
app.include_router(salary_router,          prefix="/api/ai",           tags=["salary"])
app.include_router(bulk_email_router,      prefix="/api/email",        tags=["bulk-email"])
app.include_router(campaigns_router,       prefix="/api/campaigns",    tags=["bulk-email"])
app.include_router(tracker_router,         prefix="/api/tracker",      tags=["tracker"])
app.include_router(templates_router,       prefix="/api/templates",    tags=["templates"])
app.include_router(job_search_router,      prefix="/api/job-search",   tags=["job-search"])
app.include_router(startup_hunt_router,    prefix="/api/startup-hunt", tags=["startup-hunt"])
app.include_router(startup_scout_router,   prefix="/api/startup-scout",tags=["startup-scout"])
app.include_router(profile_router,         prefix="/api/profile",      tags=["profile"])
app.include_router(auth_router,            prefix="/api/auth",         tags=["auth"])


@app.get("/api/health", tags=["health"])
async def health():
    return {"status": "ok", "version": "1.0.0"}
