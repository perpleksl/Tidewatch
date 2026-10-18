# CLAUDE.md — Tidewatch

> Status: **APPROVED v1.0** (Owner, 18 Oct 2026). Every agent reads this file before doing any work on this repository.
> Framework: SIGNAL. Reference: https://signal-wemuda.vercel.app/llms-full.txt

## 0. The first rule: stop and ask

When anything is unclear — a requirement, a product behaviour, a data model change, anything security-related — **do not guess**. Post a question as a comment on the Linear ticket, mark the ticket blocked, and move to the next agent-safe ticket.

Never make product decisions. Never invent thresholds, weights or behaviour that the PRD doesn't specify.

## 1. What this project is

Tidewatch is a single-user crypto research dashboard. A Python/FastAPI backend with a background worker ingests market, on-chain, revenue, wallet and social data, scores tokens on two axes (opportunity and risk), tracks signals through a lifecycle, and sends a daily email digest. A React/TypeScript dashboard on Vercel displays the results.

The Owner is not a developer. They review your work by **using the preview**, not by reading code. Your acceptance criteria must be verifiable through the dashboard, and your tests must prove them.

## 2. Documents to read

| Document | When |
|---|---|
| `VISION.md` | Product intent; consult when a ticket is ambiguous |
| `PRD.md` | The section referenced by your ticket — always |
| `ARCHITECTURE.md` | Before touching structure, data model, jobs or providers |
| `diagrams/` | Before implementing flows or data model changes |
| `DESIGN.md` and `design/` | Before any UI work, if they exist |

**Never read `notes/`.** It contains human working notes and is excluded from agent context.

## 3. Repository structure

- `apps/web/` — React dashboard (Vite, TypeScript strict).
- `backend/tidewatch/` — Python package, organised by domain:
  `api/`, `worker/`, `ingestion/`, `identity/`, `scoring/`, `tabs/`, `lifecycle/`, `digest/`, `backtest/`, `ai/`, `costs/`, `db/`.
- `backend/tests/` mirrors `backend/tidewatch/`.
- `backend/scripts/` holds one-off probes and maintenance scripts; the worker never runs them.
- `docs/spikes/` holds spike write-ups and sample data. Read the relevant spike write-up before implementing anything it covers.
- New code goes in the domain folder it belongs to. Do not create technical-layer folders like `services/` or `utils/` at the top level.

## 4. Coding standards

### Backend (Python)
- Python 3.12+. Manage dependencies with `uv`. Lint with `ruff`; type-check with `mypy` in strict mode. Fix all warnings.
- FastAPI routes live in `api/`. Every route depends on the Clerk auth dependency except `/health`.
- Database access through SQLAlchemy 2 models in `db/`. Schema changes only through Alembic migrations generated with the CLI.
- Validate all external data with Pydantic models before storing it.
- Each data source is an adapter in `ingestion/` implementing the common adapter interface. Adapters store the source name and the **time the data became available** on every row.
- Monetary and price values use `Decimal`, never `float`.
- All times are stored in UTC. Convert to Europe/Copenhagen only for display and for scheduling the 10:00 digest.

### Frontend (TypeScript)
- React + TypeScript strict, Vite, Redux Toolkit + RTK Query for API data, shadcn/ui + Radix components, Tailwind CSS.
- Score bands always show colour **and** a text label (Low / Medium / High).
- Every page must work at 375px width without horizontal scrolling and be keyboard-usable.
- Missing data renders "Not available" with the reason. Never render an empty section.

### Scoring and AI
- **Code computes every number used in a score.** AI produces only judgments and explanations, always with source links.
- AI calls go through `ai/` only. Every task uses the tier assigned in ARCHITECTURE.md AD9 (worker, reviewer, professor). Log provider, model, tokens and cost for every call.
- **Professor tasks never go through Surplus or any marketplace**; they use the official Anthropic API only. If a task isn't listed in the AD9 task table, stop and ask which tier it belongs to.
- Read the tier-to-model mapping from Settings; never hardcode model IDs in task code.
- Send only public market and social data to AI providers. Never secrets, keys or personal data.
- Use the Batch API and prompt caching for professor-tier work that isn't time-critical.
- All thresholds, weights and [CALIBRATE] values are read from the `Setting` table. Defaults must exactly match PRD.md. **Never hardcode them in logic.**
- Tokens are identified by chain + contract address (or native chain). **Never identify a token by ticker.**

### Backtests
- Use only data whose availability time is at or before the simulated moment. Any look-ahead is a critical bug.

## 5. Testing requirements

- Every acceptance criterion in your ticket gets at least one test. Put the criterion text in the test name or docstring.
- Backend: `pytest`. Frontend: Vitest for components, Playwright for end-to-end flows.
- Minimum 80% coverage for `scoring/`, `lifecycle/`, `backtest/` and `costs/`.
- Use synthetic data in tests (e.g. `0xTEST…` addresses, fake tokens). Never use real API responses containing personal data.
- All CI checks must pass before you request review. If CI fails, fix it; do not ask the Owner to merge a failing PR.

## 6. Git, branches and pull requests

- Branch name: `feat/PER-[number]-short-description` (or `fix/…`). The ticket ID must be in the branch name so Linear links the PR.
- Conventional Commits (`feat:`, `fix:`, `test:`, `chore:` …).
- One ticket per pull request.
- PR description must include:
  - `Fixes PER-[number]`
  - A plain-language summary the Owner can understand.
  - **How to verify:** step-by-step instructions for checking each acceptance criterion in the preview.
  - **Uncertainties:** anything you weren't sure about.
- Never merge any PR. Your PRs appear under the Owner's GitHub account, so the Owner's merge is the approval. Only the Owner clicks Merge.

## 7. Agents must never

1. Put API keys, passwords, tokens or email addresses in code, docs, tickets, tests or commits. Read them from environment variables (names listed in ARCHITECTURE.md Section 10).
2. Run or modify database migrations against staging or production without explicit Owner confirmation on the ticket.
3. Delete data. Archive or soft-delete instead.
4. Change sign-in, session or security code without labelling the PR `security-review`.
5. Add a new paid service, or raise the tier of an existing one.
6. Hardcode or change scoring formulas, thresholds or weights outside the `Setting` table defaults defined in PRD.md.
7. Merge pull requests or push directly to `main`.
8. Add any exchange connection, wallet connection, order placement or trading capability.
9. Install new packages not already in the project without stating why in the PR (and asking on the ticket if it's a large dependency).
10. Read files in `notes/` or any file listed in `.claudeignore`.

## 8. Linear

- Team: **Perpleksl** (key `PER`). Project: **Tidewatch**. The team may hold other work, so scope every ticket query to the Tidewatch project only.
- Only pick up tickets labelled `AGENT-SAFE`.
- When blocked, comment on the ticket with a specific question and move on.

## 9. CI expectations

A PR is ready for Owner review only when:
- Backend lint, type checks and tests pass.
- Frontend lint, type checks and tests pass.
- Playwright end-to-end tests pass against the preview.
- Coverage thresholds are met.
- The PR description includes the "How to verify" steps.

## 10. Learned rules

*(Added after each Learn session. Specific, testable instructions only.)*

- None yet.
