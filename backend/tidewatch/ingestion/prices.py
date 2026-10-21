"""Choosing a price when sources disagree (PRD 3.3 edge case; PER-20).

PRD 3.3: "Sources disagreeing by more than 5% on price: use the higher-liquidity venue's price
and log the discrepancy." Liquidity per venue isn't available from every source, so the 24-hour
volume each snapshot reports stands in for it: the busier market wins. CoinGecko's aggregate
price (`coingecko`) spans every venue, so it normally wins over a single venue
(`coingecko:safetrade`).

Only snapshots that were available at `now` and are at most `MAX_AGE` old are compared, so a
stale source never overrides a fresh one (and backtests can call this with a past `now`).
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tidewatch.db.models import MarketSnapshot, Token

log = logging.getLogger("tidewatch.prices")

#: PRD 3.3 rule (not a [CALIBRATE] value): more than 5% apart counts as a disagreement.
DISAGREEMENT_THRESHOLD = Decimal("0.05")
#: Technical choice: snapshots older than this aren't compared (sources refresh hourly).
MAX_AGE = timedelta(hours=2)


@dataclass(frozen=True)
class SourcePrice:
    source: str
    price: Decimal
    volume_24h: Decimal
    available_at: datetime


@dataclass(frozen=True)
class PriceChoice:
    chosen: SourcePrice
    sources: list[SourcePrice]
    #: (highest - lowest) / lowest, across sources.
    spread: Decimal

    @property
    def disagrees(self) -> bool:
        return self.spread > DISAGREEMENT_THRESHOLD


def latest_prices(session: Session, token_id: object, now: datetime) -> list[SourcePrice]:
    """The newest usable snapshot per source for one token, as known at `now`."""
    rows = session.scalars(
        select(MarketSnapshot)
        .where(
            MarketSnapshot.token_id == token_id,
            MarketSnapshot.archived_at.is_(None),
            MarketSnapshot.price.is_not(None),
            MarketSnapshot.available_at <= now,
            MarketSnapshot.available_at >= now - MAX_AGE,
        )
        .order_by(MarketSnapshot.available_at.desc())
    ).all()
    newest: dict[str, SourcePrice] = {}
    for row in rows:
        if row.source not in newest and row.price is not None:
            newest[row.source] = SourcePrice(
                row.source, row.price, row.volume_24h or Decimal(0), row.available_at
            )
    return list(newest.values())


def choose_price(prices: list[SourcePrice]) -> PriceChoice | None:
    if not prices:
        return None
    chosen = max(prices, key=lambda p: (p.volume_24h, p.available_at))
    low = min(p.price for p in prices)
    high = max(p.price for p in prices)
    return PriceChoice(chosen=chosen, sources=prices, spread=(high - low) / low)


def preferred_price(session: Session, token_id: object, now: datetime) -> PriceChoice | None:
    """The price scoring should use, logging a warning when sources disagree by more than 5%."""
    choice = choose_price(latest_prices(session, token_id, now))
    if choice is not None and choice.disagrees:
        log.warning(
            "price disagreement for token %s: %s; using %s",
            token_id,
            ", ".join(f"{p.source}={p.price}" for p in choice.sources),
            choice.chosen.source,
        )
    return choice


def disagreements(session: Session, now: datetime) -> list[tuple[Token, PriceChoice]]:
    """Tokens whose sources currently disagree by more than 5% (shown on System Health)."""
    multi = session.execute(
        select(MarketSnapshot.token_id)
        .where(
            MarketSnapshot.archived_at.is_(None),
            MarketSnapshot.available_at <= now,
            MarketSnapshot.available_at >= now - MAX_AGE,
        )
        .group_by(MarketSnapshot.token_id)
        .having(func.count(MarketSnapshot.source.distinct()) > 1)
    ).scalars()
    found: list[tuple[Token, PriceChoice]] = []
    for token_id in multi:
        choice = preferred_price(session, token_id, now)
        token = session.get(Token, token_id)
        if choice is not None and choice.disagrees and token is not None:
            found.append((token, choice))
    return found
