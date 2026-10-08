# Recrutamento: AI-assisted recruitment platform

Internal recruitment system built for the HR team of an urban bus transport company. It ingests résumés from a shared folder, extracts and structures their content, classifies each candidate by job role, ranks candidates per vacancy and tracks them through the hiring pipeline.

## What it does

- **Résumé ingestion:** initial and incremental import of PDF/DOCX files, deduplicated by SHA-256 hash, with a processing log per file
- **Role classification:** a multi-step pipeline (literal match, synonym dictionary, regex per area, fuzzy match, then an optional LLM call through Groq) with explicit fallbacks
- **Scoring and ranking:** per-vacancy scoring profiles with weighted criteria, ranking filters and an audit view that explains each score
- **Search:** keyword and vector-similarity search over structured résumé data
- **Pipeline management:** candidate stages, talent pool, review queue and stage automation rules
- **Communication:** message templates and dispatch through messaging channels (including WhatsApp via WPPConnect)
- **Privacy (LGPD):** PII stored in an encrypted vault (Fernet), candidate consent records and a retention cycle
- **Operations:** health and readiness endpoints, Prometheus metrics, audit log, backups, optional Redis queue for ingestion

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Pydantic 2 |
| Frontend | React 18, Vite, Tailwind CSS, Recharts |
| Database | SQLite for the MVP, structured for PostgreSQL |
| AI | Groq API (Llama 3.3), optional and disabled by default |
| Infrastructure | Redis, Prometheus, Grafana (docker-compose) |
| Quality | pytest (39 tests), GitHub Actions CI (backend tests + frontend build) |

## Project structure

```text
.
|-- backend/
|   |-- app/
|   |   |-- api/routes/     # REST endpoints (about 90)
|   |   |-- core/           # settings, database, security
|   |   |-- models/         # SQLAlchemy models
|   |   |-- repositories/   # data access per entity
|   |   |-- schemas/        # Pydantic schemas
|   |   `-- services/       # ingestion, scoring, ranking, search, LGPD
|   `-- tests/
|-- frontend/               # React + Vite application
|-- docs/                   # architecture, runbook, go-live checklist
|-- ops/                    # Prometheus configuration
`-- docker-compose.infra.yml
```

## Running locally

Requirements: Python 3.12+, Node.js 18+.

```bash
# 1. Environment
cp .env.example .env        # then fill in your own credentials and keys

# 2. Backend (http://127.0.0.1:8091)
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8091

# 3. Frontend (http://127.0.0.1:8090)
cd frontend
npm install
npm run dev
```

On Windows, `start-dev.ps1` starts both with one command.

Optional infrastructure (Redis, Prometheus, Grafana):

```bash
docker compose -f docker-compose.infra.yml up -d
```

## Tests

```bash
cd backend
pytest -q
```

## Useful endpoints

- `GET /healthz` and `GET /readyz`: health and readiness
- `GET /metrics`: Prometheus metrics
- `GET /api/v1`: API base (interactive docs at `/docs`)

## Notes

- All credentials are read from environment variables. The values in `.env.example` are placeholders.
- No candidate data is stored in this repository.
- Documentation in `docs/` is written in Portuguese.
