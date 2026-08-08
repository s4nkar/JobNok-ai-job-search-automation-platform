# 🚀 Deployment & Local Development

JobNok is designed to be easily deployed to modern serverless and PaaS providers. The current Phase 1 architecture is designed specifically to run entirely on **Free Tier** services.

## Production Environments

- **Frontend (Next.js):** [Vercel](https://vercel.com/)
- **Backend (FastAPI & Celery):** [Railway](https://railway.app/)
- **Database (PostgreSQL):** [Neon](https://neon.com/)
- **Auth:** [Clerk](https://clerk.com/)
- **Storage:** [Supabase](https://supabase.com/) (CV photo uploads only)
- **Cache & Rate Limits (Redis):** [Upstash](https://upstash.com/)
- **Email Delivery:** [Resend](https://resend.com/)

---

## Local Development via Docker (Recommended)

JobNok provides a comprehensive `docker-compose.yml` that orchestrates all local services (Frontend, Backend, Celery Worker, Redis, and Nginx proxy).

### Setup Steps
1. Clone the repository.
2. Setup environment variables:
   - Copy `apps/web/.env.example` to `apps/web/.env.local`.
   - Copy `apps/api/.env.example` to `apps/api/.env`.
   - Fill in your API keys (Clerk, Supabase Storage, Upstash Redis, Resend, AI Provider, Neon's `DATABASE_URL`/`MIGRATIONS_DATABASE_URL`).
3. Setup the Database:
   - Provision a Neon project and run `pnpm api:migrate` (Alembic) against it — this creates the full schema on a fresh database. No manual SQL step.
4. Run Docker Compose:
   ```bash
   docker-compose up --build
   ```
5. Access the application:
   - Frontend: `http://localhost:3000`
   - Backend API Docs: `http://localhost:8000/docs`

---

## Manual Local Development (Without Docker)

If you prefer to run services individually without Docker:

### 1. Frontend — requires [pnpm](https://pnpm.io/installation) (Node ≥ 22)
```bash
pnpm install   # from the repo root — it's a pnpm workspace
cd apps/web
pnpm dev
# Running on http://localhost:3000
```

### 2. Backend (FastAPI) — requires [uv](https://docs.astral.sh/uv/getting-started/installation/)
```bash
cd apps/api
uv sync --frozen
uv run uvicorn app.main:app --reload --port 8000
# Running on http://localhost:8000
```

### 3. Celery Worker (Required for Bulk Email)
In a separate terminal:
```bash
cd apps/api
uv run celery -A app.workers.celery_app worker --loglevel=info
```

---

## Important Deployment Considerations

### Proxying API Calls
In the frontend `next.config.mjs` (or Next.js middleware), calls to `/api/*` are rewritten/proxied to the backend url. In the Docker compose setup, an Nginx container serves as the ingress point handling the routing to the appropriate containers.

### CORS Configuration
The FastAPI backend locks down CORS via the `APP_URL` environment variable. Ensure this variable exactly matches the frontend domain in production (e.g., `https://jobnok.app`) to prevent CORS errors.

### Background Workers
Deploying Celery requires a dedicated worker process. On platforms like Railway, you define a secondary service or custom start command:
```bash
celery -A app.workers.celery_app worker --loglevel=info
```
Ensure both the FastAPI web service and the Celery worker service share the exact same environment variables (including `DATABASE_URL`) and connect to the same Redis instance.

### Database Migrations (Alembic)
Alembic is the single source of truth for the schema — `alembic revision --autogenerate` + `alembic upgrade head`. Against a fresh Neon database, `alembic upgrade head` creates every table from scratch (including the `uuid-ossp` extension the baseline migration now provisions itself). No RLS policies, triggers, or grants to manage outside Alembic — those were Supabase-specific and were removed when the database moved to Neon.

### Post-Migration Manual Steps (one-time)
This repo was reorganized from `backend`/`frontend` to `apps/api`/`apps/web`, and the frontend moved from npm to a pnpm workspace rooted at the repo root. Since Railway and Vercel projects are configured via their dashboards (no config files checked into this repo), update each service's settings once:
- **Railway** (FastAPI service and Celery worker service): Root Directory `backend` → `apps/api`.
- **Vercel** (frontend project): Root Directory `frontend` → `apps/web`. Vercel auto-detects pnpm from `pnpm-lock.yaml` at the repo root and understands the monorepo layout automatically once Root Directory is set — no extra build-command config needed.
