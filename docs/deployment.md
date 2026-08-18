# 🚀 Deployment & Local Development

## Production Environments

Target hosting is **AWS** — not Vercel, Railway, Render, or Neon. The AWS architecture (ECS/App Runner/Lambda, exact service choices, etc.) isn't finalized yet, so it isn't documented here until it's decided.

Current managed services, independent of where the app itself runs:

- **Database (PostgreSQL):** [Supabase](https://supabase.com/) (Postgres hosting only — accessed directly via SQLAlchemy, not the Supabase client/RLS/PostgREST)
- **Auth:** [Clerk](https://clerk.com/)
- **Storage:** [Cloudinary](https://cloudinary.com/) (CV photo uploads)
- **Cache & Rate Limits (Redis):** [Upstash](https://upstash.com/) (REST, rate limiting) + a plain Redis instance (TCP, ARQ broker)
- **Email Delivery:** [Resend](https://resend.com/)

---

## Local Development via Docker (Recommended)

`docker-compose.yml` + `docker-compose.dev.yml` together orchestrate every local service: Postgres, Redis (ARQ broker), the API, the ARQ worker, both Next.js apps (`web` and `marketing`), Nginx, and Adminer (`http://localhost:8085`) for browsing the local database.

### Setup Steps
1. Clone the repository.
2. Setup environment variables:
   - Copy `apps/web/.env.example` to `apps/web/.env.local`.
   - Copy `apps/api/.env.example` to `apps/api/.env`.
   - Fill in your API keys (Clerk, Cloudinary, Upstash Redis, Resend, an AI provider, and a Supabase project's `DATABASE_URL`/`MIGRATIONS_DATABASE_URL`).
3. Setup the Database:
   - Provision a Supabase project (Postgres only — Auth/Storage/RLS aren't used) and run `pnpm api:migrate` (Alembic) against it — this creates the full schema on a fresh database. No manual SQL step.
4. Run Docker Compose:
   ```bash
   pnpm dev   # or: docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
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

### 3. ARQ Worker (Required for Bulk Email)
In a separate terminal:
```bash
cd apps/api
uv run arq app.workers.arq_worker.WorkerSettings
```

---

## Important Deployment Considerations

### Proxying API Calls
In the frontend `next.config.mjs` (or Next.js middleware), calls to `/api/*` are rewritten/proxied to the backend url. In the Docker compose setup, an Nginx container serves as the ingress point handling the routing to the appropriate containers.

### CORS Configuration
The FastAPI backend locks down CORS via the `APP_URL` environment variable. Ensure this variable exactly matches the frontend domain in production (e.g., `https://jobnok.app`) to prevent CORS errors.

### Background Workers
Deploying ARQ requires a dedicated worker process, run separately from the FastAPI web process:
```bash
arq app.workers.arq_worker.WorkerSettings
```
Ensure both the FastAPI web service and the ARQ worker service share the exact same environment variables (including `DATABASE_URL`) and connect to the same Redis instance. The exact deployment shape for this on AWS (ECS service, Lambda, etc.) isn't decided yet.

### Database Migrations (Alembic)
Alembic is the single source of truth for the schema — `alembic revision --autogenerate` + `alembic upgrade head`. Against a fresh Supabase database, `alembic upgrade head` creates every table from scratch (including the `uuid-ossp` extension the baseline migration provisions itself). No RLS policies, triggers, or grants to manage outside Alembic — data isolation is enforced entirely in the application layer (`UserScopedRepository`, explicit `user_id` filtering on every query), not Postgres RLS.
