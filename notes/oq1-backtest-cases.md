# OQ1 — Backtest cases: $MASK and $PRL

> Working note (human reference, not agent context). Researched 18 Oct 2026 from public price pages and articles. Earliest on-chain and X signals still need reconstruction from historical data during the build.

## Case 1 — Nullmask ($MASK)

- **What:** ZK privacy protocol, token on Solana. Max supply ~1B.
- **Move:** All-time low ~$0.013 on 28 Sep 2026 → ~$0.056 on 2 Oct 2026 (~4x in about four days). New highs again around 16 Oct.
- **Market cap at peak:** ~$45–50M. ~13K holders.
- **Narrative:** Privacy. Has a MASK/ZEC pool on Raydium — explicitly tied to the Zcash/privacy theme.
- **Risk flags our system would raise:** Very thin liquidity (liquidity ~0.6% of market cap, DeFi TVL ~$58K). Copycat "Nullmask" token exists on pump.fun at a ~$2K market cap.
- **Tab it belongs to:** Narratives (privacy) + Launches.
- **Timeframe of the move:** Days.

## Case 2 — Pearl ($PRL)

- **What:** GPU-mined PoW Layer 1 ("proof of useful work" — mining built on AI matrix multiplication). Mainnet 27 Apr 2026. Max supply 2.1B. No contract address (native chain).
- **Move:** ~$0.28 in August → ~$0.59 mid-September → $2.10 on 14 Oct 2026 (~7x since August).
- **Venue:** Trades mainly on **SafeTrade** — the owner's own venue.
- **Narrative:** AI compute + PoW.
- **Risk flags our system would raise:**
  - Heavy emissions: ~1M+ PRL mined per day against ~350M circulating (~9% monthly dilution).
  - Large gap between market cap (~$590M) and FDV (~$3.5B).
  - Researchers dispute the "useful work" claim.
  - Thin liquidity on very few exchanges.
  - Ticker collisions: Perle (PRL, Solana), The Parallel (PRL, BNB), legacy Oyster Pearl (PRL).
- **Tab it belongs to:** Mispriced (PoW fundamentals: hashrate, miner growth) + Narratives (AI).
- **Timeframe of the move:** Roughly two months.

## Lessons for requirements

1. **Both rode a narrative** (privacy, AI compute). The Narratives tab is load-bearing, not optional.
2. **SafeTrade PoW coverage matters.** One of the two reference winners trades there. OQ5 (PoW data sources) is critical.
3. **Identity must be by chain + contract (or native chain), never ticker.** Both cases have copycats or ticker collisions.
4. **Both winners carried real risk flags.** A filter that hides anything risky would have missed both. → Opportunity and risk must be scored separately (proposed D12).
5. **Neither move was minute-level.** Days for $MASK, weeks for $PRL. Supports the build order and a daily digest.

## Still to reconstruct (during build)

- First on-chain signals (holder growth, smart-wallet buys, hashrate/miner growth for PRL).
- First X mentions by tracked accounts.
- When each would have crossed our scoring thresholds.
