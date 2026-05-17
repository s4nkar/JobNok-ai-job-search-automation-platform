# ⚡ QuickJob — AI Job Search Automation Platform

**Ship fast. Ship right. Ship once.**

QuickJob is a free-tier, production-grade web application that eliminates the repetitive work of job hunting. Eleven AI-powered tools in one place — built to get you hired faster.

---

## 🚀 Tools & Features

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
| 9 | **Recent Job Search** | Search for jobs across platforms, save them, and sync instantly to your Tracker |
| 10| **Startup Hunt** | Discover high-potential startups, track leads, contacts, and link AI artifacts |
| 11| **Profile Management**| Manage CV details, skills, and a CV photo to automatically tailor AI generations |

---

## 📚 Documentation

Detailed documentation for developers has been moved to the `docs/` folder:

- [🏗️ System Architecture](docs/architecture.md) — Next.js, FastAPI, caching, and background workers.
- [🔄 API & Tool Workflows](docs/api_workflows.md) — How the 11 AI tools communicate with external APIs and models.
- [🗄️ Database Schema & Security](docs/database_schema.md) — Supabase RLS policies and table structures.
- [🚀 Deployment & Local Setup](docs/deployment.md) — Docker compose instructions and environment variables.

---

## 📦 Tech Stack

**Frontend:** Next.js 14, TypeScript, Tailwind CSS, shadcn/ui, Zustand, React Hook Form + Zod  
**Backend:** FastAPI, Python 3.11, Celery, PyMuPDF, httpx, pydantic-settings  
**AI:** Anthropic Claude or HuggingFace Inference API (switchable via env)  
**Infrastructure:** Vercel, Railway, Supabase, Upstash, Resend, Cloudflare

---

## 🗺️ Roadmap

- **Phase 1** (Weeks 1–8): Core tools, free-tier infrastructure ← *you are here*
- **Phase 2** (Month 4–8): Stripe payments, team workspaces, template marketplace
- **Phase 3** (Month 12+): Kubernetes/EKS, SOC 2, enterprise SSO, on-premise

---

*QuickJob Confidential — Phase 1 v1.0 | April 2026*
