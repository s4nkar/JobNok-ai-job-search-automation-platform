"""Cross-cutting HTTP middleware: CORS + the shared API-secret check."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


def setup_middleware(app: FastAPI, settings) -> None:
    # CORS — locked to frontend origin only
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.app_url],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    # API Secret validation (optional defence-in-depth). In Docker deployments
    # FastAPI is only reachable from nginx (internal network), so this check
    # is skipped when BACKEND_API_SECRET is unset.
    @app.middleware("http")
    async def verify_api_secret(request: Request, call_next):
        if request.url.path == "/api/health":
            return await call_next(request)

        if settings.backend_api_secret:
            secret = request.headers.get("X-API-Secret", "")
            if secret != settings.backend_api_secret:
                return JSONResponse({"detail": "Forbidden"}, status_code=403)

        return await call_next(request)
