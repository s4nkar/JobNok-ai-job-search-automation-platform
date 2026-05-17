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
   - Copy `frontend/.env.example` to `frontend/.env.local`.
   - Copy `backend/.env.example` to `backend/.env`.
   - Fill in your API keys (Supabase, Upstash Redis, Resend, AI Provider).
3. Setup the Database:
   - Run the SQL script located in `supabase/schema.sql` within your Supabase project's SQL editor.
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
cd frontend
npm install
npm run dev
# Running on http://localhost:3000
```

### 2. Backend (FastAPI)
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# Running on http://localhost:8000
```

### 3. Celery Worker (Required for Bulk Email)
In a separate terminal, within the activated backend virtual environment:
```bash
cd backend
celery -A workers.email_worker worker --loglevel=info
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
celery -A workers.email_worker worker --loglevel=info
```
Ensure both the FastAPI web service and the Celery worker service share the exact same environment variables and connect to the same Redis instance.
