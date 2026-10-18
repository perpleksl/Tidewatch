# VISION.md — Tidewatch

> Status: **APPROVED v1.0** — produced from the Vision Session, approved in writing by the owner on 18 Oct 2026.
> Project classification: **Sparse Input** (no brief or designs; all content derived from the Vision Session).

---

## 1. The problem

Crypto opportunities — fresh launches, fundamentally mispriced tokens, and narrative rotations — become visible to a retail trader only after the move has already happened. The owner's X feed is a lagging signal: recent examples ($MASK, $PRL) surfaced only after 10x+ moves.

The opposite risk is equally real: most early-stage tokens are hype, overpromised, or outright rugs. Catching upside without a reliable way to filter out the bad ones just trades missed gains for realised losses.

**The problem in one sentence:** A retail trader has no systematic, early, risk-aware way to find crypto opportunities before they trend, or to tell real value from hype.

## 2. Who has it

**Primary persona (Phase 1): the owner.**
- Active crypto trader, willing to trade on any EVM chain, Solana, and small-cap PoW L1 coins on SafeTrade.
- Not a developer. Directs the build and reviews results; agents implement.
- Wants signals to act on manually; execution stays in their hands in Phase 1.

**Future persona (Phase 3, not designed for now):** Retail crypto traders paying roughly $49/month for access to the dashboard.

## 3. The product

Tidewatch is a research agent and dashboard that continuously scans market, on-chain, revenue, wallet, and social data. It surfaces early opportunities, scores each one for opportunity *and* risk, and explains why.

### Three tabs (all in release 1)
| Tab | What it finds | Typical timeframe |
|---|---|---|
| **Mispriced** | Tokens/coins with real revenue, usage or fundamentals that the market is undervaluing. Includes SafeTrade PoW coins (judged on hashrate, mining spread, dev activity, order books). | Days to weeks |
| **Narratives** | Themes about to run (e.g. a sector heating up) and the strongest tokens within them. | Days |
| **Launches** | New tokens in their first hours or days with genuine early signals. | Minutes to hours |

### Two-axis scoring: opportunity and risk (D12)
- Every signal carries **two separate scores**: an **opportunity score** (how strong the signal is) and a **risk score** (how likely it is to blow up). Each has a visible breakdown of what raised or lowered it.
- Risky tokens are shown, not hidden — a token can be "high opportunity, high risk." Both reference winners ($MASK, $PRL) carried real risk flags.
- Tokens are identified by **chain + contract address** (or native chain for L1 coins), never by ticker, to avoid copycats and ticker collisions.
- Red flags that feed the score: holder concentration, unlocked team/VC supply, anonymous or unproven team, fake revenue (emissions or wash trading), paid or bot-driven X engagement, overpromising roadmap.
- **Hard stops** (e.g. mint function still enabled, liquidity not locked) mark a token "avoid" regardless of upside.
- Measurable checks are computed by code; judgment checks (team credibility, roadmap realism) are AI-assessed and marked lower-confidence.
- The dashboard shows a risk score only — no position sizing.

### Signal lifecycle
Each token is tracked as **one signal** from first flag, stamped with first-flag date and price:

`New → Active → Upgraded / Downgraded → Target hit / Invalidated / Expired`

All outcomes are stored as the system's own track record.

### Delivery
- **Web dashboard** (readable on mobile) with the three tabs and full signal lists.
- **Daily email digest at 10:00 Copenhagen time:** new signals, meaningful changes, and outcomes. Active signals appear as a count only.

### How evaluation works (design principle)
A cost-controlled funnel: deterministic code filters → cheap AI triage → deeper AI analysis on the shortlist only → once-daily narrative synthesis. AI never does the arithmetic; it judges and explains.

## 4. Why now

*(Hypothesis — not discussed in depth.)* The data needed (on-chain revenue, wallet labels, security checks, social data) is now available through affordable APIs, and AI models are cheap enough to evaluate a filtered stream continuously for well under $200/month. A single trader can now run what used to require a research desk.

## 5. Success metrics (starting targets, recalibrated after first backtests)

| Metric | Target |
|---|---|
| **Hit rate** | ≥ 25% of alerts gain ≥ 50% within 14 days of first flag (measured per tab) |
| **Backtest** | $MASK, $PRL and 3–5 other recent winners flagged *before* their main move, without excessive alert volume |
| **Avoidance** | < 10% of "low risk" alerts rug or drop ≥ 80% within 30 days |
| **Lead time** | ≥ 24h before trending on X (Launches tab: a few hours) |
| **Volume guardrail** | ~20 new alerts/day across all tabs (soft cap) |

## 6. MVP scope (release 1)

- All three tabs: Mispriced, Narratives, Launches.
- Built in sequence (Mispriced → Narratives → Launches), **released together**, fully live in the digest.
- Shared scoring engine and risk filters with explainable scores.
- Signal lifecycle with stored track record.
- Web dashboard plus 10:00 email digest.
- Backtesting capability sufficient to measure the success metrics.
- Release 1 goes live once all three tabs meet the success targets in backtest (see A10).

## 7. Explicitly out of scope (Phase 1)

1. No trade execution or position sizing (Phase 2).
2. No wallet or exchange account connection.
3. Single user only — no logins for others, no subscriptions or payments (Phase 3).
4. No real-time push notifications — dashboard and 10:00 email only.
5. No mobile app — web dashboard, readable on mobile.
6. No price predictions or price targets.
7. No NFTs, perps, or derivatives — spot tokens and coins only.
8. No meme tokens — tokens without a product, revenue or utility are excluded from all tabs (D13).

## 8. Constraints

- **Budget:** ≤ ~$700/month combined data + AI. Start Lean (~$260–425/month); upgrade a data source only when backtests show it improves results.
  - Starting data set: DefiLlama (free API), Nansen Pro, Birdeye Starter, X via curated account list or reseller, contract-security API.
  - AI: tiered models (small model for triage, mid model for deep dives, large model for daily synthesis); estimated ~$110–175/month.
- **Builder:** The owner directs; AI agents implement. The owner verifies by using the product, so acceptance criteria must be verifiable through the dashboard, and automated tests are the main code-quality gate.
- **Stack:** Decided in the Architecture Session — React dashboard on Vercel, Python backend and PostgreSQL on Render. See ARCHITECTURE.md. Including hosting, the estimated total running cost is ~$310–480/month (ARCHITECTURE.md Section 9).

## 9. Roadmap context (beyond this vision)

- **Phase 2:** Trading agent that acts on signals, with position sizing calibrated to the risk score.
- **Phase 3:** Commercial subscription product (~$49/month).
- Phase 1 must be "perfected" — meeting its success metrics — before Phase 2 or 3 begins.

## 10. Assumptions

All assumptions below were written into PRD.md and confirmed when the Owner approved PRD v1.0 on 18 Oct 2026.

| ID | Assumption | Status |
|---|---|---|
| A2 | The owner reviews results, not code; agents handle all implementation. | Confirmed (D10) |
| A5 | Tabs are built one at a time. | Confirmed (D5) |
| A6 | Solana is included even though it is not EVM. | Confirmed (PRD 3.2) |
| A7 | Judgment-based red flags are scored by AI reasoning over sources, marked lower-confidence. | Confirmed (PRD 3.4) |
| A8 | Certain critical flags are hard stops that override the score. | Confirmed (PRD 3.4) |
| A9 | ~20 alerts/day is an acceptable volume guardrail. | Confirmed (PRD Section 1) |
| A10 | Release 1 goes live only once all three tabs pass their backtest targets, not on a fixed date. | Confirmed (PRD Section 1) |

## 11. Open questions

| ID | Question | Owner | Resolve by |
|---|---|---|---|
| OQ1 | What were the earliest detectable signals for $MASK and $PRL? **Partly resolved:** cases documented in notes/oq1-backtest-cases.md; exact first on-chain/X signals to be reconstructed from historical data during the build. | Claude (research) → Owner (review) | First backtest tickets |
| OQ2 | Selling signals (Phase 3) while a bot trades them (Phase 2) creates a conflict of interest and possible regulatory exposure (EU/Denmark). How will this be handled? | Owner (with legal advice) | Before Phase 3 design |
| OQ3 | Is "Tidewatch" available (trademarks EUIPO/USPTO, domain, X handle)? Confusion risk with existing "Tide"/"Tidal" crypto projects. | Owner | Before Phase 3 |
| ~~OQ4~~ | **Resolved in Navigate:** GoPlus free tier (150K CU/month) to start, paid from $199/month; DefiLlama free API covers revenue/fees/TVL (paid tier only if unlock data is needed). See ARCHITECTURE.md Section 6. | — | — |
| ~~OQ5~~ | **Resolved in Navigate:** SafeTrade public REST API for prices and volume; per-coin explorers and pool APIs for hashrate and miners, built as a Sprint 1 spike (ARCHITECTURE.md risk R1). | — | — |

## 12. Decision log

| ID | Decision |
|---|---|
| D1 | Dashboard shows a risk score only; sizing belongs to Phase 2. |
| D2 | Six red-flag categories feed the risk score. |
| D3 | Phase 1 ceiling ~$700/month combined data + AI; start Lean, upgrade on evidence. |
| D4 | Success targets accepted as starting hypotheses (Section 5). |
| D5 | Build Mispriced → Narratives → Launches; release all three together, fully live. |
| D6 | Tokens tracked as signals with a lifecycle and stored track record. |
| D7 | Daily digest at 10:00 Copenhagen time. |
| D8 | Digest delivered by email. |
| D9 | Out-of-scope list confirmed (Section 7). |
| D10 | Owner directs; agents build; owner reviews results, not code. |
| D11 | Working name: Tidewatch. |
| D12 | Opportunity and risk are scored separately (two axes); risky tokens are shown with both scores, only hard stops remove a token. Tokens are identified by chain + contract, never ticker. |
| D13 | Meme tokens are excluded from all tabs, not just Narratives. Classification is AI-assessed and visible to the Owner. |
