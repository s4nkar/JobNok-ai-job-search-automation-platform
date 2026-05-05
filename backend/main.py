"""QuickJob FastAPI Backend — Phase 1

Entry point. Registers all routers, middleware, and startup hooks.
Heavy operations: LinkedIn scraping, AI generation, bulk email queue.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import sentry_sdk

from lib.config import settings
from routers import scrape, ai, email, tracker, templates, campaigns

# ── Sentry ───────────────────────────────────────────────────────
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.2,
        send_default_pii=False,
    )

# ── App ───────────────────────────────────────────────────────────
_debug = settings.app_url.startswith("http://localhost")

app = FastAPI(
    title="QuickJob API",
    version="1.0.0",
    docs_url="/docs" if _debug else None,
    redoc_url=None,
)

# ── CORS — locked to frontend origin only ────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.app_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# ── API Secret validation (optional defence-in-depth) ────────────
# In Docker deployments FastAPI is only reachable from nginx (internal
# network), so this check is skipped when BACKEND_API_SECRET is unset.
@app.middleware("http")
async def verify_api_secret(request: Request, call_next):
    if request.url.path == "/api/health":
        return await call_next(request)

    if settings.backend_api_secret:
        secret = request.headers.get("X-API-Secret", "")
        if secret != settings.backend_api_secret:
            return JSONResponse({"detail": "Forbidden"}, status_code=403)

    return await call_next(request)

# ── Routers ───────────────────────────────────────────────────────
app.include_router(scrape.router,    prefix="/api/scrape",    tags=["scrape"])
app.include_router(ai.router,        prefix="/api/ai",        tags=["ai"])
app.include_router(email.router,     prefix="/api/email",     tags=["email"])
app.include_router(tracker.router,   prefix="/api/tracker",   tags=["tracker"])
app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
app.include_router(campaigns.router, prefix="/api/campaigns", tags=["campaigns"])


@app.get("/api/health", tags=["health"])
async def health():
    return {"status": "ok", "version": "1.0.0"}
