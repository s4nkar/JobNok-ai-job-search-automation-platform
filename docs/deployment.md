# 🚀 Deployment & Local Development

QuickJob is designed to be easily deployed to modern serverless and PaaS providers. The current Phase 1 architecture is designed specifically to run entirely on **Free Tier** services.

## Production Environments

- **Frontend (Next.js):** [Vercel](https://vercel.com/)
- **Backend (FastAPI & Celery):** [Railway](https://railway.app/)
- **Database & Auth (PostgreSQL):** [Supabase](https://supabase.com/)
- **Cache & Rate Limits (Redis):** [Upstash](https://upstash.com/)
- **Email Delivery:** [Resend](https://resend.com/)

---

## Local Development via Docker (Recommended)

QuickJob provides a comprehensive `docker-compose.yml` that orchestrates all local services (Frontend, Backend, Celery Worker, Redis, and Nginx proxy).

### Setup Steps
1. Clone the repository.
2. Setup environment variables:
   - Copy `apps/web/.env.example` to `apps/web/.env.local`.
   - Copy `apps/api/.env.example` to `apps/api/.env`.
   - Fill in your API keys (Supabase, Upstash Redis, Resend, AI Provider, `DATABASE_URL`).
3. Setup the Database:
   - Run the SQL script located in `supabase/schema.sql` within your Supabase project's SQL editor.
   - Stamp Alembic at the current schema (first deploy only — see "Database Migrations" below).
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

### 1. Frontend
```bash
cd apps/web
npm install
npm run dev
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
The FastAPI backend locks down CORS via the `APP_URL` environment variable. Ensure this variable exactly matches the frontend domain in production (e.g., `https://quickjob.app`) to prevent CORS errors.

### Background Workers
Deploying Celery requires a dedicated worker process. On platforms like Railway, you define a secondary service or custom start command:
```bash
celery -A app.workers.celery_app worker --loglevel=info
```
Ensure both the FastAPI web service and the Celery worker service share the exact same environment variables (including `DATABASE_URL`) and connect to the same Redis instance.

### Database Migrations (Alembic)
Schema changes go through Alembic, not manual `schema.sql` edits, going forward — `alembic revision --autogenerate` + `alembic upgrade head`. On the **first** deploy after this migration, all 13 tables already exist in production (created by hand-applying `supabase/schema.sql` over time), so run `alembic stamp head` once — **not** `alembic upgrade head` — to tell Alembic "the DB already matches this baseline" without it trying to recreate anything. From then on, `alembic upgrade head` runs as part of the normal release step. `supabase/schema.sql` remains the reference for RLS policies, triggers, and grants, which aren't managed by Alembic.

### Post-Migration Manual Steps (one-time)
This repo was reorganized from `backend`/`frontend` to `apps/api`/`apps/web`. Since Railway and Vercel projects are configured via their dashboards (no config files checked into this repo), update each service's **Root Directory** setting once:
- **Railway** (FastAPI service and Celery worker service): Root Directory `backend` → `apps/api`.
- **Vercel** (frontend project): Root Directory `frontend` → `apps/web`.
