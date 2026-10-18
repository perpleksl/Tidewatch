# Tidewatch

Single-user crypto research dashboard: scans market, on-chain, revenue, wallet and social data, scores each token for **opportunity** and **risk**, and sends a daily digest.

Built with the SIGNAL framework. Start with the documents at the repo root:

| Document | What it is |
|---|---|
| [VISION.md](VISION.md) | Why Tidewatch exists and what success looks like |
| [PRD.md](PRD.md) | What the product does, with acceptance criteria |
| [ARCHITECTURE.md](ARCHITECTURE.md) | How it's built, and why |
| [CLAUDE.md](CLAUDE.md) | Rules every agent follows |

## Repository layout

```
apps/web/        React dashboard (Vite, TypeScript, Tailwind, shadcn/ui, Redux Toolkit)
backend/         Python backend (FastAPI API + worker), package `tidewatch`
docs/spikes/     Spike write-ups
diagrams/        Mermaid diagrams
notes/           Human working notes (never read by agents)
```

## Running locally

### Requirements
- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js 22+ and [pnpm](https://pnpm.io/)

### Configuration
Copy `.env.example` to `.env` and fill in values. Never commit `.env`.

### Backend (API)
```bash
cd backend
uv sync                                         # install dependencies
uv run uvicorn tidewatch.api.main:app --reload  # start the API on http://localhost:8000
```
Check it works: open http://localhost:8000/health → `{"status": "ok"}`

Quality checks:
```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
```

### Database
PostgreSQL. Tables are created only through Alembic migrations (`backend/migrations/`).
```bash
cd backend
uv run alembic upgrade head                            # apply migrations to DATABASE_URL
uv run alembic revision --autogenerate -m "what changed"  # after changing tidewatch/db/models.py
uv run alembic check                                   # fails if models and migrations differ
```
Database tests need a throwaway PostgreSQL database in `TEST_DATABASE_URL` (they wipe it).
Without it they are skipped locally; CI always runs them.
On Render, staging runs `alembic upgrade head` automatically before each API deploy.

### Dashboard
```bash
cd apps/web
pnpm install   # install dependencies
pnpm dev       # start on http://localhost:5173
```
The page shows "Tidewatch" and an **API status** line (OK when the backend above is running).

Quality checks:
```bash
pnpm typecheck && pnpm lint && pnpm test
```
