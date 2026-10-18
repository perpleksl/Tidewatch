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
