"""System Health API (PER-13; PRD 3.12): status of every data source.

Test-only controls for `fake_source` exist on non-production environments so the Owner can
watch a source go OK → Degraded / Paused → OK on staging.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tidewatch.api.auth import protected_router
from tidewatch.api.deps import get_session
from tidewatch.db.models import CoinGeckoListing, CostEntry, SourceStatus, Token
from tidewatch.ingestion.coingecko import MONTHLY_CALL_ALLOWANCE, USAGE_SOURCE
from tidewatch.ingestion.fake import FakeSource
from tidewatch.ingestion.prices import disagreements
from tidewatch.ingestion.registry import (
    RETIRED_SOURCES,
    registered_adapters,
    test_controls_enabled,
)
from tidewatch.ingestion.runner import errors_last_24h, get_status, utc_now

router = protected_router()

DbSession = Annotated[Session, Depends(get_session)]


class SourceOut(BaseModel):
    source: str
    status: str
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    paused_until: datetime | None
    errors_24h: int
    last_error: str | None
    run_requested: bool
    test_mode: str | None
    #: False for entries that aren't data sources (e.g. the AI marketplace): no "Run now".
    runnable: bool


class NewListingOut(BaseModel):
    coingecko_id: str
    name: str
    symbol: str
    chains: list[str]
    outcome: str
    reason: str | None
    candidate_tab: str | None
    first_seen_at: datetime


class NewListingsOut(BaseModel):
    """PER-19: coins newly listed on CoinGecko in the last 7 days (PRD 3.2)."""

    #: When the starting list was recorded; None until discovery has run once.
    starting_list_at: datetime | None
    items: list[NewListingOut]


class CoinGeckoUsageOut(BaseModel):
    """PER-20: CoinGecko calls this calendar month (UTC) against the free plan's allowance."""

    calls_this_month: int
    allowance: int
    projected_month_end: int
    #: True when the projection is above the allowance (a warning; the plan is never upgraded).
    projected_over: bool


class TokenRef(BaseModel):
    name: str
    ticker: str
    chain: str


class SourcePriceOut(BaseModel):
    source: str
    price: Decimal
    volume_24h: Decimal


class PriceDisagreementOut(BaseModel):
    token: TokenRef
    spread_percent: Decimal
    used_source: str
    sources: list[SourcePriceOut]


class MarketDataOut(BaseModel):
    """PER-20: which tracked tokens can get market data, and current price disagreements."""

    tokens_with_coingecko_id: int
    tokens_without_coingecko_id: int
    #: Up to `MISSING_LIST_MAX` of them, each "Not available: not listed on CoinGecko".
    without_coingecko_id: list[TokenRef]
    price_disagreements: list[PriceDisagreementOut]


class SystemHealthOut(BaseModel):
    sources: list[SourceOut]
    test_controls: bool
    new_listings: NewListingsOut
    coingecko_usage: CoinGeckoUsageOut
    market_data: MarketDataOut


class TestModeIn(BaseModel):
    mode: Literal["normal", "fail", "rate_limit", "invalid"]


def _out(row: SourceStatus, now: datetime) -> SourceOut:
    runnable = row.source in {a.name for a in registered_adapters()}
    return SourceOut(
        runnable=runnable,
        source=row.source,
        status=row.status,
        last_success_at=row.last_success_at,
        last_attempt_at=row.last_attempt_at,
        paused_until=row.paused_until,
        errors_24h=errors_last_24h(row, now),
        last_error=row.last_error,
        run_requested=row.run_requested_at is not None,
        test_mode=row.test_mode,
    )


def archive_retired_sources(db: Session) -> None:
    """Hide replaced sources from System Health (soft delete; their data rows stay)."""
    now = utc_now()
    for row in db.scalars(
        select(SourceStatus).where(
            SourceStatus.source.in_(RETIRED_SOURCES), SourceStatus.archived_at.is_(None)
        )
    ):
        row.archived_at = now


NEW_LISTINGS_DAYS = 7
#: Display limit for the section (a technical cap, not a product threshold).
NEW_LISTINGS_MAX = 200


def new_listings(db: Session, now: datetime) -> NewListingsOut:
    starting_at = db.scalar(
        select(func.min(CoinGeckoListing.first_seen_at)).where(
            CoinGeckoListing.in_starting_list.is_(True)
        )
    )
    rows = db.scalars(
        select(CoinGeckoListing)
        .where(
            CoinGeckoListing.in_starting_list.is_(False),
            CoinGeckoListing.archived_at.is_(None),
            CoinGeckoListing.first_seen_at >= now - timedelta(days=NEW_LISTINGS_DAYS),
        )
        .order_by(CoinGeckoListing.first_seen_at.desc(), CoinGeckoListing.name)
        .limit(NEW_LISTINGS_MAX)
    ).all()
    return NewListingsOut(
        starting_list_at=starting_at,
        items=[
            NewListingOut(
                coingecko_id=r.coingecko_id,
                name=r.name,
                symbol=r.symbol,
                chains=list(r.chains or []),
                outcome=r.outcome or "unresolved",
                reason=r.reason,
                candidate_tab=r.candidate_tab,
                first_seen_at=r.first_seen_at,
            )
            for r in rows
        ],
    )


MISSING_LIST_MAX = 50


def _month_start(now: datetime) -> datetime:
    utc = now.astimezone(UTC)
    return utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_month_start(start: datetime) -> datetime:
    return (start + timedelta(days=32)).replace(day=1)


def coingecko_usage(db: Session, now: datetime) -> CoinGeckoUsageOut:
    start = _month_start(now)
    calls = int(
        db.scalar(
            select(func.coalesce(func.sum(CostEntry.calls), 0)).where(
                CostEntry.source == USAGE_SOURCE,
                CostEntry.archived_at.is_(None),
                CostEntry.at >= start,
            )
        )
        or 0
    )
    month = (_next_month_start(start) - start).total_seconds()
    elapsed = max((now - start).total_seconds(), 3600.0)  # avoid wild projections on day 1
    projected = round(calls * month / elapsed) if calls else 0
    return CoinGeckoUsageOut(
        calls_this_month=calls,
        allowance=MONTHLY_CALL_ALLOWANCE,
        projected_month_end=projected,
        projected_over=projected > MONTHLY_CALL_ALLOWANCE,
    )


def _ref(token: Token) -> TokenRef:
    return TokenRef(name=token.name, ticker=token.ticker, chain=token.chain)


def market_data(db: Session, now: datetime) -> MarketDataOut:
    tracked = Token.archived_at.is_(None)
    with_id = db.scalar(select(func.count()).where(tracked, Token.coingecko_id.is_not(None)))
    missing_q = select(Token).where(tracked, Token.coingecko_id.is_(None))
    missing = db.scalar(select(func.count()).select_from(missing_q.subquery()))
    shown = db.scalars(missing_q.order_by(Token.name).limit(MISSING_LIST_MAX)).all()
    return MarketDataOut(
        tokens_with_coingecko_id=int(with_id or 0),
        tokens_without_coingecko_id=int(missing or 0),
        without_coingecko_id=[_ref(t) for t in shown],
        price_disagreements=[
            PriceDisagreementOut(
                token=_ref(token),
                spread_percent=(choice.spread * 100).quantize(Decimal("0.1")),
                used_source=choice.chosen.source,
                sources=[
                    SourcePriceOut(source=p.source, price=p.price, volume_24h=p.volume_24h)
                    for p in sorted(choice.sources, key=lambda p: p.source)
                ],
            )
            for token, choice in disagreements(db, now)
        ],
    )


@router.get("/system-health")
def system_health(db: DbSession) -> SystemHealthOut:
    """Every registered source, including ones that have never run yet."""
    for adapter in registered_adapters():
        get_status(db, adapter.name)
    archive_retired_sources(db)
    rows = db.scalars(
        select(SourceStatus).where(SourceStatus.archived_at.is_(None)).order_by(SourceStatus.source)
    ).all()
    now = utc_now()
    return SystemHealthOut(
        sources=[_out(r, now) for r in rows],
        test_controls=test_controls_enabled(),
        new_listings=new_listings(db, now),
        coingecko_usage=coingecko_usage(db, now),
        market_data=market_data(db, now),
    )


def _known_source(source: str) -> None:
    if source not in {a.name for a in registered_adapters()}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown source")


@router.post("/system-health/{source}/run")
def run_now(source: str, db: DbSession) -> SourceOut:
    """Ask the worker to run this source on its next check (within about 15 seconds)."""
    _known_source(source)
    row = get_status(db, source)
    row.run_requested_at = utc_now()
    return _out(row, utc_now())


@router.post("/system-health/fake_source/test-mode")
def set_test_mode(body: TestModeIn, db: DbSession) -> SourceOut:
    """Make fake_source misbehave (or go back to normal). Not available in production."""
    if not test_controls_enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not available")
    row = get_status(db, FakeSource.name)
    row.test_mode = None if body.mode == "normal" else body.mode
    return _out(row, utc_now())
