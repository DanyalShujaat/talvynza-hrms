# TALVYNZA HRMS

Multi-tenant HR management system: employees, attendance, leave, payroll, hiring, notices and tasks, with role-based
access and a full audit trail. See [PROGRESS.md](PROGRESS.md) for what is built and what is not, and
[docs/product/known-limitations.md](docs/product/known-limitations.md) for gaps.

## Layout
```
apps/api            FastAPI modular monolith (Python 3.12)
apps/web            React, TypeScript, Vite, Tailwind SPA (plus Playwright browser tests in apps/web/e2e)
packages/shared-types   TypeScript API types
infrastructure/     Dockerfiles and nginx config
docs/               architecture, database, product docs, API spec
scripts/            permission-matrix generator, style check
```

## Run locally (no Docker, SQLite)
Two terminals.

```powershell
# API  ->  http://127.0.0.1:8000  (docs at /api/docs)
cd apps/api
python -m venv .venv ; .\.venv\Scripts\pip install -e ".[dev]"
$env:TALVYNZA_DATABASE_URL = "sqlite:///./dev.db"; $env:TALVYNZA_LOG_JSON = "false"
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\uvicorn app.main:app --reload --port 8000

# Web  ->  http://localhost:5173
cd apps/web ; npm install ; npm run dev
```

With the default `console` email backend, verification and reset links are printed in the API terminal.

Load fictional demo data (refuses to run in production):
```powershell
cd apps/api ; .\.venv\Scripts\python scripts\seed_demo.py     # API must be running
```
It creates the organization "Northwind Demo" and prints the owner login.

## Run with PostgreSQL and Redis (Docker)
```bash
cp .env.example .env     # set TALVYNZA_SECRET_KEY and POSTGRES_PASSWORD
docker compose up --build   # web on http://localhost:8080
```
The Docker files have not been run yet. See known limitations.

## Deploy on Railway

Create a Railway project from the `master` branch, then add PostgreSQL and Redis services. Deploy two services from this
repository: the API service uses `infrastructure/docker/api.Dockerfile` and listens on port `8000`; the web service uses
`infrastructure/docker/web.Dockerfile` and listens on port `80`.

Set `API_UPSTREAM` on the web service to the API service's private Railway hostname and port, for example
`api.railway.internal:8000`. Set the API service's `TALVYNZA_DATABASE_URL` and `TALVYNZA_REDIS_URL` from the Railway
PostgreSQL and Redis references. Production also requires a strong `TALVYNZA_SECRET_KEY`, `TALVYNZA_ENVIRONMENT=production`,
SMTP settings, and matching `TALVYNZA_FRONTEND_URL` and `TALVYNZA_CORS_ORIGINS`. Add a persistent volume mounted at
`/srv/storage` to the API service for uploaded files. Use `/health` as the API healthcheck and expose the web service's
port `80` through its Railway domain.

## Tests
```powershell
cd apps/api ; .\.venv\Scripts\pytest -q ; .\.venv\Scripts\ruff check app tests
cd apps/web ; npm run typecheck ; npm test ; npm run build
cd apps/web ; npx playwright install chromium ; npm run e2e     # starts its own API and web server
python scripts/check_style.py                                     # no em dashes
python scripts/gen_permission_matrix.py                           # regenerates docs/product/permission-matrix.md
```

## Configuration
All settings are `TALVYNZA_*` environment variables, listed in [.env.example](.env.example). Production refuses to start
with the default secret key or the in-memory email backend. Never commit `.env`.
