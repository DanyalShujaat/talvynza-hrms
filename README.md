# Talvynza HRMS

Talvynza brings employee records, attendance, leave, payroll, recruitment, and workplace requests into one workspace. Administrators manage the organization, managers review their teams, and employees use My Space for their own records and requests.

## Project guide

| Guide | What it covers |
| --- | --- |
| [System design](docs/architecture/system-design.md) | Application boundaries, data ownership, and the production topology |
| [Workflow diagrams](docs/product/workflows.md) | Onboarding, attendance, requests, payroll, and offboarding |
| [Business rules](docs/product/business-rules.md) | Validation rules and lifecycle transitions |
| [Security and privacy](docs/architecture/security-privacy.md) | Tenant isolation, authentication, permissions, and sensitive data |
| [Database relationships](docs/database/erd.md) | Key records and their relationships |
| [API schema](docs/api/openapi.json) | Request and response contracts |
| [Testing](docs/product/testing.md) | API and browser verification |
| [Changelog](CHANGELOG.md) | Named releases and changes |

## Repository layout

| Path | Contents |
| --- | --- |
| `apps/api` | FastAPI, SQLAlchemy, Alembic migrations, and API tests |
| `apps/web` | React, TypeScript, Vite, and Playwright browser tests |
| `packages/shared-types` | Shared TypeScript contracts |
| `infrastructure/docker` | Container build and reverse proxy configuration |
| `docs` | Architecture, database, product, and API references |
| `scripts` | Local demo and repository utilities |

## Run locally

Install Python 3.12 and Node.js. From the repository root in PowerShell:

```powershell
python -m venv apps/api/.venv
apps/api/.venv/Scripts/python.exe -m pip install -e "./apps/api[dev]"
npm --prefix apps/web ci
apps/api/.venv/Scripts/python.exe scripts/run_demo.py
```

Open <http://localhost:5180>. The demo keeps fictional accounts and data in `.local/demo`. Use the same command to reopen the existing demo.

For a container-based development stack, copy `.env.example` to `.env`, set the local secrets, and run `docker compose up --build`. The web app listens on port 8080.

## Verify changes

```powershell
Push-Location apps/api
.venv/Scripts/python.exe -m pytest -q
Pop-Location
npm --prefix apps/web test
npm --prefix apps/web run build
npm --prefix apps/web run e2e
```

Install the Chromium test browser with `npx playwright install chromium` from `apps/web` before the first browser run.

## Production

Production serves the web app through Vercel and the API through Railway. The web app forwards `/api/*` to the API so sessions use the web origin. The Railway API container applies Alembic migrations before starting. Keep production configuration and credentials in the hosting environments. See [system design](docs/architecture/system-design.md#production-and-release) for the release sequence.
