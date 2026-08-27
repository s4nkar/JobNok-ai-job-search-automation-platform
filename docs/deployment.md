# Deployment & Local Development Guide

**Document Version:** 2.0.0  
**Status:** Production Baseline  

---

## 1. Container Architecture & Docker Compose Setup

The project uses Docker Compose for orchestrating containers across development and production environments.

### Compose Configuration Files
- `docker-compose.yml`: Production base composition.
- `docker-compose.dev.yml`: Development overrides enabling volume mounts and hot-reload.

### Service Topology & Ports
| Container Service | Role | Network Port / Access |
| :--- | :--- | :--- |
| `nginx` | Ingress Reverse Proxy & Router | `http://localhost:80` |
| `api` | FastAPI Backend (`apps/api`) | Exposed on `8000` internally |
| `worker` | ARQ Task Runner (`arq app.workers.arq_worker`) | Internal execution |
| `nextjs` | Web Dashboard (`apps/web`) | Exposed on `3000` |
| `marketing` | Marketing Landing Site (`apps/marketing`) | Exposed on `3001` |
| `admin` | Admin Portal App (`apps/admin`) | Exposed on `3002` |

---

## 2. Local Setup & Execution

### Prerequisites
- Node.js >= 22 with [pnpm](https://pnpm.io/)
- Python >= 3.12 with [uv](https://astral.sh/uv)
- Docker Desktop or Docker Engine

### Quickstart Sequence

```bash
# 1. Install monorepo dependencies
pnpm install

# 2. Configure environment files
cp apps/web/.env.example apps/web/.env.local
cp apps/api/.env.example apps/api/.env

# 3. Execute Alembic schema migrations against PostgreSQL
pnpm api:migrate

# 4. Spin up the container stack
pnpm dev
# Alternatively: docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

---

## 3. Manual Local Setup (Without Docker)

### Backend Service (FastAPI)
```bash
cd apps/api
uv sync --frozen
uv run uvicorn app.main:app --reload --port 8000
```

### Background Task Worker (ARQ)
```bash
cd apps/api
uv run arq app.workers.arq_worker.WorkerSettings
```

### Web Client (Next.js)
```bash
cd apps/web
pnpm dev
```

---

## 4. Production Environment Checklist

- [x] **Alembic Database Migrations**: Run `pnpm api:migrate` (`alembic upgrade head`) before deploying backend updates.
- [x] **CORS Constraints**: Backend `APP_URL` strictly set to the production web domain.
- [x] **Redis Network Isolation**: ARQ worker and FastAPI API share identical Redis credentials and network bridges.
- [x] **Environment Validation**: Server startup validates required secrets (`CLERK_ISSUER_URL`, `DATABASE_URL`, `REDIS_URL`, API keys).
