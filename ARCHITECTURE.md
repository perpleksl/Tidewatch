# ARCHITECTURE.md — Tidewatch

> Status: **APPROVED v1.0**. Produced from the Architecture Session; approved in writing by the Owner on 18 Oct 2026.
> Inputs: VISION.md v1.0 (D1–D13), PRD.md v1.0, default-stack.md.
> Every deviation from the Wemuda default stack is marked **[DEVIATION]** with its rationale.

## 1. System overview

Tidewatch is a single-user web application with four parts:

1. **Dashboard (web):** React app on Vercel. Shows tabs, signals, track record, backtests, settings and system health.
2. **API:** Python/FastAPI web service on Render. Serves the dashboard and verifies every request against Clerk.
3. **Worker:** Python always-on background service on Render. Runs all scheduled jobs: data ingestion, scoring, lifecycle updates, AI analysis, the daily digest, and backtests.
4. **Database:** Managed PostgreSQL on Render.

External services: Clerk (sign-in), Resend (email), Anthropic Claude API (professor-tier AI), Surplus Intelligence (worker and reviewer AI, AD9), and the data providers in Section 6.

See `diagrams/system-architecture.md` (generated at the end of Navigate).

## 2. Stack decisions

### AD1 — Frontend: React + TypeScript (default stack)
- React, TypeScript (strict), Vite, Redux Toolkit + RTK Query, shadcn/ui + Radix, Tailwind CSS, deployed to Vercel.
- **Rationale:** Matches the Wemuda default. Well suited to data dashboards, and agents build it reliably.

### AD1 — Backend: Python + FastAPI [DEVIATION]
- Python 3.12+, FastAPI for the API, SQLAlchemy 2 for database access, Alembic for migrations, Pydantic for validation.
- Dependency management with `uv`; linting with `ruff`; type checking with `mypy`; tests with `pytest`.
- **Default was:** .NET/C# with FastEndpoints.
- **Rationale:** The core of Tidewatch is data ingestion, scoring and backtesting. Python has the strongest ecosystem for this, and most crypto data providers publish Python examples or SDKs, so agents write fewer custom integrations. One backend language keeps the codebase simple for a single non-developer Owner.
- **Given up:** Consistency with Wemuda's .NET conventions. Acceptable for a solo, agent-built project.

### AD2 — Hosting: Vercel (web) + Render (API, worker, database) [DEVIATION]
- **Default was:** Kubernetes for complex projects, or Azure App Service for simpler ones.
- **Rationale:** Kubernetes is far too heavy for one user. Azure App Service needs extra services for scheduled jobs and workers. Render offers web services, background workers, cron jobs and managed Postgres in one place, configured from a `render.yaml` file in the repo, with flat per-service pricing.
- **Alternative rejected:** Railway is cheaper when idle but bills on usage with no fixed ceiling, which conflicts with the strict $700/month ceiling (VISION D3).
- **Estimated cost:** about $50/month for production plus staging (see Section 9).

### AD3 — Database: PostgreSQL [DEVIATION]
- Managed PostgreSQL on Render, one instance per environment. Paid instances from the start, since free Render databases expire after 30 days.
- **Default was:** SQL Server.
- **Rationale:** Native to Render, excellent Python support, good handling of time-series data. Can adopt a time-series extension later if price history grows large.
- **Data rules:** Nothing is hard-deleted; records are archived or soft-deleted. Every score stores its inputs so it can be reproduced (PRD Section 4, Auditability).

### AD5 — Email: Resend
- Transactional email via Resend, free tier (3,000 emails/month, 100/day, one domain).
- Sent from a domain the Owner buys. SPF, DKIM and DMARC records are set at the domain registrar.
- **Rationale:** Simple Python SDK, free at our volume, good deliverability with a verified domain.
- **Upgrade trigger:** None expected in Phase 1.

### AD6 — Sign-in: Clerk
- Clerk free tier (50,000 monthly retained users).
- The dashboard uses Clerk's prebuilt sign-in. The API verifies the Clerk session token on **every** request, so no endpoint is public except a health check.
- Self sign-up is disabled; the Owner account is created during setup.
- Free plan limits accepted (AQ1/IR2): no two-factor authentication, 7-day sessions. Lockout policy set to 5 attempts / 15 minutes in the Clerk dashboard. Upgrade to Clerk Pro (2FA, custom session length) before Phase 2.
- **Rationale:** Security-critical code is handled by a specialist service rather than written by agents. Scales naturally to Phase 3.

### AD9 — AI: workers, reviewer and professor [DEVIATION from the original Claude-only routing]
Decided with the Owner on 18 Oct 2026. AI runs in three tiers. Cheap models do the high-volume, low-judgment work; Claude, bought from the official Anthropic API, makes every judgment the Owner sees.

**The tiers**

| Tier | Purpose | Starting model | Bought via | Fallback if unavailable |
|---|---|---|---|---|
| **Worker** | High volume, low judgment: reading and labelling text | `deepseek-v4.1-flash` | Surplus Intelligence marketplace | `claude-haiku-5-5` (official API) |
| **Reviewer** | Medium judgment: deciding what deserves a closer look | `deepseek-v4-pro-0813` | Surplus Intelligence marketplace | `claude-haiku-5-5` (official API) |
| **Professor (deep)** | Final judgments shown to the Owner | `claude-sonnet-5-5` | **Official Anthropic API only** | Pause, keep code-only scores, show "Not assessed" |
| **Professor (synthesis)** | Once-daily cross-market reasoning | `claude-opus-5-5` | **Official Anthropic API only** | Retry next cycle; digest sends without the narratives section |

Starting models are hypotheses. Spike R3 (PER-17) compares them on the same sample, and the tier-to-model mapping lives in Settings so it can change without code.

**Which task goes to which tier**

| Task | PRD | Tier | Why |
|---|---|---|---|
| Classify each X post: which tokens/themes it mentions, relevance | 3.6, 3.7 | Worker | Highest volume (~100k posts/month); simple labelling |
| Extract token names and contract addresses from text | 3.2 | Worker | Pattern work; code then resolves chain + contract, never trusts a ticker |
| Tag tokens with narratives | 3.6 | Worker | Simple classification against a fixed list |
| Meme classification, first pass | 3.2 | Worker | High volume (every new token) |
| Meme classification, borderline or low-confidence cases | 3.2 | Professor (deep) | Wrong exclusions hide real projects; needs judgment |
| Social authenticity: is engagement bot-like or paid? | 3.4 (factor 5) | Reviewer | Medium judgment over many posts |
| Triage: does this token deserve a deep dive? | 3.4 | Reviewer | Medium judgment; decides what the professor sees |
| Team credibility and track record | 3.4 (factor 3) | Professor (deep) | Judgment shown to the Owner, feeds the risk score |
| Roadmap realism | 3.4 (factor 6) | Professor (deep) | Same |
| Revenue quality: real fees vs emissions or wash trading (judgment part) | 3.4 (factor 4) | Professor (deep) | Same; code supplies the numbers |
| Signal AI summary on the detail page | 3.9 | Professor (deep) | The Owner reads it to decide trades |
| Narrative summaries, "why it's moving" | 3.6 | Professor (synthesis) | Part of the daily cross-market view |
| Proposing new narratives | 3.6 | Professor (synthesis) | Needs the broadest reasoning |
| First read of a GitHub repository (README, file tree, commit messages): flag placeholder, copied or generated-looking work | 3.4 (factor 11) | Reviewer | Medium judgment; a flag only raises deep-dive priority, never sets the factor status |
| Verdict on a project's code within a deep dive | 3.4 (factor 11) | Professor (deep) | Shown to the Owner as an AI-assessed note |
| Backtest re-analysis | 3.11 | Same tier as the live task | Results must match live behaviour |

**No AI at all:** digest one-line reasons (built from the signal data), X account early-call scores, every number in every score, lifecycle transitions, cost tracking.

**Rules**
- **Professor tasks never go through Surplus or any marketplace.** The model answering them must be verifiable.
- Worker and reviewer outputs are never shown to the Owner as final judgments. They only route work and label data.
- Only public market and social data is sent to any AI provider. Never secrets, keys or personal data.
- If Surplus fails or has no supply, worker and reviewer tasks fall back to `claude-haiku-5-5` automatically, and System Health shows "AI marketplace unavailable — using fallback."
- **Deep-dive cap:** at most `ai.max_deep_dives_per_day` professor deep dives per day (default 30), highest-ranked tokens first. This is the main AI cost lever.
- The official API uses the Batch API and prompt caching where possible (both unavailable on Surplus, where prices make them unnecessary).
- AI never computes numbers used in scores; code does. AI outputs are judgments and explanations with source links.
- Every AI call records provider, model, token counts and cost for the System Health cost view (PRD 3.12).

**Why marketplaces aren't trusted for judgment:** Surplus's own documentation says it cannot prove which model a seller served. Prices far below list (e.g. "Claude Opus 4.6" listed at $0.0053 per million input tokens in Oct 2026, about 1/1000 of Anthropic's price) suggest substituted models or capacity that can disappear. A swapped worker model only degrades first-pass filtering, which the professor double-checks; a swapped professor would silently corrupt the risk scores.

## 3. Repository structure

Monorepo:

```
/
├── VISION.md  PRD.md  ARCHITECTURE.md  CLAUDE.md  DESIGN.md (if any)
├── render.yaml                 # Render services for staging + production
├── .claudeignore
├── apps/
│   └── web/                    # React dashboard (Vite)
├── backend/
│   ├── pyproject.toml
│   ├── tidewatch/
│   │   ├── api/                # FastAPI routes, Clerk auth dependency
│   │   ├── worker/             # Scheduler and job definitions
│   │   ├── ingestion/          # One adapter per data source
│   │   ├── identity/           # Token identity, copycats, meme classification
│   │   ├── scoring/            # Opportunity + risk scores, hard stops
│   │   ├── tabs/               # Mispriced, Narratives, Launches selection logic
│   │   ├── lifecycle/          # Signal states and transitions
│   │   ├── digest/             # Email digest builder and sender
│   │   ├── backtest/           # Point-in-time replay engine
│   │   ├── ai/                 # Claude client, prompts, model routing, cost logging
│   │   ├── costs/              # Spend tracking and budget enforcement
│   │   └── db/                 # SQLAlchemy models, Alembic migrations
│   ├── scripts/                # One-off probes and maintenance scripts (never run by the worker)
│   └── tests/
├── docs/
│   └── spikes/                 # Spike write-ups and sample data (agent-facing)
├── diagrams/                   # Mermaid diagrams (agent-facing)
├── design/                     # Exported screens (if any)
└── notes/                      # Human working notes (never read by agents)
```

**Code organisation:** Features are organised by domain (as in the default stack's vertical-slice principle), not by technical layer.

## 4. Data model (key entities)

| Entity | Purpose |
|---|---|
| `Token` | One per chain + contract (or native chain). Name, ticker, chain, contract, meme classification, links. |
| `TokenAlias` | Links wrapped versions to their native coin; records shared-ticker relationships. |
| `MarketSnapshot` | Time-stamped price, market cap, FDV, liquidity, volume, holders. Source and fetch time on every row. |
| `FundamentalSnapshot` | Time-stamped revenue, fees, TVL, active users, hashrate, miner count, emissions. |
| `WalletActivity` | Smart-wallet buys and sells per token (from Nansen). |
| `SocialPost` | Every X post read from tracked accounts. Stored permanently (OQ-P3: builds our own history). |
| `XAccount` | Tracked accounts with labels and early-call score. |
| `Narrative` / `NarrativeMember` | Themes and member tokens; status (seed / proposed / accepted / rejected). |
| `SecurityCheck` | Contract-security results per token, time-stamped. |
| `Score` | Opportunity and risk scores with the full factor breakdown and inputs, time-stamped. |
| `Signal` | One per token per tab episode: first-flag time, price and scores (immutable), current state. |
| `SignalEvent` | Every state change with time, price and reason. |
| `OwnerLabel` | Watching / Dismissed. |
| `Setting` / `SettingChange` | All [CALIBRATE] values and weights, with a change log. |
| `BacktestRun` / `BacktestResult` | Run settings and outcomes, including reference cases. |
| `ReferenceCase` | $MASK, $PRL and Owner-added cases. |
| `TokenRepo` | Links a token to the GitHub repositories found through its official links (D14). |
| `RepoSnapshot` | Time-stamped GitHub measurements per repository: commits (30/90/180 days), active contributors and account ages, releases, fork status and own commits, language breakdown, largest 48-hour commit share. |
| `CostEntry` | Spend per data source and AI call. |
| `DigestLog` | Each digest: time, status, contents summary. |

See `diagrams/er-diagram.md` for relationships.

**Point-in-time rule:** Every snapshot carries the time the data *was available* to Tidewatch, not just the time it describes. Backtests only use rows available at the simulated moment (PRD 3.11).

## 5. Jobs and schedules

All jobs run in the worker using an in-process scheduler. Times are configurable; defaults are below.

| Job | Default interval |
|---|---|
| Launches ingestion (new pairs, liquidity, holders, smart-wallet buys) | Every 5 min |
| Security checks on new or young tokens | On discovery, then every 5 min until 72h old |
| Market and fundamentals ingestion | Every 60 min |
| X ingestion from tracked accounts | Every 15 min |
| Meme classification for new tokens | On discovery (batched) |
| Scoring and lifecycle update | After each ingestion cycle |
| AI triage and deep dives | After scoring, shortlist only |
| Daily narrative synthesis | Once daily, 06:00 Copenhagen |
| GitHub repository refresh (discovery + measurements) | Daily, 03:00 Copenhagen |
| Daily digest | 10:00 Copenhagen |
| X account early-call scores | Weekly |
| Cost aggregation and budget check | Hourly |

**Failure isolation:** Each job runs independently. One failing source never blocks other jobs or the digest (PRD Section 4, Reliability).

## 6. Data providers (AD4)

Each provider sits behind an adapter in `backend/tidewatch/ingestion/` with a common interface, so it can be replaced without touching scoring code.

| Need | Provider | Starting tier | Notes |
|---|---|---|---|
| Revenue, fees, TVL | DefiLlama | Free API | Paid tier only if unlock data is needed |
| Smart wallets, labels | Nansen | Pro + API credits | Credit use tracked in costs |
| Prices, market cap, FDV, volume for tracked tokens (M1) | CoinGecko Demo API (`/coins/markets`, up to 250 tokens per call) | Free (Demo plan) | Owner decision, 19 Oct 2026: used for Mispriced in M1 to avoid paying for Birdeye before Launches needs it. Built as its own adapter, so Birdeye can replace it later. Covers PoW coins too |
| Prices, new pairs (EVM + Solana) | Birdeye | Starter ($99), **from M3** | Subscribed when Launches (M3) is built; likely to take over EVM/Solana prices from CoinGecko then. WebSockets via upgrade only on evidence |
| Contract security, top holders, DEX liquidity | GoPlus | Free (150K CU/month) | **From M1** (Owner decision, 19 Oct 2026): Mispriced needs the hard stops. Its holder and liquidity data also feed risk factors 1 and 7. Paid from $199/month if limits are hit |
| SafeTrade prices and volume | CoinGecko Demo API (`/coins/{id}/tickers`), reading the SafeTrade ticker | Free (Demo plan) | Changed in PER-18 (19 Oct 2026): SafeTrade blocks requests from Render (HTTP 403). SafeTrade stays the price venue; if it has no current ticker, the highest-volume USDT venue is used and named in `source`. Low CoinGecko Trust Score (2/10); fed into risk as a venue factor |
| PoW hashrate and miners | Per-coin explorers and pool APIs | Free | Sprint 1 spike (R1) |
| New-listing discovery (adds to Birdeye) | CoinGecko Demo API (`/coins/list?include_platform=true`, once a day, compared with the previous day) | Free (Demo plan) | Owner decision, 19 Oct 2026 (PER-19, PRD 3.2). The paid `/coins/list/new` endpoint isn't used |
| Code activity (D14) | GitHub REST API | Free (authenticated: 5,000 requests/hour) | Read-only token for public repositories; repositories found only via official project links |
| X live posts | twitterapi.io (reseller) | Pay-as-you-go credits (~$20–30/month) | Decided in spike R2 (PER-16, 18 Oct 2026): ~25× cheaper than the official API at ~100k posts/month. Not an official X partner; revisit before Phase 3 (OQ2). Fallback: SocialData. See `docs/spikes/R2-x-data.md` |
| X history | twitterapi.io (same account) | ~$0.15 per 1,000 posts, one-off per backfill | Decided in spike R2 (PER-16). Coverage of the $MASK window checked with `backend/scripts/x_history_probe.py` |

**Upgrade rule (VISION D3):** A provider is upgraded only when a backtest shows the upgrade improves a success metric. Agents never upgrade tiers.

## 7. Environments and deployment (AD8)

| Environment | Purpose | Deploys when |
|---|---|---|
| Local | Development by agents | — |
| Preview | Per-pull-request dashboard preview (Vercel) | Every PR |
| Staging | Full system on live data; sends digest to the Owner with a "[STAGING]" subject prefix | Every merge to `main` |
| Production | The real dashboard and digest | Owner promotes a staging version |

- Each environment has its own database, API keys and Clerk instance.
- Agents only have access to local and preview. **Agents never hold production credentials.**
- Secrets live in Render and Vercel environment settings, never in the repo.
- **How this maps to the providers (PER-8):** Render runs staging from `render.yaml` (deploys after CI passes on `main`). The production environment (manual deploy only) is added to `render.yaml` in M4, to avoid paying for idle services before launch. On Vercel, one project builds `main` as the **staging** dashboard and every PR as a **preview**, all pointing at the staging API. A separate Vercel project for the **production** dashboard is added in M4.
- Browser tests (`apps/web/e2e`) run automatically against each Vercel deployment once it's live (`.github/workflows/e2e.yml`). If Vercel Deployment Protection is on for previews, the GitHub secret `VERCEL_AUTOMATION_BYPASS_SECRET` lets the tests through.

## 8. Testing and CI (AD8)

- GitHub Actions runs on every pull request: backend lint, type checks and tests; frontend lint, type checks and tests; Playwright end-to-end tests against the preview.
- Merging is blocked if any check fails.
- Minimum coverage: **80%** for `scoring/`, `lifecycle/`, `backtest/` and `costs/`. These are the parts where silent bugs cost money.
- Every acceptance criterion in a ticket has at least one test that names the criterion.
- Branch protection on `main`: pull request required, no direct pushes, no force pushes; required status checks added once CI exists (PER-7).
- **The Owner's merge is the approval.** Pull requests opened by Claude appear under the Owner's GitHub account, and GitHub doesn't allow approving your own pull request, so the rule requires 0 approvals. Only the Owner merges.

## 9. Cost model

| Item | Est. monthly |
|---|---|
| Render production (API $7, worker $7, Postgres ~$19) | ~$33 |
| Render staging (API $7, worker $7, Postgres ~$6) | ~$20 |
| Vercel, Clerk, Resend | $0 (free tiers) |
| Data providers (Lean tier) | ~$150–250 |
| AI workers + reviewer (Surplus) | ~$5–15 |
| AI professor (official Claude API: deep dives at 30/day, daily synthesis, borderline memes, web search) | ~$90–150 |
| **Total** | **~$295–470** |

**AI cost note (AD9):** The professor dominates the AI bill. Lowering `ai.max_deep_dives_per_day` from 30 to 15 roughly halves the deep-dive cost (~$55–95 for the professor tier). Tune it against backtest results.

Ceiling: ~$700/month (VISION D3). Enforced in code by `costs/` (PRD 3.12): warning at 80% projected; AI deep dives pause at 100% actual.

**How spend is measured:**
- **Metered costs** (Claude API, Surplus, Nansen API credits, X pay-per-use) are recorded per call as `CostEntry` rows.
- **Fixed subscriptions** (Birdeye, Nansen Pro, Render) are entered once as monthly amounts in Settings and spread evenly across the month in the projection.

## 10. Environment variables (names only — values never in the repo)

```
DATABASE_URL
CLERK_SECRET_KEY            CLERK_PUBLISHABLE_KEY
ANTHROPIC_API_KEY           # professor tier + fallback (official API)
SURPLUS_API_KEY             # worker + reviewer tiers (marketplace)
GITHUB_TOKEN                # read-only, public repositories only (code review, D14)
RESEND_API_KEY              DIGEST_FROM_ADDRESS         DIGEST_TO_ADDRESS
DEFILLAMA_API_KEY (optional)
NANSEN_API_KEY
BIRDEYE_API_KEY
GOPLUS_API_KEY (optional)
COINGECKO_API_KEY           # free Demo plan (PoW coin prices via CoinGecko)
X_API_KEY / X_RESELLER_API_KEY
X_HISTORY_API_KEY
APP_ENV                     # local | preview | staging | production
MONTHLY_BUDGET_USD          # default 700
CORS_ALLOWED_ORIGINS        # dashboard addresses allowed to call the API (comma-separated; not secret)
CORS_ALLOWED_ORIGIN_REGEX   # pattern for Vercel preview addresses allowed to call the staging API (not secret)
VITE_API_BASE_URL           # dashboard only: where to find the API (not secret)
```

`.env.example` at the repo root lists every variable for local development. It contains names only, never values.

## 11. Milestones

| Milestone | Content | Done when |
|---|---|---|
| **M0 — Foundation and spikes** | Repo, CI, Render and Vercel setup, Clerk, database schema, ingestion framework, spikes R1–R3 | Owner can sign in to an empty staging dashboard; spikes answered |
| **M1 — Mispriced** | Identity, meme classification, CoinGecko market data, DefiLlama/Nansen/SafeTrade/PoW/GitHub/GoPlus ingestion, hard stops, scoring engine, lifecycle, Mispriced tab, signal detail, digest, System Health, Settings | Mispriced signals visible on staging with both scores; digest arriving at 10:00 |
| **M2 — Narratives** | X ingestion, narrative momentum, AI synthesis, Narratives tab, X account management | Narratives ranked on staging; proposed narratives reviewable |
| **M3 — Launches** | Birdeye new pairs, GoPlus checks every 5 minutes for young tokens, Launches tab | Launch signals within ≤5 min data freshness on staging |
| **M4 — Backtest and release 1** | Backtest engine, reference cases, Track Record page, calibration | All three tabs meet the VISION success targets in backtest; Owner promotes to production |

Build order follows VISION D5 (Mispriced → Narratives → Launches; released together).

## 12. Technical risks

| ID | Risk | Impact if wrong | Mitigation |
|---|---|---|---|
| **R1** | No standard source for PoW hashrate and miner data | Mispriced can't cover PoW coins like $PRL | **Sprint 1 spike:** build the PoW adapter for $PRL using public pool/explorer sources; check terms of use |
| **R2** | X history reseller quality or cost unknown | Narratives and Launches can't be validated on past cases | **Sprint 1 spike:** test 1–2 resellers on the $MASK/$PRL periods; pick on coverage and cost |
| **R3** | Meme classification accuracy | Real projects excluded, or memes let through | **Sprint 1 spike:** classify a labelled sample of 100 tokens; Owner reviews; override path in Settings |
| R4 | Birdeye Starter polling too slow for Launches | Late launch signals | Measure in M3; WebSockets upgrade only on evidence |
| R5 | Nansen API credit burn | Budget pressure | Credit tracking in `costs/`; query only shortlisted tokens |
| R6 | SafeTrade data reliability | Bad PoW prices | Cross-check with CoinGecko where listed; venue risk factor |
| R7 | Look-ahead bias in backtests | False confidence in results | Point-in-time rule (Section 4); a dedicated test suite |
| R8 | AI cost drift | Budget breach | Tiered models (AD9), deep-dive cap, per-call cost logging, automatic pause at the ceiling |
| R9 | Marketplace serves a substituted model, or supply disappears | Worse first-pass filtering; missed tokens | Professor never uses the marketplace; R3 bake-off compares marketplace vs official output; automatic fallback to `claude-haiku-5-5` |
| R10 | A scam token links to a real project's GitHub repository | Fake code credibility | Repositories only from official links; "Shared repo" warning when one repository is linked by several tokens (PRD 3.4) |

If R1 or R2 fails badly, the Owner is told immediately: it may require a PRD change (e.g. dropping PoW coverage or social inputs from backtests).

## 13. Open architecture questions

| ID | Question | Owner |
|---|---|---|
| ~~AQ1~~ | **Resolved (IR2):** stay on Clerk's free plan — no 2FA, 7-day sessions, lockout 5 attempts / 15 min. Upgrade to Clerk Pro before Phase 2. PRD 3.1 updated. | — |
| ~~AQ2~~ | **Resolved:** Linear team "Perpleksl" (key PER), project "Tidewatch". | — |
