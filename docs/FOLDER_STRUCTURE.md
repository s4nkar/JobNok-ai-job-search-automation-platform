# 📁 Repository & Monorepo Structure

```
quickjob-ai-job-search-automation-platform/
│
├── apps/
│   ├── web/                          # Next.js 14 Web Frontend Client
│   │   ├── app/                      # Next.js App Router ((dashboard), (auth), etc.)
│   │   ├── components/               # React UI components & shadcn/ui Design System
│   │   ├── lib/                      # API client, state management & custom hooks
│   │   ├── package.json
│   │   └── Dockerfile
│   │
│   ├── api/                          # FastAPI Backend (Modular Monolith)
│   │   ├── alembic/                  # Database migration scripts & versions
│   │   ├── app/
│   │   │   ├── main.py               # Application entrypoint & composition root
│   │   │   ├── core/                 # Config, security (Clerk JWKS), database, rate-limiting
│   │   │   ├── shared/               # Base models, UserScopedRepository, model_registry
│   │   │   ├── ai/                   # LLM providers (Groq/OpenRouter), Jina/Cohere embeddings
│   │   │   ├── services/             # Cache, storage (Cloudinary), email (Resend)
│   │   │   ├── workers/              # ARQ worker & Celery task runners
│   │   │   └── modules/              # Feature modules
│   │   │       ├── auth/             # Clerk webhook handler (/api/auth/webhooks/clerk)
│   │   │       ├── job_search/       # Recent Job Search module (Adzuna/Bundesagentur/Arbeitnow)
│   │   │       ├── startup_hunt/     # Startup Hunt discovery & ATS crawler module
│   │   │       ├── startup_scout/    # Startup Scout AI intelligence module
│   │   │       ├── tracker/          # Application Follow-Up Tracker module
│   │   │       ├── bulk_email/       # Bulk email campaign runner module
│   │   │       ├── profile/          # User CV profile & avatar photo upload
│   │   │       ├── templates/        # Message templates module
│   │   │       ├── cover_letter/     # AI Cover Letter generator
│   │   │       ├── interview_prep/   # AI Interview Prep generator
│   │   │       ├── salary/           # AI Salary Insights generator
│   │   │       ├── resume_tailor/    # AI Resume Tailoring engine
│   │   │       ├── linkedin_fill/    # RapidAPI / PhantomBuster scraper
│   │   │       ├── usage/            # Feature usage analytics event tracking
│   │   │       └── admin/            # Admin platform metrics
│   │   ├── pyproject.toml
│   │   ├── alembic.ini
│   │   └── Dockerfile
│   │
│   ├── admin/                        # Next.js Admin App
│   └── marketing/                    # Marketing Site App
│
├── docs/                             # Production Technical Documentation Suite
│   ├── architecture.md               # Master Platform System Architecture (HLD)
│   ├── database_schema.md            # Database Architecture & Schema Master Reference
│   ├── api_workflows.md              # API Architecture & Routing Reference
│   ├── deployment.md                 # Deployment & Operations Guide
│   ├── FOLDER_STRUCTURE.md           # Repository Structure Map
│   │
│   ├── recent_job_search/            # Recent Job Search Dedicated Docs
│   ├── startup_hunt/                 # Startup Hunt Dedicated Docs
│   └── startup_scout/                # Startup Scout Dedicated Docs
│
├── docker/                           # Nginx configuration
├── docker-compose.yml                # Base Docker Compose orchestration
├── docker-compose.dev.yml            # Development hot reload overrides
├── pnpm-workspace.yaml               # pnpm monorepo workspace configuration
└── README.md
```