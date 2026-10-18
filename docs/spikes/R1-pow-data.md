# Spike R1: PoW data for Pearl ($PRL) (PER-15)

*Research date: 18 Oct 2026.*

## The answer

**Can we get at least 30 days of hashrate history for PRL? No, not today from a free source whose terms allow automated access.**

- **Price history: yes.** SafeTrade's public API gives daily PRL prices from the listing day (23 May 2026), e.g. $0.28 on 1 Aug and $1.90 on 14 Oct.
- **Current network data: yes.** The 2Miners pool API gives network hashrate, difficulty, block reward and block time every hour. Both new adapters store these from today.
- **Past hashrate: no.** Sites that *show* PRL hashrate charts either forbid automated access or don't offer the data through an API.

The options to close the gap are below; the Owner decides.

## Sources compared

| Source | What it gives | History | Key needed | Terms for automated access | Use? |
|---|---|---|---|---|---|
| **2Miners pool API** (`prl.2miners.com/api/stats`) | Network hashrate, difficulty, height, block reward, average block time; miners and workers **on 2Miners** | None (current values only) | No | Public API that 2Miners documents ([apidoc.2miners.com](https://apidoc.2miners.com/)); robots.txt allows `/api/stats` and blocks `/blocks`, `/miners`, `/payments` | ✅ **Chosen** for `pow_pearl` |
| **SafeTrade public API** (`/api/v2/trade/public/tickers`, `/markets/{id}/k-line`) | Price, 24h volume (USDT); daily candles | **From 23 May 2026** (daily) | No | Public market-data API, no account | ✅ **Chosen** for price |
| Official Pearl explorer (`explorer.pearlresearch.ai`) | Blocks with timestamp and difficulty (could rebuild hashrate history) | Since genesis | No | ❌ Terms §3(a) forbid accessing it "via any automated process" and screen scraping | No |
| Kryptex pool (hashrate charts) | Network hashrate chart, up to 1 year | ~1 year (chart only) | — | ❌ robots.txt disallows automated fetching | No |
| WhatToMine API | Network hashrate, difficulty; `stats_history` gives daily history | Daily, coin's full range | Yes | Allowed with a token, but **history needs a paid Business plan** | No (paid) |
| hashrate.no API | Coin stats and estimates | Not documented | Yes (login) | Commercial use needs a paid plan; history not documented | No |
| MiningBoard / MiningPoolStats | Hashrate charts, pool lists | Charts only | — | No API; data not offered for reuse | No |
| **Own Pearl node** (`pearld`, open source, ISC licence) | Every block's difficulty and timestamp, so hashrate at any past height | **Since genesis** | No | Our own copy of a public blockchain | ⏸️ Possible, but costs money (see options) |

## Options for hashrate history

| Option | History | Cost | Effort |
|---|---|---|---|
| **A. Collect from today** (already built) | 30 days by **~18 Nov 2026**, growing from there | $0 | Done |
| **B. Run our own Pearl node** on Render and read block difficulties back to genesis (~May 2026) | Full history, including the Aug–Oct $PRL move | ~$10–15/month (small instance plus ~20 GB disk) | ~1–2 days |
| C. WhatToMine Business plan | Daily history | Paid plan (price not published; on request) | ~0.5 day |

**Recommendation:** go with **A**, which is already running, and decide on **B** only if the backtest needs the hashrate part of the $PRL case. Without B, the $PRL backtest can still use price, volume and emissions. Only the "PoW-based" trigger (hashrate or miners up ≥ 30% while price lags) can't be replayed for August.

## What the adapters store

> **Update, 19 Oct 2026 (PER-18):** SafeTrade blocks requests from Render (HTTP 403), so the `safetrade` adapter was replaced by `coingecko`. It reads SafeTrade's PRL/USDT ticker through CoinGecko's free Demo API and stores rows with `source = coingecko:safetrade`, with price and volume in USD. The old `safetrade` rows are kept.

| Adapter | Every | Stores (for the native coin `chain = "pearl"`, ticker PRL) | Source on each row |
|---|---|---|---|
| `pow_pearl` | `refresh.standard_minutes` (60) | `FundamentalSnapshot`: **hashrate** (H/s), **miners**, **emissions_per_month** | `2miners` |
| `safetrade` | `refresh.standard_minutes` (60) | `MarketSnapshot`: **price** (USDT), **volume_24h** (USDT) | `safetrade` |

Both appear on **System Health** with OK / Degraded / Paused like any source.

**How the numbers are worked out:**

- **Emissions** = block reward (2,243.85 PRL on 18 Oct) × blocks per day (86,400 ÷ average block time of ~172 s) ≈ **1.13M PRL per day**, stored as a monthly figure (× 365.25/12). This is close to the 1,135,718 PRL "Emission" figure on hashrate.no, which is probably also per day. Supply is capped at 2.1B, so emissions are large relative to supply, which is why dilution is a mandatory risk factor for PoW coins (PRD 3.5).
- **Miners: caveat.** PoW networks don't publish a network-wide miner count. The value stored is the number of miners **on 2Miners** (75 on 18 Oct), roughly half the network by hashrate. It's a usable trend signal but **not** a network total. The scoring ticket should weight hashrate above this number, or treat it as a proxy.

## Things found along the way

- **SafeTrade renamed the market today.** At 16:53 UTC on 18 Oct the `prlusdt`, `prlusdc` and `prlbtc` markets were disabled and replaced with `pearlusdt`, `pearlusdc` and `pearlbtc` (shown as "PEARL"). The old daily candles carried over. The adapter finds the market by base unit (`pearl` or `prl`), so it survives renames like this.
- **Where PRL trades:** CoinGecko (`pearl-2`) lists SafeTrade (~90% of volume), BigONE (~8%) and CoinEx (<1%). Price is taken from SafeTrade, as ARCHITECTURE.md §6 decided. BigONE could be added later as a second venue for the 5% price-disagreement rule (PRD 3.3).
- **Risk notes for scoring:** the project's announcement thread contains *unverified* user claims about the mining algorithm being exploitable, plus warnings about a suspicious third-party miner download. These aren't checked here. They're the kind of thing the professor deep dive should weigh.

## Adding another PoW coin

| If the coin… | Effort |
|---|---|
| has a 2Miners pool and a SafeTrade market | **~0.5 day**: copy the two adapters with a new pool URL, chain name and market base unit, plus tests |
| has another open pool API (most pools run the same open-source software) | ~1 day: the same parsing with a different URL, after a terms check |
| has no permitted API | Needs our own node (option B style): ~1–2 days plus hosting |

## Sources

- [2Miners PRL pool](https://2miners.com/prl-mining-pool), [2Miners API docs](https://apidoc.2miners.com/), `https://prl.2miners.com/api/stats` (read on 18 Oct 2026)
- [SafeTrade public API (Peatio endpoints, community wiki)](https://github.com/Fair-Exchange/safecoinwiki/wiki/SafeTrade-API), [safetrade-radar endpoint list](https://github.com/zywiecrypto/safetrade-radar), `https://safetrade.com/api/v2/trade/public/tickers` (read on 18 Oct 2026)
- [Pearl explorer](https://explorer.pearlresearch.ai/) and its [terms of use](https://explorer.pearlresearch.ai/terms-of-use)
- [Pearl source code](https://github.com/pearl-research-labs/pearl), [Pearl announcement thread](https://bitcointalk.org/index.php?topic=5584502)
- [WhatToMine API docs](https://whattomine.com/api-docs), [WhatToMine PRL](https://whattomine.com/coins/469-prl-pearl)
- [hashrate.no PRL](https://www.hashrate.no/coins/PRL), [hashrate.no API](https://www.hashrate.no/api)
- [Kryptex PRL hashrate](https://pool.kryptex.com/prl/hashrate), [MiningBoard PRL](https://miningboard.com/mining/pearl/hashrate?range=ytd), [MiningPoolStats](https://miningpoolstats.stream/pearl)
- [CoinGecko: Pearl](https://www.coingecko.com/en/coins/pearl-2)
