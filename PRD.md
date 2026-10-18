# PRD.md — Tidewatch

> Status: **APPROVED v1.0**. Generated from VISION.md (including D12 and D13), with all Owner-side open questions resolved. Approved in writing by the Owner on 18 Oct 2026.
> Persona throughout: **Owner** — the single user of Phase 1.
> Values marked **[CALIBRATE]** are starting defaults. They are configurable and will be tuned from backtest results.
> Items marked **[OPEN]** must be resolved before the related ticket enters a sprint.

## Table of contents

1. [Overview](#1-overview)
2. [Core user flows](#2-core-user-flows)
3. [Feature specifications](#3-feature-specifications)
   - 3.1 [Access and security](#31-access-and-security)
   - 3.2 [Token identity and universe](#32-token-identity-and-universe)
   - 3.3 [Data ingestion](#33-data-ingestion)
   - 3.4 [Scoring engine](#34-scoring-engine)
   - 3.5 [Mispriced tab](#35-mispriced-tab)
   - 3.6 [Narratives tab](#36-narratives-tab)
   - 3.7 [Launches tab](#37-launches-tab)
   - 3.8 [Signal lifecycle and track record](#38-signal-lifecycle-and-track-record)
   - 3.9 [Signal detail page](#39-signal-detail-page)
   - 3.10 [Daily email digest](#310-daily-email-digest)
   - 3.11 [Backtesting and performance](#311-backtesting-and-performance)
   - 3.12 [Cost and system health](#312-cost-and-system-health)
   - 3.13 [Settings](#313-settings)
4. [Non-functional requirements](#4-non-functional-requirements)
5. [Out of scope](#5-out-of-scope)
6. [Future scope](#6-future-scope)
7. [Open questions](#7-open-questions)

---

## 1. Overview

**Summary.** Tidewatch is a single-user research dashboard that scans market, on-chain, revenue, wallet and social data to surface crypto opportunities early. Every signal gets two scores: opportunity and risk. Signals are tracked over time, and their outcomes are stored as a track record.

**Persona.** The Owner: an active crypto trader on EVM chains, Solana and SafeTrade PoW coins. Not a developer. Verifies the product by using it, not by reading code.

**Release 1 scope.** Three tabs (Mispriced, Narratives, Launches), built in that order and released together. Release 1 goes live once all three tabs meet the success targets in backtest (VISION A10).

**Success targets** (from VISION.md, Section 5):
- Hit rate: ≥ 25% of signals gain ≥ 50% within 14 days of first flag, per tab.
- Backtest: $MASK, $PRL and 3–5 other recent winners flagged before their main move.
- Avoidance: < 10% of low-risk signals rug or drop ≥ 80% within 30 days.
- Lead time: ≥ 24h before trending on X (Launches: a few hours).
- Volume guardrail: ~20 new signals/day across all tabs. Adding a data source adds candidates, not signals: the cap stays at ~20 *(Owner, 19 Oct 2026)*.

## 2. Core user flows

**Flow A — Morning routine**
1. At 10:00, the Owner receives the digest email.
2. They click a new signal in the email and land on its signal detail page.
3. They read the opportunity and risk breakdowns and decide whether to trade (outside Tidewatch).
4. Optionally, they mark the signal "Watching" or "Dismissed."

**Flow B — Browsing a tab**
1. The Owner opens the dashboard and picks a tab.
2. They see a ranked list of active signals with both scores.
3. They filter or sort, then open a signal for detail.

**Flow C — Checking whether the system works**
1. The Owner opens the Track Record page.
2. They see hit rate, avoidance rate and lead time per tab, over a selectable period.
3. They drill into individual outcomes.

**Flow D — Running a backtest**
1. The Owner opens the Backtest page, picks a date range and tabs, and starts a run.
2. When it finishes, they see what would have been flagged and how those signals performed, including whether the reference cases were caught.

---

## 3. Feature specifications

### 3.1 Access and security

**Story:** As the Owner, I want the dashboard to be private so that nobody else can see my signals or settings.

*Note: VISION excludes logins for other users. Protecting the Owner's own dashboard is still required.*

*Sign-in runs on Clerk's free plan (ARCHITECTURE AD6). Resolved IR2, 18 Oct 2026: sessions last 7 days and two-factor authentication is not available on that plan; both are revisited before Phase 2 (see Future scope).*

Acceptance criteria — happy path:
- Visiting any dashboard page without being signed in redirects to a sign-in page.
- The Owner can sign in with a single account and stays signed in for 7 days on that device unless they sign out.
- A "Sign out" action is available on every page and ends the session immediately.
- Every API request without a valid session is rejected; only the health check is public.

Error states:
- A wrong password shows Clerk's standard sign-in error. Sign-in messages are not customised by agents.
- After 5 failed attempts, sign-in is blocked for 15 minutes (Clerk lockout policy, configured during setup).

Edge cases:
- No page offers account creation; the Owner account is created during setup.
- API keys for data sources are never shown in the dashboard; Settings shows only whether each key is configured (✓ / ✗).

### 3.2 Token identity and universe

**Story:** As the Owner, I want every token identified unambiguously so that I never confuse a real project with a copycat.

Acceptance criteria — happy path:
- Each token is identified by **chain + contract address**, or by **native chain** for L1 coins with no contract (e.g. Pearl).
- Every signal displays its chain, a shortened contract address with a copy button, and a link to the relevant block explorer (or to the coin's page on SafeTrade or CoinGecko for native coins).
- Covered universe: all EVM chains supported by the chosen data providers, Solana, and PoW coins listed on SafeTrade.

Error states:
- If a token's chain or contract can't be resolved, it is excluded from scoring and logged in System Health under "unresolved tokens."

Edge cases:
- **Ticker collisions:** When two or more tracked tokens share a ticker, each shows a "Shared ticker" badge with the number of others, listed on the detail page.
- **Copycats:** If a token's name or ticker matches a token with at least 10× its market cap on a different contract, it gets the risk flag "Possible copycat of [name]" with a link to the larger token.
- **Wrapped versions:** A wrapped version of a native coin (e.g. WPRL) is linked to the native coin and not shown as a separate signal.

**Meme token exclusion** *(VISION D13, resolved OQ-P6, 18 Oct 2026)*

Story: As the Owner, I want meme tokens kept out of every tab so that I only see projects with a product, revenue or utility.

Acceptance criteria:
- Before scoring, every token is classified as **Meme** or **Not meme**. Classification is AI-assessed from the project's website, docs, contract and social presence, and stored with a 1–3 sentence rationale and source links.
- Tokens classified as Meme are excluded from all tabs, the digest and backtests.
- The Owner can see excluded meme tokens through a "Show excluded memes" view, each with its rationale, marked "AI-assessed, lower confidence."
- The Owner can override a classification (Meme → Not meme, or the reverse). Overrides are logged and survive reclassification.

Error states:
- If classification fails, the token is held out of all tabs and marked "Unclassified" in System Health until classification succeeds.

Edge cases:
- A token that started as a meme but has since shipped a real product is classified on its current state, not its origin.
- If a project's materials can't be found at all, it is classified Meme by default, with the rationale "No product materials found."

**New-listing discovery via CoinGecko** *(Owner decisions, 19 Oct 2026; PER-19)*

Story: As the Owner, I want coins newly listed on CoinGecko picked up automatically, so that tokens Birdeye's new-pairs feed misses (such as new SafeTrade PoW coins) are still assessed early.

Acceptance criteria:
- Once a day, Tidewatch compares CoinGecko's full coin list with the previous day's. Coins that weren't there before are **new listings**. The first comparison only records a starting list and flags nothing.
- CoinGecko discovery **adds to** Birdeye's new-pairs feed; it doesn't replace it.
- Each new listing is identified by chain + contract address (or native chain), as above, then goes through meme classification and scoring like any other token.
- **Universe unchanged:** only listings inside the covered universe (EVM chains supported by the chosen providers, Solana, and PoW coins listed on SafeTrade) are assessed. Others are recorded with the reason "Outside the covered universe" and not scored.
- **Which tab:** a new listing whose launch was **less than 72 hours ago** (the Launches window, same setting as 3.7) is a Launches candidate. Anything older is a Mispriced candidate. Each tab's own inclusion criteria still apply.
- If the launch time can't be determined, the listing is treated as older than 72 hours, so it's a Mispriced candidate.
- Discovery appears on System Health like any source.

### 3.3 Data ingestion

**Story:** As the Owner, I want data gathered automatically and reliably so that signals reflect the current market.

Sources (Lean tier, VISION D3; providers fixed in ARCHITECTURE.md Section 6): DefiLlama (free API), Nansen Pro (API credits), Birdeye Starter, X (curated account list or reseller), GoPlus contract security (free tier), the SafeTrade public API (read through CoinGecko's free Demo API since PER-18), CoinGecko new listings (daily discovery, see 3.2), per-coin explorers and pool APIs for PoW hashrate and mining stats, and the GitHub API for code activity (3.4, factor 11).

Acceptance criteria — happy path:
- Each source has a defined refresh interval: Launches data ≤ 5 minutes **[CALIBRATE]**, Mispriced and Narratives data ≤ 1 hour **[CALIBRATE]**.
- Every data point stores its source and fetch time.
- The signal detail page shows "Data as of [time]" for each source used.

Error states:
- If a source fails, the system retries 3 times with backoff, then marks the source "Degraded" in System Health.
- Scores computed while a source is degraded show a "Partial data" badge naming the missing source.
- If a source stays down for more than 6 hours, the next digest includes a one-line notice.

Edge cases:
- Sources disagreeing by more than 5% on price: use the higher-liquidity venue's price and log the discrepancy.
- Rate limits or credit exhaustion: the source is marked "Paused — limit reached," and System Health shows when it resumes.
- A paid source being removed must not break the system; scoring continues with a "Partial data" badge.

### 3.4 Scoring engine

**Story:** As the Owner, I want every token scored for both opportunity and risk, with reasons, so that I can judge quickly and trust the numbers.

**Design rules**
- Two independent scores, each 0–100: **Opportunity** (higher = stronger signal) and **Risk** (higher = more dangerous).
- Measurable factors are computed in code. Judgment factors (team credibility, roadmap realism) are AI-assessed and marked "AI-assessed, lower confidence."
- Evaluation funnel: code filters → AI triage → AI deep dive on the shortlist → daily AI narrative synthesis. AI never performs arithmetic used in a score.

**Risk factors** (each shows a status of pass, warning or fail, plus its contribution):
1. Holder concentration: share held by top 10 wallets, excluding known pools, burns and exchanges.
2. Unlocked or upcoming team/VC supply: share of supply unlocking in the next 90 days.
3. Team: public and verifiable vs anonymous; track record (AI-assessed).
4. Revenue quality: real fees vs token emissions or incentives; wash-trading indicators.
5. Social authenticity: share of engagement from bot-like or paid accounts.
6. Roadmap realism: claims vs delivered product (AI-assessed).
7. Liquidity depth: liquidity as % of market cap.
8. Emissions and dilution: new supply per month as % of circulating supply.
9. Valuation gap: FDV vs market cap.
10. Contract security: results from the security API.
11. Code activity and authenticity: evidence from the project's public GitHub repositories (see "GitHub code review" below; VISION D14).

**Hard stops** (token gets status "Avoid" and is excluded from the lists and digest):
- Mint function enabled by a non-renounced owner.
- Liquidity not locked or burned — **only for tokens under 72 hours old** (the Launches window, **[CALIBRATE]**). For older tokens, unlocked liquidity is not a hard stop; it is reflected in the "Liquidity depth" risk factor instead. *(Resolved IR1, 18 Oct 2026.)*
- Honeypot detected (cannot sell).
- Owner can modify balances, blacklist holders, or change transfer tax above 10%.

Acceptance criteria — happy path:
- Every scored token shows both scores and a breakdown listing each factor's value, status and contribution.
- AI-assessed factors are labelled and show a 1–3 sentence rationale with source links.
- The Owner can open any score and see exactly which inputs produced it, without reading code.
- Scores recompute whenever underlying data refreshes; the detail page shows "Last scored at [time]."

Error states:
- If a factor can't be computed, it shows "Unknown" with the reason, and the score is labelled "Incomplete (n of 11 risk factors)."
- If AI analysis fails, the token keeps its code-computed scores, and AI-assessed factors show "Not assessed."

Edge cases:
- Hard-stop tokens stay visible through a "Show avoided" toggle on each tab, with the triggering reason.
- **Native PoW coins:** factors that don't apply (contract security, liquidity lock) show "Not applicable" rather than counting as missing. PoW-specific factors apply instead (see 3.5).

- **Weighting:** All factors within each score start with equal weight **[CALIBRATE]** (11 risk factors). Weights are editable in Settings (3.13) and tuned from backtest results; each backtest run stores the weights it used. *(Resolved OQ-P1, 18 Oct 2026.)*

#### GitHub code review (risk factor 11) *(VISION D14, added 18 Oct 2026)*

**Story:** As the Owner, I want each project's public code checked for real, original, ongoing work, so that I can spot projects that promise more than they build.

**Finding the repositories**
- Repositories are taken only from the project's **official links**: its website or docs, or its listing on CoinGecko or DefiLlama. Tidewatch never searches GitHub by name, because a copycat could point to someone else's code.
- If an official link points to a GitHub organisation, the up to 10 **[CALIBRATE]** most recently active public repositories in it are reviewed together.

**What code measures** (computed in code, no AI):
- Commits in the last 30, 90 and 180 days.
- Distinct active contributors in the last 90 days, and how old their GitHub accounts are.
- Releases in the last 180 days.
- Whether a repository is a fork, of what, and how many of its own commits it has since forking.
- Whether the repository contains source code at all (GitHub's language breakdown), or only a README, docs or config.
- Commit bursts: the share of the last 90 days' commits that landed within any single 48-hour window.

**Factor status**

| Status | When |
|---|---|
| **Fail** | Any of: the main repository is a fork with fewer than 20 **[CALIBRATE]** own commits since forking, presented as the project's own; it contains no source code; at least 50% **[CALIBRATE]** of the last 90 days' commits landed in one 48-hour window; or no commits in 180 days **[CALIBRATE]** while the project's official X account posted in the last 30 days |
| **Warning** | Any of: no public repository found; no commits in 90 days **[CALIBRATE]**; only one active contributor in 90 days; most active contributors' GitHub accounts are younger than 90 days **[CALIBRATE]**; or no commits in 180 days when the project's X activity is unknown |
| **Pass** | None of the above |

Acceptance criteria — happy path:
- Every scored token shows factor 11 with its status, the measured values (e.g. "142 commits / 90 days, 6 contributors, last release 12 days ago") and links to the repositories used.
- A reviewer-tier AI reads each repository's README, file tree and recent commit messages and may mark it **"Flagged for review"** with a one-line reason (e.g. "placeholder code," "commit messages look generated"). A flag never changes the status on its own; it raises the token's priority for a professor deep dive.
- When a token gets a professor deep dive (3.4), the repository evidence is part of it, and the professor's verdict on the code appears as an AI-assessed note under factor 11.
- GitHub evidence is also shown under factor 3 (team), e.g. contributor count and account history.

Error states:
- If the GitHub API is unavailable or rate-limited, factor 11 shows "Unknown," the score is labelled "Incomplete," and System Health shows the GitHub source as Degraded or Paused (3.3).

Edge cases:
- **Closed source is not a fail.** No public repository is a warning.
- **Shared repository:** if the same repository is linked by more than one token, each shows a "Shared repo" warning listing the others (catches copycats pointing at a real project's code).
- Native PoW coins are reviewed the same way, from their official links.
- Stars and followers are shown for context but never count toward the status, since they are easy to buy.

### 3.5 Mispriced tab

**Story:** As the Owner, I want tokens whose fundamentals outrun their valuation, so that I can buy undervalued projects before the market notices.

Inclusion criteria (a token appears when **all** hold):
- No hard stops.
- Market cap between $1M and $500M **[CALIBRATE]**.
- At least one fundamental signal fires:
  - **Revenue-based:** annualised real fees ÷ market cap is in the top 20% of tracked tokens in the same category **[CALIBRATE]**.
  - **Growth-based:** revenue, active users or TVL grew ≥ 50% over 30 days **[CALIBRATE]** while price grew less than half as much.
  - **PoW-based:** hashrate or miner count grew ≥ 30% over 30 days **[CALIBRATE]** while price grew less than half as much.
  - **Developer momentum:** commits or active contributors over the last 30 days grew ≥ 50% **[CALIBRATE]** versus the 30 days before, while price grew less than half as much. Counts only repositories whose factor 11 status is not Fail. *(VISION D14.)*

Opportunity score drivers: size of the valuation gap, momentum of fundamentals (including developer momentum), smart-wallet accumulation (Nansen), and narrative fit (from 3.6).

Acceptance criteria — happy path:
- The tab lists active Mispriced signals ranked by opportunity score by default.
- Each row shows: token, chain, opportunity score, risk score, the fired signal with its value (e.g. "Fee/MC: 0.42, top 8%"), market cap, 7-day price change, state, and first-flag date.
- The Owner can sort by opportunity, risk, market cap, or first-flag date.
- The Owner can filter by chain, risk band (low 0–33 / medium 34–66 / high 67–100), and state.

Error states:
- If revenue data is unavailable for a token, it is evaluated only on growth or PoW signals, and the row shows "Revenue data unavailable."

Edge cases:
- **Native PoW coins (e.g. $PRL):** use the PoW signal plus SafeTrade price and volume. Emissions and dilution are mandatory risk factors for these.
- A token that qualifies for more than one tab appears in each, with the same scores and a "Also in: [tab]" label.

### 3.6 Narratives tab

**Story:** As the Owner, I want to see which themes are starting to move and the best tokens within them, so that I can position early in a rotation.

**Narrative definition:** a named theme (e.g. "Privacy," "AI compute") with a list of member tokens. The tab starts with five seed narratives, **Privacy, AI compute, DePIN, RWA and Perp DEX**, and grows over time as the daily AI synthesis proposes new themes for the Owner to accept. *(Resolved OQ-P4, 18 Oct 2026. Memes deliberately excluded as a narrative.)*

Narrative momentum is computed daily from:
- Growth in X mentions of the theme across the tracked accounts.
- Aggregate 7-day price and volume change of member tokens.
- Smart-wallet inflows into member tokens.
- New tokens launching in the theme.

Acceptance criteria — happy path:
- The tab shows narratives ranked by momentum, each with a momentum score (0–100), a 7-day trend sparkline, and member count.
- Opening a narrative shows its member tokens with both scores, ranked by opportunity.
- A narrative whose momentum rises ≥ 20 points **[CALIBRATE]** within 7 days is flagged "Heating up."
- Each narrative shows a 2–4 sentence AI summary of why it's moving, with source links.

Error states:
- If X data is unavailable, momentum is computed from on-chain and price inputs only, and labelled "Partial data."

Edge cases:
- **AI-proposed new narratives** appear with a "Proposed" badge. The Owner can accept, rename, merge or reject them in Settings. Rejected narratives are not proposed again.
- A token can belong to several narratives.
- A narrative with fewer than 3 member tokens is not ranked.

### 3.7 Launches tab

**Story:** As the Owner, I want promising new tokens flagged within hours of launch, with dangerous ones filtered out, so that I can enter early without walking into rugs.

Inclusion criteria (a token appears when **all** hold):
- Launched within the last 72 hours **[CALIBRATE]**.
- Passes all hard stops.
- Liquidity ≥ $50K **[CALIBRATE]**.
- At least one early signal fires:
  - Smart wallets (Nansen-labelled) bought ≥ 3 **[CALIBRATE]**.
  - Mentioned by ≥ 2 **[CALIBRATE]** tracked X accounts.
  - Holder count grew ≥ 100% in 6 hours **[CALIBRATE]**.
  - Belongs to a narrative flagged "Heating up."

Acceptance criteria — happy path:
- The tab lists launch signals, newest first by default.
- Each row shows: token, chain, age (e.g. "6h"), opportunity score, risk score, the fired early signals, liquidity, holder count, and state.
- The Owner can sort by age, opportunity, risk or liquidity.

Error states:
- If the contract-security check fails or times out, the token is **not** shown until the check succeeds. Unchecked launches are never shown.

Edge cases:
- Hard stops are rechecked every refresh for launches younger than 72 hours. If one fires, the signal is invalidated immediately with the reason.
- Tokens on pump-style launchpads are excluded until they graduate to a DEX. The launch age is counted from graduation, not from creation on the launchpad. *(Resolved OQ-P2, 18 Oct 2026.)*

### 3.8 Signal lifecycle and track record

**Story:** As the Owner, I want each token tracked as one continuous signal so that the digest isn't repetitive and performance is measured honestly.

**States and transitions** (VISION D6):

| State | Entered when |
|---|---|
| New | First flagged; stays New for 24 hours |
| Active | 24 hours after New, while still meeting the tab's criteria |
| Upgraded | Opportunity rises ≥ 15 points, or risk falls ≥ 15 points, since the last digest **[CALIBRATE]** |
| Downgraded | Opportunity falls ≥ 15 points, or risk rises ≥ 15 points **[CALIBRATE]** |
| Target hit | Price ≥ +50% vs first-flag price |
| Invalidated | A hard stop fires; price falls ≥ 40% from first-flag **[CALIBRATE]**; or the token no longer meets the tab's criteria for 3 consecutive days |
| Expired | 30 days with no Upgrade, Downgrade or Target hit |

Upgraded and Downgraded return to Active after appearing in one digest. Target hit, Invalidated and Expired are final; the signal is archived.

Acceptance criteria — happy path:
- Every signal records first-flag timestamp, first-flag price, and both scores at first flag. These never change.
- Every state change is logged with timestamp, price and reason, and shown as a timeline on the signal detail page.
- A token that is re-flagged after archiving starts a **new** signal, linked to the previous one.

Edge cases:
- If a token hits Target and also fires a hard stop in the same refresh, record Target hit first, then show the hard-stop warning on the archived signal.
- "Watching" and "Dismissed" are Owner labels only; they don't change the state or the track record.

**Track Record page**

Acceptance criteria:
- Shows per tab and overall, for a selectable period (7 / 30 / 90 days / all):
  - Hit rate (share of signals reaching +50% within 14 days of first flag).
  - Avoidance rate (share of low-risk signals that rug or drop ≥ 80% within 30 days).
  - Median lead time vs X trending, where measurable.
  - Signal count per day.
- Each metric shows its target and whether it is currently met (✓ / ✗).
- Clicking a metric lists the signals behind it.

### 3.9 Signal detail page

**Story:** As the Owner, I want one page that tells me everything about a signal, so I can decide in under two minutes.

Acceptance criteria:
- Header: token name, ticker, chain, contract (copy button), explorer link, current price, market cap, state badge.
- Both scores, each with its full factor breakdown (3.4).
- "Why flagged": the signals that fired, with values.
- AI summary (3–6 sentences) covering the thesis and the main risks, with source links.
- Price chart since first flag, with the first-flag point and each state change marked.
- Lifecycle timeline (3.8).
- "Data as of" times per source.
- Watching / Dismissed toggle.

Error states:
- A missing section shows "Not available" with the reason; the page never renders empty.

### 3.10 Daily email digest

**Story:** As the Owner, I want a 10:00 email covering only what's new or changed, so I can act without opening the dashboard first.

Acceptance criteria — happy path:
- Sent daily at 10:00 Europe/Copenhagen, adjusting for daylight saving.
- Sections, in this order (empty sections are omitted):
  1. **New signals** — grouped by tab, ranked by opportunity. Each shows token, chain, both scores, a one-line reason, and a link to its detail page.
  2. **Upgraded / Downgraded** — what changed and why.
  3. **Outcomes** — Target hit, Invalidated, Expired, with % change from first flag.
  4. **Narratives heating up.**
  5. **Summary line** — "N active signals across Mispriced / Narratives / Launches."
- Subject line: "Tidewatch — [N] new, [N] changed — [date]."
- Digest content covers the 24 hours before send time.

Error states:
- If the digest fails to send, it retries every 15 minutes for 2 hours, then System Health shows "Digest failed."
- If any data source was degraded for > 6 hours in the period, a notice line appears at the top.

Edge cases:
- No new signals or changes: send a short email saying "No new signals today" with the active count.
- More than 20 new signals: show the top 20 by opportunity and add a link "See all [N] on the dashboard."

### 3.11 Backtesting and performance

**Story:** As the Owner, I want to replay past periods to see what the system would have flagged, so I can verify it works before trusting it.

Acceptance criteria — happy path:
- The Owner can choose a date range (at most limited by available historical data) and one or more tabs, then start a run.
- Results show every signal that would have been flagged, with first-flag date and price, and its outcome under the lifecycle rules.
- Results show the same metrics as the Track Record page, against the same targets.
- **Reference cases** ($MASK, $PRL, plus 3–5 more the Owner adds) each show: flagged (yes/no), first-flag date, price at flag, and gain to peak.
- Each run stores the settings used (thresholds, weights) so runs can be compared side by side.

Error states:
- If historical data is missing for part of the range, the run completes with a warning listing the gaps.

Edge cases:
- Backtests must use only data that would have been available at each point in time (no look-ahead).
- **Historical X data** *(resolved OQ-P3, 18 Oct 2026)*:
  - Past periods (including the $MASK and $PRL reference cases) use a third-party X data reseller, vetted for coverage and quality during the build. Its cost counts toward the $700 ceiling.
  - From the day ingestion starts, Tidewatch stores every post it reads from tracked accounts, so future backtests rely on its own history.
  - Where neither source covers a period, the backtest runs without social inputs and is labelled "No social data."

### 3.12 Cost and system health

**Story:** As the Owner, I want to see what Tidewatch costs and whether everything is running, so that I stay under budget and know when something breaks.

Acceptance criteria:
- A System Health page shows each data source's status (OK / Degraded / Paused), last successful fetch, and error count over 24 hours.
- It shows month-to-date spend per data source and for AI, plus a projected month-end total, against the $700 ceiling (VISION D3).
- At 80% of the ceiling (projected), the next digest includes a warning line.
- At 100% of the ceiling (actual), AI deep dives pause automatically. Code-based scoring continues, and System Health shows "AI paused — budget reached."
- The page shows the last digest send time and status.

### 3.13 Settings

**Story:** As the Owner, I want to adjust thresholds and lists without code changes, so that I can tune the system as I learn.

Acceptance criteria:
- Every value marked [CALIBRATE] in this PRD is editable in Settings, shows its default, and can be reset to default.
- The Owner can manage the tracked X accounts list (add, remove, label).
- **Account track record** *(resolved OQ-P5, 18 Oct 2026)*: Each tracked X account shows an "early-call score": the share of its token mentions that came before the token's signal hit target, and its median lead time. Recalculated weekly.
- Accounts whose early-call score stays in the bottom 20% **[CALIBRATE]** for 60 days are suggested for removal in Settings. The Owner decides; nothing is removed automatically.
- Accounts mentioned repeatedly by top-scoring accounts are suggested as additions.
- The Owner can manage narratives (accept, rename, merge, reject).
- The Owner can manage backtest reference cases.
- Every change is logged with time, old value and new value.

Error states:
- Invalid values (e.g. negative thresholds) are rejected with an inline message naming the valid range.

---

## 4. Non-functional requirements

**Performance**
- Dashboard pages load in under 3 seconds on a normal broadband connection.
- Launches data is at most 5 minutes old; other tabs at most 1 hour.

**Reliability**
- A failure in one data source never stops the others or the digest.
- The digest is delivered on ≥ 95% of days per month.

**Security**
- API keys are stored as environment variables or in a secrets manager, never in the repository or the dashboard.
- All dashboard traffic is over HTTPS.
- No exchange or wallet credentials exist anywhere in the system (VISION out of scope #2).

**Cost**
- Total spend stays within ~$700/month for data plus AI (VISION D3), enforced by 3.12.

**Accessibility and usability**
- Score bands use colour **and** a text label (Low / Medium / High), never colour alone.
- All pages are readable on a 375px-wide phone screen without horizontal scrolling.
- All interactive elements are usable by keyboard.

**Auditability**
- Every score is reproducible from its stored inputs.
- Every Owner action and setting change is logged.

## 5. Out of scope

From VISION.md, Section 7:
1. Trade execution or position sizing (Phase 2).
2. Wallet or exchange account connection.
3. Multiple users, logins for others, subscriptions or payments (Phase 3).
4. Real-time push notifications — dashboard and 10:00 email only.
5. Mobile app.
6. Price predictions or price targets.
7. NFTs, perps or derivatives.
8. Meme tokens, in all tabs (VISION D13; see 3.2).

## 6. Future scope

Ideas captured during Ground. Each needs Owner sign-off before entering a build.

- Two-factor authentication and longer sessions (Clerk Pro) — required before Phase 2 connects to real funds.
- **GitHub review, layer (c) "substance":** a professor-tier AI reads key source files against the project's claims (e.g. does the protocol match the whitepaper, are there audits and tests). Deferred until the cost of layers (a) and (b) is known (VISION D14).
- Push notifications for very high-opportunity Launches signals.
- Paid data upgrades (DefiLlama paid API, Birdeye WebSockets, more X volume) — each only on backtest evidence (VISION D3).
- Phase 2 integration: exposing both scores to a trading agent.
- Phase 3: a public, verifiable track record page.

## 7. Open questions

| ID | Question | Owner | Must close before |
|---|---|---|---|
| ~~OQ-P1~~ | **Resolved:** equal weights to start, tuned from backtests (see 3.4). | Owner | — |
| ~~OQ-P2~~ | **Resolved:** pump-style launchpad tokens are excluded until they graduate to a DEX (see 3.7). | Owner | — |
| ~~OQ-P3~~ | **Resolved:** third-party reseller for past periods, plus own X history stored from day one (see 3.11). Reseller selection happens in Navigate. | Owner | — |
| ~~OQ4~~ | **Resolved in Navigate** (see VISION.md OQ4, ARCHITECTURE.md Section 6). | — | — |
| ~~OQ5~~ | **Resolved in Navigate** (see VISION.md OQ5, ARCHITECTURE.md Section 6 and risk R1). | — | — |
| ~~OQ-P4~~ | **Resolved:** seed narratives are Privacy, AI compute, DePIN, RWA, Perp DEX (no Memes); the list grows through AI proposals the Owner accepts (see 3.6). | Owner | — |
| ~~OQ-P5~~ | **Resolved:** Claude researches a starter list of ~100–300 accounts across the five narratives for Owner review, delivered before Narratives tickets are written. Accounts are then evaluated on their early-call track record (see 3.13). | Claude → Owner | — |
