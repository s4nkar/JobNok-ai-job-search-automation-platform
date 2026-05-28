# QuickJob

AI-powered job search automation platform. Eleven tools in one place to cover every repetitive step of the job hunt, from tailoring your resume to sending bulk outreach emails.

## Tools

| Tool | What it does |
|------|-------------|
| Smart Templates | Reusable message templates with `{{placeholder}}` auto-fill |
| LinkedIn Auto-Fill | Paste a LinkedIn URL, get template fields populated from their profile |
| Resume Tailor | Upload resume + job description, get ATS match score, missing keywords, and bullet rewrites |
| Cover Letter Generator | Generates a tailored cover letter, editable inline before export |
| Interview Prep | Paste a JD, get 10 STAR-method Q&As scoped to that exact role |
| Follow-Up Tracker | Lightweight application CRM with overdue follow-up highlighting |
| Salary Research | Job title + location to median salary, range, and negotiation talking points |
| Bulk Email Sender | CSV upload, configurable send delay, live per-recipient status |
| Recent Job Search | Cross-platform job search with one-click sync to the tracker |
| Startup Hunt | Discover and track early-stage companies, leads, and contacts |
| Profile Management | Store CV details, skills, and photo used by all AI generation tools |

## Architecture

```
Browser
  |
  | HTTPS
  v
Vercel (Next.js)
  |
  | /api/* proxy
  v
Nginx
  |
  | HTTP
  v
Railway (FastAPI)
  |-- Supabase (PostgreSQL + Auth + RLS)
  |-- Upstash Redis (rate limits + Celery broker)
  |-- Celery Worker (bulk email, background tasks)
  |-- Groq / Cerebras / HuggingFace (AI generation, fallback chain)
  |-- Jina / Cohere (embeddings, fallback chain)
  |-- Resend (transactional + bulk email)
  |-- RapidAPI / PhantomBuster (LinkedIn scraping)
```

The frontend is UI-only. All business logic lives in FastAPI. Next.js `/api/*` routes exist only for Supabase Auth; everything else proxies straight to the backend.

## Tech Stack

**Frontend:** Next.js 14, TypeScript, Tailwind CSS, shadcn/ui, Zustand, React Hook Form, Zod

**Backend:** FastAPI, Python 3.11, Pydantic v2, Celery, PyMuPDF, WeasyPrint, httpx, Sentry

**AI:** Groq (primary), Cerebras (fallback), HuggingFace (last resort) via `lib/ai_provider.py`

**Embeddings:** Jina (primary), Cohere (fallback) via `lib/embeddings.py` — used for resume/JD semantic matching

**Infrastructure:** Vercel, Railway, Supabase, Upstash Redis, Resend, Cloudflare

## Resume Tailor Pipeline

The tailor endpoint uses a deterministic + LLM-focused split to keep costs down and results honest:

1. Chunk resume with regex (cached by PDF hash for 30 days)
2. Embed resume via Jina/Cohere (cached alongside chunks)
3. Chunk JD fresh on every request
4. Embed JD with jina
5. Deterministic matching: numpy similarity matrix, per-requirement evidence, no AI
6. Deterministic scoring: keyword overlap + embedding similarity per category
7. Single focused LLM call (~1.2k tokens) for prose only: headline, tailored summary, bullet rewrites
8. Return merged JSON with scores + prose

If embeddings fail, the matcher falls back to keyword-only and sets `degraded: true` in the response. Users still get a result.

## Local Setup

### Docker (recommended)

```bash
git clone <repo>
cp frontend/.env.example frontend/.env.local
cp backend/.env.example backend/.env
# fill in keys: Supabase, Upstash, Resend, Groq, Jina
```

Run the schema in your Supabase SQL editor:
```bash
supabase/schema.sql
```

Start all services:
```bash
docker-compose up --build
```

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs

### Manual (without Docker)

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

**Backend:**
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
# or: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Celery worker** (required for bulk email — separate terminal, same venv):
```bash
cd backend
celery -A workers.email_worker worker --loglevel=info
```

## Environment Variables

### Frontend (`frontend/.env.local`)

| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key (safe for browser) |
| `NEXT_PUBLIC_API_URL` | Backend base URL (used for proxying) |

No API keys or secrets belong in frontend env vars.

### Backend (`backend/.env`)

| Variable | Purpose |
|----------|---------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Service role key (server-only) |
| `SUPABASE_JWT_SECRET` | JWT secret for token verification |
| `UPSTASH_REDIS_URL` | Redis URL for rate limits + Celery |
| `GROQ_API_KEY` | Primary AI provider |
| `CEREBRAS_API_KEY` | AI fallback |
| `HUGGINGFACE_API_KEY` | AI last resort |
| `JINA_API_KEY` | Primary embeddings provider |
| `COHERE_API_KEY` | Embeddings fallback |
| `RESEND_API_KEY` | Email delivery |
| `RAPIDAPI_KEY` | LinkedIn scraping |
| `APP_URL` | Frontend origin for CORS (exact match required) |
| `SENTRY_DSN` | Error monitoring |

## Database

Core tables in Supabase PostgreSQL, all with Row Level Security:

| Table | Purpose |
|-------|---------|
| `profiles` | User CV data, skills, photo — auto-created on signup |
| `templates` | Saved message templates |
| `job_applications` | Follow-up tracker entries |
| `email_campaigns` | Bulk email campaign metadata |
| `email_recipients` | Individual recipients per campaign, processed by Celery |
| `job_search_applications` | Jobs found or applied to via job search |
| `startup_hunt_companies` | Tracked startups |
| `startup_hunt_opportunities` | Leads and roles within tracked companies |
| `opportunity_artifacts` | AI-generated content linked to opportunities |
| `linkedin_cache` | Shared LinkedIn profile cache, no RLS, service key only |

Every FastAPI endpoint re-checks `user_id` from the JWT explicitly. RLS is a second layer, not the only layer.

## Security Rules

- No secrets in frontend: only `NEXT_PUBLIC_` vars go near the browser
- JWT required on all backend requests; ownership verified in every query
- Rate limits per `user_id` via Redis; fail closed on expensive AI/scrape endpoints if Redis is down
- CORS locked to `APP_URL` in production, no wildcards
- All text inputs have max-length limits in both Pydantic models and DB columns
- Parameterised queries only; no user input interpolated into SQL or search strings
- No sensitive data (keys, tokens, email addresses) in logs

## Fail Modes

| Failure | Behaviour |
|---------|-----------|
| Embedding service down | Keyword-only matching, `degraded: true` in response |
| AI provider 429 / 5xx | Automatic fallback: Groq -> Cerebras -> HuggingFace |
| All AI providers exhausted | 500 returned to client |
| Redis down | Rate limits fail open (allow), cache misses are non-fatal |
| Scraper failure | Falls back to manual entry or cached data |

## Adding a New Tool

1. Add frontend route under `app/`
2. Add to sidebar navigation
3. Set per-user rate limit key in Redis config
4. Add FastAPI router under `backend/routers/`
5. Add DB table + RLS policy if persistent data is needed

## Documentation

- [Architecture](docs/architecture.md)
- [API and Tool Workflows](docs/api_workflows.md)
- [Database Schema and Security](docs/database_schema.md)
- [Deployment](docs/deployment.md)
- [Resume Tailoring Architecture](docs/resume_tailoring_architecture.md)

