quickjob/
│
├── apps/
│   │
│   ├── web/                           # Next.js frontend
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/
│   │   ├── public/
│   │   ├── package.json
│   │   └── Dockerfile
│   │
│   └── api/                           # FastAPI Modular Monolith
│       │
│       ├── Dockerfile
│       ├── pyproject.toml
│       ├── alembic.ini
│       ├── .env.example
│       │
│       ├── alembic/
│       │   ├── env.py
│       │   └── versions/
│       │
│       ├── tests/
│       │
│       └── app/
│           │
│           ├── main.py
│           │
│           ├── core/
│           │   ├── config.py
│           │   ├── database.py
│           │   ├── security.py
│           │   ├── middleware.py
│           │   ├── logging.py
│           │   └── exceptions.py
│           │
│           ├── shared/
│           │   ├── models.py
│           │   ├── pagination.py
│           │   ├── utils.py
│           │   └── constants.py
│           │
│           ├── modules/
│           │
│           │   ├── auth/
│           │   │   ├── routes.py
│           │   │   ├── service.py
│           │   │   ├── schemas.py
│           │   │   └── dependencies.py
│           │   │
│           │   ├── users/
│           │   │   ├── models.py
│           │   │   ├── routes.py
│           │   │   ├── schemas.py
│           │   │   └── service.py
│           │   │
│           │   ├── resumes/
│           │   │   ├── models.py
│           │   │   ├── routes.py
│           │   │   ├── schemas.py
│           │   │   ├── parser.py
│           │   │   └── service.py
│           │   │
│           │   ├── jobs/
│           │   │   ├── models.py
│           │   │   ├── routes.py
│           │   │   ├── schemas.py
│           │   │   ├── service.py
│           │   │   └── filters.py
│           │   │
│           │   ├── applications/
│           │   │   ├── models.py
│           │   │   ├── routes.py
│           │   │   ├── schemas.py
│           │   │   └── service.py
│           │   │
│           │   ├── companies/
│           │   │
│           │   ├── dashboard/
│           │   │
│           │   ├── automation/
│           │   │   ├── routes.py
│           │   │   ├── service.py
│           │   │   └── scheduler.py
│           │   │
│           │   └── billing/
│           │
│           ├── ai/
│           │
│           │   ├── llm/
│           │   │   ├── prompts/
│           │   │   ├── provider.py
│           │   │   ├── ollama.py
│           │   │   └── openai.py
│           │   │
│           │   ├── embeddings/
│           │   │
│           │   ├── ranking/
│           │   │
│           │   ├── matching/
│           │   │
│           │   ├── resume_generation/
│           │   │
│           │   └── cover_letter/
│           │
│           ├── integrations/
│           │
│           │   ├── linkedin/
│           │   ├── greenhouse/
│           │   ├── lever/
│           │   ├── workday/
│           │   ├── ashby/
│           │   └── indeed/
│           │
│           ├── workers/
│           │
│           │   ├── scheduler.py
│           │   ├── scraping.py
│           │   ├── autofill.py
│           │   ├── embeddings.py
│           │   └── notifications.py
│           │
│           └── services/
│               ├── email.py
│               ├── storage.py
│               ├── cache.py
│               └── browser.py
│
├── packages/
│
│   ├── ui/
│
│   └── api-client/
│
├── docker/
│   ├── nginx/
│   └── compose/
│
├── docs/
│
├── scripts/
│
├── docker-compose.yml
├── docker-compose.dev.yml
├── README.md
└── .env.example