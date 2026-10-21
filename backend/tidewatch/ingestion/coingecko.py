"""`coingecko`: PRL price and 24-hour volume via CoinGecko's free Demo API (PER-18).

Replaces direct SafeTrade calls, which SafeTrade's bot protection blocks from Render (HTTP 403).
SafeTrade stays the price venue (ARCHITECTURE.md Section 6): CoinGecko reports each venue's
PRL ticker, and this adapter reads SafeTrade's.

Source: GET https://api.coingecko.com/api/v3/coins/pearl-2/tickers with the
`x-cg-demo-api-key` header (CoinGecko docs, checked 19 Oct 2026). Key from COINGECKO_API_KEY.

Which ticker is used:
1. SafeTrade's PRL/USDT ticker.
2. If SafeTrade has none, the USDT ticker with the highest 24-hour volume on another venue.
The venue is recorded in the row's `source`, e.g. `coingecko:safetrade`.

The quote currency is matched by CoinGecko coin ID (`tether`), not by ticker. Stale or
anomalous tickers (CoinGecko's own flags) are skipped. Price and volume are stored in USD
(`converted_last.usd`, `converted_volume.usd`), so every venue is in the same unit.
"""

import os
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, ClassVar

import httpx
from pydantic import Field
from sqlalchemy.orm import Session

from tidewatch.db.models import MarketSnapshot
from tidewatch.identity.tokens import native_token
from tidewatch.ingestion.base import Adapter, SourceRecord, SourceUnavailable, Usage
from tidewatch.ingestion.http import get_json
from tidewatch.ingestion.pow_pearl import PEARL_CHAIN

API_BASE = "https://api.coingecko.com/api/v3"
KEY_ENV = "COINGECKO_API_KEY"
KEY_HEADER = "x-cg-demo-api-key"
#: CoinGecko's ID for Pearl ($PRL), checked on coingecko.com/en/coins/pearl-2.
PEARL_COINGECKO_ID = "pearl-2"
TICKERS_URL = f"{API_BASE}/coins/{PEARL_COINGECKO_ID}/tickers"
PREFERRED_VENUE = "safetrade"
USDT_COIN_ID = "tether"


#: The Demo plan's monthly call allowance (coingecko.com/api/pricing, checked 21 Oct 2026).
#: A provider limit, not a product threshold. Tidewatch never upgrades the plan.
MONTHLY_CALL_ALLOWANCE = 10_000
#: The `CostEntry.source` that every CoinGecko adapter counts its calls under.
USAGE_SOURCE = "coingecko"


def api_key() -> str:
    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        raise SourceUnavailable(f"{KEY_ENV} is not set")
    return key


class CoinGeckoCalls:
    """Counts every CoinGecko request an adapter makes, for the monthly allowance (PER-20).

    A request counts even when it fails: CoinGecko counts it too.
    """

    _http: httpx.Client | None
    _cg_calls: int = 0

    def cg_get(self, url: str, key: str, **params: Any) -> Any:
        self._cg_calls += 1
        return get_json(url, self._http, headers={KEY_HEADER: key}, **params)

    def drain_usage(self) -> list[Usage]:
        calls, self._cg_calls = self._cg_calls, 0
        return [Usage(source=USAGE_SOURCE, calls=calls)]


class CoinGeckoTicker(SourceRecord):
    venue: str = Field(min_length=1)
    price_usd: Decimal = Field(gt=0)
    volume_24h_usd: Decimal = Field(ge=0)


def _usd(ticker: dict[str, Any], field: str) -> Any:
    converted = ticker.get(field)
    return converted.get("usd") if isinstance(converted, dict) else None


def _venue(ticker: dict[str, Any]) -> str:
    market = ticker.get("market")
    identifier = market.get("identifier") if isinstance(market, dict) else None
    return str(identifier or "").lower()


def _volume(ticker: dict[str, Any]) -> Decimal:
    try:
        return Decimal(str(_usd(ticker, "converted_volume")))
    except ArithmeticError:
        return Decimal(0)


def pick_prl_ticker(body: Any, now: datetime) -> dict[str, Any]:
    """Choose SafeTrade's PRL/USDT ticker, else the highest-volume USDT ticker elsewhere."""
    if not isinstance(body, dict) or not isinstance(body.get("tickers"), list):
        raise SourceUnavailable("unexpected CoinGecko response")
    usable = [
        t
        for t in body["tickers"]
        if isinstance(t, dict)
        and t.get("target_coin_id") == USDT_COIN_ID
        and not t.get("is_stale")
        and not t.get("is_anomaly")
    ]
    if not usable:
        raise SourceUnavailable("CoinGecko lists no current PRL/USDT ticker")
    preferred = [t for t in usable if _venue(t) == PREFERRED_VENUE]
    chosen = preferred[0] if preferred else max(usable, key=_volume)
    return {
        "observed_at": chosen.get("timestamp") or chosen.get("last_fetch_at") or now,
        "venue": _venue(chosen),
        "price_usd": _usd(chosen, "converted_last"),
        "volume_24h_usd": _usd(chosen, "converted_volume"),
    }


class CoinGecko(CoinGeckoCalls, Adapter):
    name = "coingecko"
    interval_setting: ClassVar[str] = "refresh.standard_minutes"
    record_model: ClassVar[type[SourceRecord]] = CoinGeckoTicker

    def __init__(self, http: httpx.Client | None = None) -> None:
        self._http = http

    def fetch(self, session: Session) -> Sequence[Any]:
        body = self.cg_get(TICKERS_URL, api_key())
        return [pick_prl_ticker(body, datetime.now(UTC))]

    def store(
        self, session: Session, records: Sequence[SourceRecord], available_at: datetime
    ) -> int:
        token = native_token(session, PEARL_CHAIN, name="Pearl", ticker="PRL")
        token.coingecko_id = token.coingecko_id or PEARL_COINGECKO_ID
        for record in records:
            if not isinstance(record, CoinGeckoTicker):
                raise TypeError("coingecko received a record of the wrong type")
            session.add(
                MarketSnapshot(
                    token_id=token.id,
                    source=f"{self.name}:{record.venue}",
                    observed_at=record.observed_at,
                    available_at=available_at,
                    price=record.price_usd,
                    volume_24h=record.volume_24h_usd,
                )
            )
        return len(records)
