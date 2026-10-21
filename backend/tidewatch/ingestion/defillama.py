"""`defillama`: fees, revenue, TVL, and which token belongs to which protocol (PER-21; PRD 3.5).

DefiLlama's free API (no key; about 500 requests per 5 minutes):
- `GET https://api.llama.fi/protocols`: every protocol with its token (`address` as
  "chain:0x…", or a bare "0x…" on Ethereum), `gecko_id`, `category`, `url`, `twitter`,
  `github`, `tvl` and `mcap`.
- `GET https://api.llama.fi/overview/fees?dataType=dailyFees` and `dataType=dailyRevenue`
  (with `excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true`): each protocol's
  `total24h`, matched by `slug`.
- History (separate adapter `defillama_history`, below): `GET /summary/fees/{slug}?dataType=…`
  (`totalDataChart` as [[unix_seconds, usd], …]). A protocol with no fee data answers 400;
  that means "no history", not a failure.
Field names follow DefiLlama's API docs and SDKs (checked 21 Oct 2026); parsing is tolerant
of missing fields, and anything unusable is skipped rather than guessed.

**Identity:** a protocol's token is its chain + contract address (chain prefixes mapped in
`identity/chains.py`). Several protocols can share one token (e.g. versions of the same
project); their fees, revenue and TVL are summed per token, and the largest protocol by TVL
names the token's main slug and category. Protocols without a token, or on chains outside the
universe, create nothing. Never matched by ticker.

**Backfill (point-in-time rule), adapter `defillama_history`:** up to 60 days of daily fees and
revenue per token, fetched once, `BACKFILL_PER_RUN` tokens per run. It is a separate job so a
slow or failing backfill can never cost the hourly update its data (21 Oct 2026: the first
combined run was killed for memory while downloading full TVL histories, and nothing was
saved). TVL history isn't backfilled: DefiLlama's per-protocol history is too large for the
worker; TVL history builds up from the hourly rows instead. Backfilled rows keep the day they
describe as `observed_at`, but `available_at` is the time Tidewatch fetched them, never the
past, so backtests can't use them before that moment.
"""

import time
import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

import httpx
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tidewatch.db.models import FundamentalSnapshot, MarketSnapshot, Token
from tidewatch.db.settings import get_setting
from tidewatch.identity.chains import DEFILLAMA_CHAINS
from tidewatch.identity.tokens import contract_token
from tidewatch.ingestion.base import Adapter, SourceRecord, SourceUnavailable
from tidewatch.ingestion.http import get_json

API_BASE = "https://api.llama.fi"
SOURCE = "defillama"
PROTOCOLS_URL = f"{API_BASE}/protocols"
FEES_URL = f"{API_BASE}/overview/fees"
HISTORY_DAYS = 60
#: DefiLlama answers these when a protocol has no fee data: an empty history, not a failure.
NO_DATA_ANSWERS = frozenset({"HTTP 400", "HTTP 404"})
#: Storage guard (technical, not a product threshold): a token's current figures are written
#: when they moved by at least this much since its last row, or once a day regardless. Daily fee
#: and revenue figures change once a day; this stops hourly runs repeating identical rows.
MIN_CHANGE = Decimal("0.01")
REWRITE_AFTER = timedelta(hours=24)
#: Technical limit: up to 2 calls per protocol, well under DefiLlama's ~500 per 5 minutes.
BACKFILL_PER_RUN = 30
CALL_SPACING_SECONDS = 0.7


class Day(SourceRecord):
    """One day of history (observed_at is that day, 00:00 UTC)."""

    fees: Decimal | None = None
    revenue: Decimal | None = None
    tvl: Decimal | None = None


class LlamaRecord(SourceRecord):
    chain: str = Field(min_length=1)
    address: str = Field(min_length=1)
    name: str = ""
    symbol: str = ""
    gecko_id: str | None = None
    category: str | None = None
    slug: str | None = None
    slugs: list[str] = Field(default_factory=list)
    links: dict[str, Any] = Field(default_factory=dict)
    fees: Decimal | None = None
    revenue: Decimal | None = None
    tvl: Decimal | None = None


def _dec(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def parse_address(address: Any, chain_hint: Any = None) -> tuple[str, str] | None:
    """DefiLlama "chain:addr" (or bare "0x…" = Ethereum) → (Tidewatch chain, address)."""
    if not isinstance(address, str) or not address.strip() or address.strip() == "-":
        return None
    text = address.strip()
    if ":" in text:
        prefix, _, addr = text.partition(":")
        chain = DEFILLAMA_CHAINS.get(prefix.lower())
    elif text.lower().startswith("0x"):
        chain, addr = "ethereum", text
    else:
        chain = DEFILLAMA_CHAINS.get(str(chain_hint or "").lower())
        addr = text
    if chain is None or not addr:
        return None
    return chain, (addr if chain == "solana" else addr.lower())


def _links(protocol: dict[str, Any]) -> dict[str, Any]:
    links: dict[str, Any] = {}
    if isinstance(protocol.get("url"), str) and protocol["url"]:
        links["website"] = protocol["url"]
    if isinstance(protocol.get("twitter"), str) and protocol["twitter"]:
        links["twitter"] = f"https://x.com/{protocol['twitter']}"
    github = protocol.get("github")
    if isinstance(github, list) and github:
        links["github"] = [f"https://github.com/{g}" for g in github if isinstance(g, str) and g]
    return links


def _totals(body: Any) -> dict[str, Decimal]:
    """slug → total24h from an /overview/fees answer."""
    if not isinstance(body, dict) or not isinstance(body.get("protocols"), list):
        raise SourceUnavailable("unexpected DefiLlama fees response")
    totals: dict[str, Decimal] = {}
    for item in body["protocols"]:
        if isinstance(item, dict) and item.get("slug"):
            value = _dec(item.get("total24h"))
            if value is not None:
                totals[str(item["slug"])] = value
    return totals


def group_protocols(
    protocols: Any, fees: dict[str, Decimal], revenue: dict[str, Decimal], now: datetime
) -> list[dict[str, Any]]:
    """One "current" record per token, summing every protocol that shares it."""
    if not isinstance(protocols, list):
        raise SourceUnavailable("unexpected DefiLlama protocols response")
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for protocol in protocols:
        if not isinstance(protocol, dict) or not protocol.get("slug"):
            continue
        identity = parse_address(protocol.get("address"), protocol.get("chain"))
        if identity is not None:
            groups[identity].append(protocol)
    records = []
    for (chain, address), members in groups.items():
        main = max(members, key=lambda p: _dec(p.get("tvl")) or Decimal(0))
        slugs = sorted(str(p["slug"]) for p in members)

        def total(source: dict[str, Decimal], slug_list: list[str] = slugs) -> Decimal | None:
            values = [source[s] for s in slug_list if s in source]
            return sum(values, Decimal(0)) if values else None

        tvls = [v for v in (_dec(p.get("tvl")) for p in members) if v is not None]
        records.append(
            {
                "observed_at": now,
                "chain": chain,
                "address": address,
                "name": str(main.get("name") or main["slug"]),
                "symbol": str(main.get("symbol") or ""),
                "gecko_id": main.get("gecko_id")
                or next((p["gecko_id"] for p in members if p.get("gecko_id")), None),
                "category": main.get("category"),
                "slug": str(main["slug"]),
                "slugs": slugs,
                "links": _links(main),
                "fees": total(fees),
                "revenue": total(revenue),
                "tvl": sum(tvls, Decimal(0)) if tvls else None,
            }
        )
    return records


def _day(ts: Any) -> datetime | None:
    try:
        moment = datetime.fromtimestamp(int(ts), tz=UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


def _chart(body: Any) -> dict[datetime, Decimal]:
    points: dict[datetime, Decimal] = {}
    chart = body.get("totalDataChart") if isinstance(body, dict) else None
    for point in chart if isinstance(chart, list) else []:
        if isinstance(point, list) and len(point) >= 2:
            day, value = _day(point[0]), _dec(point[1])
            if day is not None and value is not None:
                points[day] = points.get(day, Decimal(0)) + value
    return points


class DefiLlama(Adapter):
    name = SOURCE
    interval_setting: ClassVar[str] = "refresh.standard_minutes"
    record_model: ClassVar[type[SourceRecord]] = LlamaRecord

    def __init__(
        self, http: httpx.Client | None = None, sleep: Callable[[float], None] = time.sleep
    ) -> None:
        self._http = http
        self._sleep = sleep

    def _get(self, url: str, **params: Any) -> Any:
        return get_json(url, self._http, **params)

    def fetch(self, session: Session) -> Sequence[Any]:
        now = datetime.now(UTC)
        protocols = self._get(PROTOCOLS_URL)
        overview = {"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true"}
        fees = _totals(self._get(FEES_URL, dataType="dailyFees", **overview))
        revenue = _totals(self._get(FEES_URL, dataType="dailyRevenue", **overview))
        return group_protocols(protocols, fees, revenue, now)

    @staticmethod
    def _latest(session: Session) -> dict[uuid.UUID, FundamentalSnapshot]:
        newest = (
            select(
                FundamentalSnapshot.token_id,
                func.max(FundamentalSnapshot.available_at).label("newest"),
            )
            .where(FundamentalSnapshot.source == SOURCE, FundamentalSnapshot.archived_at.is_(None))
            .group_by(FundamentalSnapshot.token_id)
            .subquery()
        )
        rows = session.scalars(
            select(FundamentalSnapshot)
            .join(
                newest,
                (newest.c.token_id == FundamentalSnapshot.token_id)
                & (newest.c.newest == FundamentalSnapshot.available_at),
            )
            .where(FundamentalSnapshot.source == SOURCE)
        )
        latest: dict[uuid.UUID, FundamentalSnapshot] = {}
        for row in rows:  # a backfill writes many rows at once: keep the newest day
            kept = latest.get(row.token_id)
            if kept is None or row.observed_at > kept.observed_at:
                latest[row.token_id] = row
        return latest

    @staticmethod
    def _changed(last: FundamentalSnapshot | None, record: LlamaRecord, now: datetime) -> bool:
        if last is None or now - last.available_at >= REWRITE_AFTER:
            return True
        for old, new in (
            (last.fees, record.fees),
            (last.revenue, record.revenue),
            (last.tvl, record.tvl),
        ):
            if (old is None) != (new is None):
                return True
            if old is not None and new is not None:
                if old == 0:
                    if new != 0:
                        return True
                elif abs(new - old) / abs(old) >= MIN_CHANGE:
                    return True
        return False

    def store(
        self, session: Session, records: Sequence[SourceRecord], available_at: datetime
    ) -> int:
        stored = 0
        latest = self._latest(session)
        for record in records:
            if not isinstance(record, LlamaRecord):
                raise TypeError("defillama received a record of the wrong type")
            token = contract_token(
                session, record.chain, record.address, record.name, record.symbol.upper()
            )
            token.coingecko_id = token.coingecko_id or record.gecko_id
            token.defillama_slug = record.slug
            token.category = record.category
            token.links = {**(token.links or {}), **record.links, "defillama_slugs": record.slugs}
            if self._changed(latest.get(token.id), record, available_at):
                session.add(self._snapshot(token.id, record.observed_at, available_at, record))
                stored += 1
        return stored

    @staticmethod
    def _snapshot(
        token_id: uuid.UUID, observed_at: datetime, available_at: datetime, data: Day | LlamaRecord
    ) -> FundamentalSnapshot:
        return FundamentalSnapshot(
            token_id=token_id,
            source=SOURCE,
            observed_at=observed_at,
            available_at=available_at,
            fees=data.fees,
            revenue=data.revenue,
            tvl=data.tvl,
        )


class HistoryRecord(SourceRecord):
    token_id: str = Field(min_length=1)
    days: list[Day] = Field(default_factory=list)


def history_queue(session: Session, now: datetime) -> list[Token]:
    """Tokens without history yet, those in Mispriced's market-cap range (or not yet priced)
    first, so the tokens that can actually appear get history soonest."""
    low = get_setting(session, "mispriced.market_cap_min_usd")
    high = get_setting(session, "mispriced.market_cap_max_usd")
    newest = (
        select(MarketSnapshot.token_id, func.max(MarketSnapshot.available_at).label("at"))
        .where(MarketSnapshot.market_cap.is_not(None), MarketSnapshot.available_at <= now)
        .group_by(MarketSnapshot.token_id)
        .subquery()
    )
    caps = dict(
        session.execute(
            select(MarketSnapshot.token_id, MarketSnapshot.market_cap).join(
                newest,
                (newest.c.token_id == MarketSnapshot.token_id)
                & (newest.c.at == MarketSnapshot.available_at),
            )
        ).all()
    )
    pending = list(
        session.scalars(
            select(Token).where(
                Token.archived_at.is_(None),
                Token.defillama_slug.is_not(None),
                Token.defillama_backfilled_at.is_(None),
            )
        )
    )

    def priority(token: Token) -> tuple[int, str]:
        cap = caps.get(token.id)
        return (0 if cap is None or low <= cap <= high else 1, token.name)

    pending.sort(key=priority)
    return pending[:BACKFILL_PER_RUN]


class DefiLlamaHistory(Adapter):
    """One-time 60-day fees and revenue history per token (see the module docstring)."""

    name = "defillama_history"
    interval_setting: ClassVar[str] = "refresh.standard_minutes"
    record_model: ClassVar[type[SourceRecord]] = HistoryRecord

    def __init__(
        self, http: httpx.Client | None = None, sleep: Callable[[float], None] = time.sleep
    ) -> None:
        self._http = http
        self._sleep = sleep

    def _chart(self, slug: str, data_type: str) -> dict[datetime, Decimal]:
        self._sleep(CALL_SPACING_SECONDS)
        try:
            body = get_json(
                f"{API_BASE}/summary/fees/{slug}",
                self._http,
                dataType=data_type,
                excludeTotalDataChartBreakdown="true",
            )
        except SourceUnavailable as exc:
            if str(exc) in NO_DATA_ANSWERS:
                return {}  # DefiLlama has no fee data for this protocol
            raise
        return _chart(body)

    def fetch(self, session: Session) -> Sequence[Any]:
        now = datetime.now(UTC)
        start = (now - timedelta(days=HISTORY_DAYS)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        records: list[dict[str, Any]] = []
        for token in history_queue(session, now):
            slugs = (token.links or {}).get("defillama_slugs") or [token.defillama_slug]
            fees: dict[datetime, Decimal] = defaultdict(Decimal)
            revenue: dict[datetime, Decimal] = defaultdict(Decimal)
            try:
                for slug in slugs:
                    slug_fees = self._chart(str(slug), "dailyFees")
                    if not slug_fees:
                        continue  # no fee data means no revenue data either; save a call
                    for day, v in slug_fees.items():
                        fees[day] += v
                    for day, v in self._chart(str(slug), "dailyRevenue").items():
                        revenue[day] += v
            except SourceUnavailable:
                continue  # retried next run
            days = sorted(d for d in {*fees, *revenue} if start <= d < today)
            records.append(
                {
                    "observed_at": now,
                    "token_id": str(token.id),
                    "days": [
                        {"observed_at": d, "fees": fees.get(d), "revenue": revenue.get(d)}
                        for d in days
                    ],
                }
            )
        return records

    def store(
        self, session: Session, records: Sequence[SourceRecord], available_at: datetime
    ) -> int:
        stored = 0
        for record in records:
            if not isinstance(record, HistoryRecord):
                raise TypeError("defillama_history received a record of the wrong type")
            token_id = uuid.UUID(record.token_id)
            for day in record.days:
                session.add(DefiLlama._snapshot(token_id, day.observed_at, available_at, day))
                stored += 1
            token = session.get(Token, token_id)
            if token is not None:
                token.defillama_backfilled_at = available_at
        return stored
