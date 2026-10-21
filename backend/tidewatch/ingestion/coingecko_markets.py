"""`coingecko_markets`: price, market cap, FDV and 24h volume for tracked tokens (PER-20).

Owner decision (19 Oct 2026, ARCHITECTURE.md §6): CoinGecko's free Demo plan supplies market
data for Mispriced in M1. Birdeye will likely take over EVM/Solana prices from M3, so this is a
self-contained adapter: scoring reads `MarketSnapshot` rows and never knows which adapter wrote
them.

Every `refresh.standard_minutes` it reads `/coins/markets?vs_currency=usd&ids=…` for every
distinct CoinGecko ID on a tracked (non-archived) token, up to 250 IDs per call. One coin
bridged to several chains is several tokens with the same ID; each gets its own snapshot.
Tokens without a CoinGecko ID are skipped (System Health lists them).
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, ClassVar

import httpx
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from tidewatch.db.models import MarketSnapshot, Token
from tidewatch.ingestion.base import Adapter, SourceRecord, SourceUnavailable
from tidewatch.ingestion.coingecko import API_BASE, CoinGeckoCalls, api_key

MARKETS_URL = f"{API_BASE}/coins/markets"
#: CoinGecko's maximum `per_page` for /coins/markets.
BATCH_SIZE = 250
SOURCE = "coingecko"


class CoinMarket(SourceRecord):
    coingecko_id: str = Field(min_length=1)
    price: Decimal = Field(gt=0)
    market_cap: Decimal | None = Field(default=None, ge=0)
    fdv: Decimal | None = Field(default=None, ge=0)
    volume_24h: Decimal | None = Field(default=None, ge=0)


def tracked_ids(session: Session) -> list[str]:
    """Distinct CoinGecko IDs of tracked tokens, in a stable order."""
    rows = session.scalars(
        select(Token.coingecko_id)
        .where(Token.archived_at.is_(None), Token.coingecko_id.is_not(None))
        .distinct()
        .order_by(Token.coingecko_id)
    ).all()
    return [r for r in rows if r]


def _decimal(value: Any) -> Decimal | None:
    """CoinGecko numbers as Decimal. Zero market cap or FDV means "unknown" on CoinGecko."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except ArithmeticError:
        return None
    return number if number > 0 else None


def parse_market(item: Any, now: datetime) -> dict[str, Any] | None:
    if (
        not isinstance(item, dict)
        or not item.get("id")
        or _decimal(item.get("current_price")) is None
    ):
        return None
    return {
        "observed_at": item.get("last_updated") or now,
        "coingecko_id": str(item["id"]),
        "price": _decimal(item.get("current_price")),
        "market_cap": _decimal(item.get("market_cap")),
        "fdv": _decimal(item.get("fully_diluted_valuation")),
        "volume_24h": _decimal(item.get("total_volume")) or Decimal(0),
    }


class CoinGeckoMarkets(CoinGeckoCalls, Adapter):
    name = "coingecko_markets"
    interval_setting: ClassVar[str] = "refresh.standard_minutes"
    record_model: ClassVar[type[SourceRecord]] = CoinMarket

    def __init__(self, http: httpx.Client | None = None) -> None:
        self._http = http

    def fetch(self, session: Session) -> Sequence[Any]:
        key = api_key()
        ids = tracked_ids(session)
        now = datetime.now(UTC)
        records: list[dict[str, Any]] = []
        for start in range(0, len(ids), BATCH_SIZE):
            batch = ids[start : start + BATCH_SIZE]
            body = self.cg_get(
                MARKETS_URL,
                key,
                vs_currency="usd",
                ids=",".join(batch),
                per_page=str(BATCH_SIZE),
                page="1",
            )
            if not isinstance(body, list):
                raise SourceUnavailable("unexpected CoinGecko markets response")
            records.extend(r for r in (parse_market(i, now) for i in body) if r is not None)
        return records

    def store(
        self, session: Session, records: Sequence[SourceRecord], available_at: datetime
    ) -> int:
        tokens: dict[str, list[Token]] = defaultdict(list)
        for token in session.scalars(
            select(Token).where(Token.archived_at.is_(None), Token.coingecko_id.is_not(None))
        ):
            tokens[str(token.coingecko_id)].append(token)
        stored = 0
        for record in records:
            if not isinstance(record, CoinMarket):
                raise TypeError("coingecko_markets received a record of the wrong type")
            for token in tokens.get(record.coingecko_id, []):
                session.add(
                    MarketSnapshot(
                        token_id=token.id,
                        source=SOURCE,
                        observed_at=record.observed_at,
                        available_at=available_at,
                        price=record.price,
                        market_cap=record.market_cap,
                        fdv=record.fdv,
                        volume_24h=record.volume_24h,
                    )
                )
                stored += 1
        return stored
