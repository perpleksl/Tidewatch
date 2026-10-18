# Spike R2: X data source (PER-16)

*Research date: 18 Oct 2026. Prices change; re-check before signing up.*

**Decision (Owner, 18 Oct 2026): twitterapi.io for live posts and history. Probe passed.**

## Question

Where should Tidewatch get X posts, (a) live, from ~100–300 tracked accounts (~100k posts/month), and (b) historical, for backtests such as the $MASK (Nullmask) and $PRL moves (PRD 3.11, OQ-P3)?

## Options compared

| | **Official X API (pay-per-use)** | **twitterapi.io** | **SocialData** | **Apify tweet scrapers** |
|---|---|---|---|---|
| **Price** | $0.005 per post read; $0.010 per user lookup | $0.15 per 1,000 posts; minimum $0.00015 per call; list-timeline calls $0.0015 each | $0.20 per 1,000 posts or profiles | ~$0.25–0.40 per 1,000 posts, depending on the actor |
| **Cost at ~100k live posts/month** | **~$500** (24-hour de-duplication saves little for new posts) | **~$20**: $15 for posts + ~$4 to poll one X List every 15 minutes | **~$20–25** | **~$25–40** |
| **History depth** | Full archive (`/2/tweets/search/all` is available on pay-per-use) | Advanced search with `since_time`/`until_time`. The docs don't state a depth limit; **the probe measures it** | Search with `since_time`/`until_time`, and `max_id` paging back to an account's first post | Depends on the actor; batch runs, not real-time |
| **Cost of a 12-month backfill** (~1.2M posts) | ~$6,000 | ~$180 | ~$240 | ~$300–480 |
| **Limits** | Max 3M post reads per month on pay-per-use | 20 requests/second after the first payment | 120 requests/minute (more on request) | Run-based; results arrive after minutes |
| **Terms of use** | Official and licensed. Safest for Phase 3 (commercial use) | Not an official X partner. Unofficial access means continuity risk, and X's terms restrict scraping | Same as twitterapi.io | Same; scraping-based actors |
| **Python** | REST plus official SDK | REST (`X-API-Key` header); httpx is enough | REST (Bearer token); httpx is enough | Apify Python client |

## Recommendation

| Need | Pick | Why |
|---|---|---|
| **Live posts** | **twitterapi.io** | About 25× cheaper than the official API at our volume (~$20 vs ~$500), fast enough (20 requests/second) for 15-minute polling, and one X List covers all tracked accounts. |
| **History** | **twitterapi.io** (same account and key) | Cheapest search with exact time windows. One provider means one adapter and one bill. **SocialData** is the fallback if the probe shows history gaps. |

**Not recommended now:** the official X API. At ~$500/month for live posts it alone would use ~70% of the $700 ceiling. Its one real advantage is licensed, official access. Reconsider before Phase 3 (the paid product), when terms of use matter more (VISION OQ2).

### Monthly cost against the ceiling

| | Est. monthly |
|---|---|
| Current estimate (ARCHITECTURE.md §9) | ~$295–470 |
| X via twitterapi.io (live) | ~$20–30 |
| **Total** | **~$315–500 of $700** ✅ |
| *For comparison: with the official X API instead* | *~$795–970: over the ceiling* ❌ |

History is a one-off cost per backfill: about $0.15 per 1,000 posts. A full year for the tracked accounts is ~$180, and a term search like the Nullmask probe costs cents.

## Risks

- **Continuity:** a reseller can break or shut down if X changes access. To limit this, every X source sits behind the ingestion adapter interface (PER-13), so switching to SocialData or the official API is a single new adapter. System Health shows "Degraded" if posts stop arriving.
- **Coverage gaps:** reseller search may miss deleted or protected posts. That doesn't matter for public crypto accounts. The probe checks real coverage on the $MASK window.
- **Terms:** fine for a private research tool. **Revisit before Phase 3**, together with OQ2.

## What the Owner signs up for

1. **twitterapi.io**: create an account and add prepaid credits. There's no minimum, so **$10** covers the probe and early testing; ~$20–30/month from M2 on.
2. Add the key as a **GitHub repository secret** named `X_HISTORY_API_KEY` (Settings → Secrets and variables → Actions), then run **Actions → "X history probe" → Run workflow**. The defaults cost at most about $0.30.
3. Later, in M2: the same key goes into Render as `X_RESELLER_API_KEY` (live) and `X_HISTORY_API_KEY` (history).

Nothing else to sign up for. `X_API_KEY` (official X) stays unused unless the decision changes.

## Probe

`backend/scripts/x_history_probe.py` counts posts mentioning **"nullmask"** from 20 Sep to 5 Oct 2026 via twitterapi.io. It saves nothing.

- Without a key, it explains which variable to set.
- With a key, it prints the number of posts, the oldest and newest found, and whether it hit the page limit.

**Result (Owner ran it on 18 Oct 2026 via GitHub Actions):**

| | |
|---|---|
| Posts found | **180** (10 pages; ended on its own, not at the 100-page limit) |
| Oldest | 2026-09-20 14:54 UTC (first day of the window) |
| Newest | 2026-10-05 22:55 UTC (last day of the window) |
| Cost | ≈ $0.03 |

**Conclusion:** twitterapi.io's history covers the whole $MASK window, from the first day to the last, so it is confirmed for both live posts and history. Coverage completeness, i.e. whether the 180 posts are *all* of them, gets spot-checked against SocialData when the M2 backtest adapter is built.

## Sources

- [X API pricing (official docs)](https://docs.x.com/x-api/getting-started/pricing)
- [X API search: full archive on pay-per-use](https://docs.x.com/x-api/posts/search/introduction)
- [twitterapi.io pricing](https://twitterapi.io/pricing)
- [twitterapi.io advanced search docs](https://docs.twitterapi.io/api-reference/endpoint/tweet_advanced_search)
- [twitterapi.io vs SocialData (written by twitterapi.io, so biased; used only for SocialData's listed price and limits)](https://twitterapi.io/compare/vs-socialdata)
- [SocialData search docs](https://docs.socialdata.tools/reference/get-search-results/)
- [Apify tweet scraper pricing examples](https://apify.com/apidojo/tweet-scraper/pricing), [$0.15–0.25 per 1K actors](https://apify.com/theagents/twitter-scraper)
