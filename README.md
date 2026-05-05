# ⚡ QuickJob — AI Job Search Automation Platform

**Ship fast. Ship right. Ship once.**

QuickJob is a free-tier, production-grade web application that eliminates the repetitive work of job hunting. Eight AI-powered tools in one place — built to get you hired faster.

---

## 🚀 Tools

| # | Tool | What it does |
|---|------|-------------|
| 1 | **Smart Templates** | Reusable message templates with `{{placeholder}}` auto-fill, instant copy |
| 2 | **LinkedIn Auto-Fill** | Paste a LinkedIn URL → AI fills your template with their profile data |
| 3 | **Resume Tailor** | Upload resume + paste JD → ATS score, missing keywords, bullet rewrites |
| 4 | **Cover Letter Generator** | AI writes a tailored cover letter — editable inline |
| 5 | **Interview Prep** | Paste JD → 10 STAR-method Q&As for that exact role |
| 6 | **Follow-Up Tracker** | Lightweight CRM — track every application, overdue follow-ups in red |
| 7 | **Salary Research** | Job title + location → median, range, negotiation talking points |
| 8 | **Bulk Email Sender** | CSV recipients, delay control, live send status dashboard |

---

## 🏗️ Architecture

```
Frontend (Next.js 14)  →  Vercel
Backend  (FastAPI)     →  Railway
Database (Supabase)    →  Supabase
Cache    (Redis)       →  Upstash
Email    (Resend)      →  Resend
AI       (Claude/HF)   →  Anthropic / HuggingFace
```

**Cost at Phase 1 traffic: $0/month** — all free tiers.

---

## ⚙️ Environment Variables

All limits, model names, and keys are configurable via env. No hardcoded values.

### Frontend (`frontend/.env.local`)

```env
# Supabase
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key

# App URLs
NEXT_PUBLIC_APP_URL=http://localhost:3000
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000

# Rate limits (displayed in UI)
NEXT_PUBLIC_RATE_LIMIT_LINKEDIN=10
NEXT_PUBLIC_RATE_LIMIT_RESUME=5
NEXT_PUBLIC_RATE_LIMIT_COVER_LETTER=5
NEXT_PUBLIC_RATE_LIMIT_INTERVIEW=10
NEXT_PUBLIC_RATE_LIMIT_SALARY=5
NEXT_PUBLIC_RATE_LIMIT_BULK_CAMPAIGN=500
NEXT_PUBLIC_RATE_LIMIT_BULK_MONTH=3000

# Bulk email config
NEXT_PUBLIC_BULK_EMAIL_MIN_DELAY=20
NEXT_PUBLIC_BULK_EMAIL_DEFAULT_DELAY=30

# LinkedIn cache
NEXT_PUBLIC_LINKEDIN_CACHE_TTL_DAYS=7
```

### Backend (`backend/.env`)

```env
# AI Provider — switch between anthropic and huggingface
AI_PROVIDER=anthropic
AI_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=sk-ant-...

# HuggingFace (used when AI_PROVIDER=huggingface)
HUGGINGFACE_API_KEY=hf_...
HUGGINGFACE_MODEL=mistralai/Mistral-7B-Instruct-v0.3

# Rate limits (enforced server-side via Redis)
RATE_LIMIT_LINKEDIN_PER_DAY=10
RATE_LIMIT_RESUME_PER_DAY=5
RATE_LIMIT_COVER_LETTER_PER_DAY=5
RATE_LIMIT_INTERVIEW_PER_DAY=10
RATE_LIMIT_SALARY_PER_DAY=5
RATE_LIMIT_BULK_EMAIL_PER_CAMPAIGN=500
RATE_LIMIT_BULK_EMAIL_PER_MONTH=3000

# LinkedIn scraping
RAPIDAPI_KEY=your-rapidapi-key
RAPIDAPI_LINKEDIN_HOST=linkedin-api8.p.rapidapi.com
PHANTOMBUSTER_API_KEY=your-phantombuster-key
LINKEDIN_CACHE_TTL_DAYS=7

# Bulk email
BULK_EMAIL_MIN_DELAY_SECONDS=20

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret

# Upstash Redis
UPSTASH_REDIS_REST_URL=https://...
UPSTASH_REDIS_REST_TOKEN=...
REDIS_URL=redis://...

# Resend
RESEND_API_KEY=re_...
RESEND_FROM_EMAIL=noreply@yourdomain.com
RESEND_FROM_NAME=QuickJob

# App
APP_URL=http://localhost:3000
BACKEND_API_SECRET=your-shared-secret

# Sentry (optional)
SENTRY_DSN=https://...
```

---

## 🛠️ Local Development

### Prerequisites
- Node.js 18+
- Python 3.11+
- A Supabase project (free tier)
- An Upstash Redis database (free tier)

### 1. Database Setup

Run `supabase/schema.sql` in your Supabase project's SQL editor.

### 2. Frontend

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
# → http://localhost:3000
```

### 3. Backend

```bash
cd backend
cp .env.example .env
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# → http://localhost:8000
# → API docs: http://localhost:8000/docs
```

### 4. Celery Worker (Bulk Email)

```bash
cd backend
celery -A workers.email_worker worker --loglevel=info
```

---

## 🔒 Security

- **Auth**: Supabase JWT on every route (Google, GitHub, email/password)
- **RLS**: Row Level Security on every table — enforced at the database level
- **Rate limiting**: Upstash Redis sliding window per user per tool, reset midnight UTC
- **Input validation**: Zod (frontend) + Pydantic (backend) on all inputs
- **CORS**: FastAPI locked to `APP_URL` only
- **XSS**: Next.js HTML escaping by default

---

## 📦 Tech Stack

**Frontend:** Next.js 14, TypeScript, Tailwind CSS, shadcn/ui, Zustand, React Hook Form + Zod  
**Backend:** FastAPI, Python 3.11, Celery, PyMuPDF, httpx, pydantic-settings  
**AI:** Anthropic Claude or HuggingFace Inference API (switchable via env)  
**Infrastructure:** Vercel, Railway, Supabase, Upstash, Resend, Cloudflare

---

## 🗺️ Roadmap

- **Phase 1** (Weeks 1–8): 8 tools, free-tier infrastructure ← *you are here*
- **Phase 2** (Month 4–8): Stripe payments, team workspaces, template marketplace
- **Phase 3** (Month 12+): Kubernetes/EKS, SOC 2, enterprise SSO, on-premise

---

*QuickJob Confidential — Phase 1 v1.0 | April 2026*
