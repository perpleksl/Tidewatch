"""`coingecko_listings`: daily new-listing discovery from CoinGecko (PER-19; PRD 3.2).

Once a day (`refresh.discovery_minutes`, default 1440) it reads CoinGecko's full coin list
(`/coins/list?include_platform=true`, free Demo plan) and compares it with every coin ID seen
before. The first run records a **starting list** and flags nothing. Coins that appear later
are **new listings**:

- **Contract tokens:** each contract on a covered chain (`identity.chains`) becomes or reuses a
  Token by chain + contract address. A coin whose platforms are all on other chains is
  "Outside the covered universe".
- **Native coins** (no platforms): covered only if it is a PoW coin listed on SafeTrade. That
  takes two calls per coin (`/coins/{id}/tickers?exchange_ids=safetrade` and `/coins/{id}`),
  so at most `NATIVE_CHECKS_PER_RUN` are checked per run. The rest, and any whose check
  failed, are kept as "unresolved" and retried on the next run.
- **Candidate tab:** launched less than `launches.max_age_hours` ago → `launches`, otherwise
  `mispriced`. If the launch time is unknown, it counts as older (Owner decision, 19 Oct 2026).
  Only native coins have a launch time for now (CoinGecko's `genesis_date`); contract tokens
  get theirs from Birdeye once that adapter exists.

The quote and the coin are never matched by ticker; symbols are stored for display only.
"""

import time
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any, ClassVar

import httpx
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from tidewatch.db.models import CoinGeckoListing
from tidewatch.db.settings import get_setting
from tidewatch.identity.chains import COINGECKO_PLATFORMS, native_chain_name
from tidewatch.identity.tokens import contract_token, native_token
from tidewatch.ingestion.base import Adapter, RateLimited, SourceRecord, SourceUnavailable
from tidewatch.ingestion.coingecko import API_BASE, CoinGeckoCalls, api_key

LIST_URL = f"{API_BASE}/coins/list"
#: Technical limit, not a product threshold: the Demo plan allows ~30 calls a minute.
NATIVE_CHECKS_PER_RUN = 10
#: Pause between per-coin calls, to stay under the Demo plan's per-minute limit.
CALL_SPACING_SECONDS = 2.5
SAFETRADE_EXCHANGE_ID = "safetrade"
POW_CATEGORY = "proof of work"

OUTSIDE = "Outside the covered universe"
REASON_ASSESSED = "In the covered universe; waiting for meme classification and scoring"
REASON_POSTPONED = "Native coin check postponed to the next run (daily check limit)"
REASON_NO_CONTRACT = "No contract address on a covered chain"


class ListingRecord(SourceRecord):
    coingecko_id: str = Field(min_length=1)
    name: str
    symbol: str
    starting: bool = False
    #: Covered (chain, contract) pairs. Empty for native coins and uncovered tokens.
    contracts: list[tuple[str, str]] = Field(default_factory=list)
    native: bool = False
    #: Native coins only: None = not checked yet (or the check failed).
    on_safetrade: bool | None = None
    is_pow: bool | None = None
    check_error: str | None = None
    launched_at: datetime | None = None
    #: Has platforms, but none on a covered chain.
    uncovered_platforms: bool = False


def _platforms(coin: dict[str, Any]) -> dict[str, str]:
    raw = coin.get("platforms")
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v).strip() for k, v in raw.items() if k and v and str(v).strip()}


def _genesis(detail: dict[str, Any]) -> datetime | None:
    value = detail.get("genesis_date")
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.combine(date.fromisoformat(value), datetime.min.time(), tzinfo=UTC)
    except ValueError:
        return None


class CoinGeckoListings(CoinGeckoCalls, Adapter):
    name = "coingecko_listings"
    interval_setting: ClassVar[str] = "refresh.discovery_minutes"
    record_model: ClassVar[type[SourceRecord]] = ListingRecord

    def __init__(
        self, http: httpx.Client | None = None, sleep: Callable[[float], None] = time.sleep
    ) -> None:
        self._http = http
        self._sleep = sleep

    # --- fetch: network and reads only ------------------------------------------------------

    def fetch(self, session: Session) -> Sequence[Any]:
        key = api_key()
        coins = self.cg_get(LIST_URL, key, include_platform="true")
        if not isinstance(coins, list):
            raise SourceUnavailable("unexpected CoinGecko coin list")
        now = datetime.now(UTC)
        known = dict(
            session.execute(select(CoinGeckoListing.coingecko_id, CoinGeckoListing.outcome)).all()
        )
        starting = not known

        records: list[dict[str, Any]] = []
        checks_left = NATIVE_CHECKS_PER_RUN
        for coin in coins:
            if not isinstance(coin, dict) or not coin.get("id"):
                continue
            coin_id = str(coin["id"])
            base = {
                "observed_at": now,
                "coingecko_id": coin_id,
                "name": str(coin.get("name") or coin_id),
                "symbol": str(coin.get("symbol") or ""),
            }
            if starting:
                records.append({**base, "starting": True})
                continue
            # New coins, plus earlier new listings still unresolved (retried every run).
            if coin_id in known and known[coin_id] != "unresolved":
                continue
            platforms = _platforms(coin)
            if platforms:
                covered = [
                    (COINGECKO_PLATFORMS[p], addr)
                    for p, addr in platforms.items()
                    if p in COINGECKO_PLATFORMS
                ]
                records.append({**base, "contracts": covered, "uncovered_platforms": not covered})
                continue
            record = {**base, "native": True}
            if checks_left > 0:
                checks_left -= 1
                record.update(self._check_native(coin_id, key))
            records.append(record)
        return records

    def _check_native(self, coin_id: str, key: str) -> dict[str, Any]:
        """Is this native coin listed on SafeTrade, and is it PoW? Two calls, spaced out."""
        try:
            self._sleep(CALL_SPACING_SECONDS)
            tickers = self.cg_get(
                f"{API_BASE}/coins/{coin_id}/tickers",
                key,
                exchange_ids=SAFETRADE_EXCHANGE_ID,
            )
            self._sleep(CALL_SPACING_SECONDS)
            detail = self.cg_get(
                f"{API_BASE}/coins/{coin_id}",
                key,
                localization="false",
                tickers="false",
                market_data="false",
                community_data="false",
                developer_data="false",
            )
        except RateLimited:
            raise
        except SourceUnavailable as exc:
            return {"check_error": f"Native coin check failed ({exc}); retried next run"}
        listed = isinstance(tickers, dict) and bool(tickers.get("tickers"))
        categories = detail.get("categories") if isinstance(detail, dict) else None
        is_pow = isinstance(categories, list) and any(
            POW_CATEGORY in str(c).lower() for c in categories
        )
        launched = _genesis(detail) if isinstance(detail, dict) else None
        return {"on_safetrade": listed, "is_pow": is_pow, "launched_at": launched}

    # --- store: writes ------------------------------------------------------------------------

    def store(
        self, session: Session, records: Sequence[SourceRecord], available_at: datetime
    ) -> int:
        window = timedelta(hours=int(get_setting(session, "launches.max_age_hours")))
        existing = {
            row.coingecko_id: row
            for row in session.scalars(
                select(CoinGeckoListing).where(CoinGeckoListing.outcome == "unresolved")
            )
        }
        for record in records:
            if not isinstance(record, ListingRecord):
                raise TypeError("coingecko_listings received a record of the wrong type")
            if record.starting:
                session.add(
                    CoinGeckoListing(
                        coingecko_id=record.coingecko_id,
                        name=record.name,
                        symbol=record.symbol,
                        first_seen_at=available_at,
                        in_starting_list=True,
                        chains=[],
                    )
                )
                continue
            row = existing.get(record.coingecko_id)
            if row is None:
                row = CoinGeckoListing(
                    coingecko_id=record.coingecko_id,
                    name=record.name,
                    symbol=record.symbol,
                    first_seen_at=available_at,
                    chains=[],
                )
                session.add(row)
            self._resolve(session, row, record, available_at, window)
        return len(records)

    def _resolve(
        self,
        session: Session,
        row: CoinGeckoListing,
        record: ListingRecord,
        now: datetime,
        window: timedelta,
    ) -> None:
        row.launched_at = record.launched_at
        if record.native:
            if record.check_error is not None or record.on_safetrade is None:
                row.outcome, row.reason = "unresolved", record.check_error or REASON_POSTPONED
                return
            if not (record.on_safetrade and record.is_pow):
                row.outcome, row.reason = "outside_universe", OUTSIDE
                return
            chain = native_chain_name(record.coingecko_id)
            token = native_token(session, chain, name=record.name, ticker=record.symbol.upper())
            token.coingecko_id = token.coingecko_id or record.coingecko_id
            row.chains, row.token_id = [chain], token.id
        elif record.contracts:
            tokens = [
                contract_token(session, chain, address, record.name, record.symbol.upper())
                for chain, address in record.contracts
            ]
            for t in tokens:
                t.coingecko_id = t.coingecko_id or record.coingecko_id
            row.chains = sorted({t.chain for t in tokens})
            row.token_id = tokens[0].id
        elif record.uncovered_platforms:
            row.outcome, row.reason = "outside_universe", OUTSIDE
            return
        else:  # pragma: no cover - fetch never produces this combination
            row.outcome, row.reason = "unresolved", REASON_NO_CONTRACT
            return
        row.outcome, row.reason = "assessed", REASON_ASSESSED
        young = record.launched_at is not None and now - record.launched_at < window
        row.candidate_tab = "launches" if young else "mispriced"
