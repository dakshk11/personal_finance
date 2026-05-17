# DirectIndex

DirectIndex is a local, simulation-only financial planning app for tax-aware direct indexing, tax-loss harvesting research, advisor transition proposals, 13F manager research, and retirement income analysis.

It is built for education, modeling, and workflow experimentation. It is not a trading system and does not provide tax, legal, accounting, investment, fiduciary, brokerage, or financial planning advice. Plan to add more fields and make it personal finance go to page.

## Features

- Direct-index portfolio simulation for supported indices including `XLG`, `SPY`, `TOPT`, and `QTOP`.
- Tax-loss harvesting trade review with conservative, moderate, and aggressive modes.
- Executable direct-indexing models:
  - Risk-score optimizer
  - Threshold throttle
  - Peer basket replacement
  - Completion ETF sleeve
- Backtests for supported historical windows with benchmark comparison, tracking difference, harvested losses, tax-adjusted result, and trade-cap diagnostics.
- Portfolio import workflow for holdings and tax lots.
- Advisor workspace for taxable legacy-account transition proposals, gain budgets, active-share limits, tracking-error limits, exclusions, and CSV export.
- SEC 13F research workflow for manager search, watch creation, filing refresh, holdings download, and copycat performance simulation.
- Retirement analyzer with:
  - Account inputs for taxable, tax-deferred, Roth/HSA, and cash reserves
  - Natural retirement spending smile
  - State and federal tax assumptions
  - Roth conversion analysis
  - Dynamic withdrawal guardrails
  - Cash/T-bill, bond, and growth bucket guidance
  - Annual spending funding mix by stable income, taxable, tax-deferred, Roth, cash, and shortfall
  - Saved user inputs after login

## Tech Stack

- Frontend: Next.js, React, TypeScript, Recharts, Lucide icons
- Backend: FastAPI, SQLAlchemy, Pydantic, Argon2 password hashing
- Data and jobs: PostgreSQL, Redis, Celery
- Market data: cached provider data with deterministic fallback data when providers are unavailable
- Deployment for local development: Docker Compose

## Project Structure

```text
.
├── backend/              FastAPI app, services, models, schemas, tests
├── frontend/             Next.js app and shared API client
├── docker-compose.yml    Local Postgres, Redis, backend, worker, beat, frontend
├── .env.example          Local environment template
└── README.md
```

Important frontend routes:

- `/` - marketing and overview
- `/login` and `/signup` - local authentication
- `/dashboard` - portfolio simulation, backtests, model comparison, 13F research
- `/advisor` - advisor transition proposal workspace
- `/research` - methodology and source notes
- `/retirement-analyzer` - retirement income and tax-aware withdrawal analyzer

Important backend routes:

- `/health`
- `/auth/*`
- `/indices`
- `/portfolios/*`
- `/backtests/*`
- `/filings/13f/*`
- `/advisor/*`
- `/retirement-analyzer/state`

## Quickstart

Requirements:

- Docker Desktop or compatible Docker engine
- Docker Compose

Run the full local stack:

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

Local test account:

- Email: `test@gmail.com`
- Password: `1234`

The test account is seeded on backend startup when `SEED_TEST_ACCOUNT=true`. Disable it before using this outside local development.

To stop the stack:

```bash
docker compose down
```

To stop and remove local database/cache volumes:

```bash
docker compose down -v
```

## Environment Variables

Copy `.env.example` to `.env` before running Docker Compose.

| Variable | Purpose |
| --- | --- |
| `POSTGRES_DB` | Local Postgres database name |
| `POSTGRES_USER` | Local Postgres user |
| `POSTGRES_PASSWORD` | Local Postgres password |
| `DATABASE_URL` | Backend SQLAlchemy database URL |
| `REDIS_URL` | Redis URL for Celery jobs |
| `SESSION_COOKIE_SECURE` | Set `true` for HTTPS-only cookies in deployed environments |
| `FRONTEND_ORIGIN` | Allowed frontend origin for CORS |
| `NEXT_PUBLIC_API_URL` | API URL used by the Next.js frontend |
| `SEED_TEST_ACCOUNT` | Seeds the local test user when `true` |
| `TEST_ACCOUNT_EMAIL` | Local seeded test email |
| `TEST_ACCOUNT_PASSWORD` | Local seeded test password |

## Local Development Without Docker

Docker Compose is the recommended path because it starts Postgres, Redis, the API, Celery worker, Celery beat, and the frontend together.

Backend-only local run:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend-only local run:

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

If the backend is run without `DATABASE_URL`, it falls back to a local SQLite database. Some background workflows still require Redis and Celery.

## Tests and Checks

Backend unit tests:

```bash
PYTHONPATH=backend python3 -m unittest discover backend/tests
```

After backend dependencies are installed, pytest can also run the suite:

```bash
PYTHONPATH=backend pytest backend/tests
```

Frontend typecheck:

```bash
cd frontend
npm run typecheck
```

Frontend production build:

```bash
cd frontend
npm run build
```

## Data Behavior

The backend caches holdings, daily prices, and SEC filing data. Where possible, it attempts free provider retrieval. If data is unavailable, throttled, or incomplete, the app falls back to deterministic demo data and shows warnings so the UI remains usable.

Backtest and trade outputs are hypothetical. They depend on cached data, simplified assumptions, user inputs, and model rules. They should be reviewed as research artifacts, not implementation instructions.

## Security Notes

- Passwords are hashed with Argon2.
- Sessions use HTTP-only cookies.
- Local development defaults are intentionally simple and should be changed before any hosted deployment.
- Do not commit `.env`, database files, cache volumes, or private account data.

## Legal and Advice Disclaimer

DirectIndex is educational planning software only. It is not a registered investment adviser, broker-dealer, law firm, CPA firm, tax preparer, fiduciary, custodian, or trading system.

Nothing in the app, README, backtests, tax-loss-harvesting output, transition plans, retirement analyzer, exports, or data displays is tax, legal, accounting, investment, fiduciary, brokerage, or trading advice. Consult qualified professionals before making financial decisions.

## License

No open-source license has been selected yet. Add a `LICENSE` file before publishing publicly if you want others to use, copy, modify, or distribute this project.
