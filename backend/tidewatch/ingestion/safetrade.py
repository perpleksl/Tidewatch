"""`safetrade`: PRL price and 24-hour volume from SafeTrade's public API (spike R1, PER-15).

Source: https://safetrade.com/api/v2/trade/public/tickers (public, no key). On 18 Oct 2026
SafeTrade renamed the market from `prlusdt` to `pearlusdt`, so the market is looked up by its
base unit ("pearl" or "prl") and the USDT quote instead of a fixed ID.

Stored as a MarketSnapshot for the native PRL coin: `price` = last trade (USDT), and
`volume_24h` = the ticker's `volume` field, which is the 24-hour turnover in USDT.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, ClassVar

import httpx
from pydantic import Field
from sqlalchemy.orm import Session

from tidewatch.db.models import MarketSnapshot
from tidewatch.identity.tokens import native_token
from tidewatch.ingestion.base import Adapter, SourceRecord, SourceUnavailable
from tidewatch.ingestion.http import get_json
from tidewatch.ingestion.pow_pearl import PEARL_CHAIN

TICKERS_URL = "https://safetrade.com/api/v2/trade/public/tickers"
PEARL_BASE_UNITS = ("pearl", "prl")
QUOTE_UNIT = "usdt"


class SafeTradeTicker(SourceRecord):
    market: str
    last: Decimal = Field(gt=0)
    volume_usdt: Decimal = Field(ge=0)


def pick_pearl_ticker(tickers: Any, observed_at: datetime) -> dict[str, Any]:
    if not isinstance(tickers, dict):
        raise SourceUnavailable("unexpected SafeTrade response")
    for market_id, ticker in tickers.items():
        if not isinstance(ticker, dict):
            continue
        if ticker.get("base_unit") in PEARL_BASE_UNITS and ticker.get("quote_unit") == QUOTE_UNIT:
            return {
                "observed_at": observed_at,
                "market": market_id,
                "last": ticker.get("last"),
                "volume_usdt": ticker.get("volume"),
            }
    raise SourceUnavailable("no PRL/USDT market on SafeTrade right now")


class SafeTrade(Adapter):
    name = "safetrade"
    interval_setting: ClassVar[str] = "refresh.standard_minutes"
    record_model: ClassVar[type[SourceRecord]] = SafeTradeTicker

    def __init__(self, http: httpx.Client | None = None) -> None:
        self._http = http

    def fetch(self, session: Session) -> Sequence[Any]:
        tickers = get_json(TICKERS_URL, self._http)
        return [pick_pearl_ticker(tickers, datetime.now(UTC))]

    def store(
        self, session: Session, records: Sequence[SourceRecord], available_at: datetime
    ) -> int:
        token = native_token(session, PEARL_CHAIN, name="Pearl", ticker="PRL")
        for record in records:
            if not isinstance(record, SafeTradeTicker):
                raise TypeError("safetrade received a record of the wrong type")
            session.add(
                MarketSnapshot(
                    token_id=token.id,
                    source="safetrade",
                    observed_at=record.observed_at,
                    available_at=available_at,
                    price=record.last,
                    volume_24h=record.volume_usdt,
                )
            )
        return len(records)
