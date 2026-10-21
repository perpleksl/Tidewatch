"""PER-20: market data for tracked tokens via CoinGecko. Mocked responses, synthetic IDs."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from tidewatch.db.models import CostEntry, MarketSnapshot, Token
from tidewatch.ingestion.coingecko import KEY_HEADER, TICKERS_URL, CoinGecko
from tidewatch.ingestion.coingecko_listings import LIST_URL, CoinGeckoListings
from tidewatch.ingestion.coingecko_markets import BATCH_SIZE, CoinGeckoMarkets
from tidewatch.ingestion.prices import choose_price, disagreements, preferred_price
from tidewatch.ingestion.runner import get_status, run_adapter

T0 = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def market(coin_id: str, price: str = "1.5", **extra: Any) -> dict[str, Any]:
    return {
        "id": coin_id,
        "symbol": "tst",
        "name": coin_id,
        "current_price": float(price),
        "market_cap": 12_000_000,
        "fully_diluted_valuation": 30_000_000,
        "total_volume": 800_000,
        "last_updated": "2026-10-21T11:58:00.000Z",
        **extra,
    }


class FakeMarkets:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, headers={"Retry-After": "60"})
        ids = request.url.params["ids"].split(",")
        return httpx.Response(200, json=[market(i) for i in ids if i != "test-delisted"])

    def adapter(self) -> CoinGeckoMarkets:
        return CoinGeckoMarkets(http=httpx.Client(transport=httpx.MockTransport(self.handler)))


@pytest.fixture(autouse=True)
def coingecko_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COINGECKO_API_KEY", "test-key")


def add_tokens(sessions: sessionmaker[Session], *specs: tuple[str, str | None]) -> None:
    """(contract, coingecko_id) pairs on a synthetic chain."""
    with sessions.begin() as s:
        for contract, cg_id in specs:
            s.add(
                Token(
                    chain="ethereum",
                    contract_address=contract,
                    name=f"Test {contract}",
                    ticker="TST",
                    coingecko_id=cg_id,
                )
            )


def run(sessions: sessionmaker[Session], adapter: Any, at: datetime = T0) -> str:
    return run_adapter(sessions, adapter, lambda: at, lambda _: None)


def test_ac1_tracked_tokens_get_hourly_market_snapshots(sessions: sessionmaker[Session]) -> None:
    """AC1: each tracked token with a CoinGecko ID gets a MarketSnapshot with price, market cap,
    FDV, volume, source and available_at."""
    add_tokens(sessions, ("0xtest01", "test-coin-a"))
    fake = FakeMarkets()
    assert run(sessions, fake.adapter()) == "ok"
    with sessions() as s:
        [row] = s.scalars(select(MarketSnapshot)).all()
        assert (row.source, row.price, row.market_cap, row.fdv, row.volume_24h) == (
            "coingecko",
            Decimal("1.5"),
            Decimal(12_000_000),
            Decimal(30_000_000),
            Decimal(800_000),
        )
        assert row.available_at == T0
        assert row.observed_at == datetime(2026, 10, 21, 11, 58, tzinfo=UTC)
        assert get_status(s, "coingecko_markets").status == "ok"
    request = fake.requests[0]
    assert request.headers[KEY_HEADER] == "test-key"
    assert request.url.params["vs_currency"] == "usd"


def test_ac1_one_coin_on_several_chains_updates_every_token(
    sessions: sessionmaker[Session],
) -> None:
    add_tokens(sessions, ("0xtest01", "test-bridged"), ("0xtest02", "test-bridged"))
    fake = FakeMarkets()
    assert run(sessions, fake.adapter()) == "ok"
    assert fake.requests[0].url.params["ids"] == "test-bridged"
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(MarketSnapshot)) == 2


def test_ac2_more_than_250_tokens_are_fetched_in_batches(sessions: sessionmaker[Session]) -> None:
    """AC2: more than 250 tracked tokens → batches of up to 250, one call per batch."""
    add_tokens(sessions, *[(f"0xtest{i:04d}", f"test-coin-{i:04d}") for i in range(BATCH_SIZE + 3)])
    fake = FakeMarkets()
    assert run(sessions, fake.adapter()) == "ok"
    sizes = [len(r.url.params["ids"].split(",")) for r in fake.requests]
    assert sizes == [BATCH_SIZE, 3]
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(MarketSnapshot)) == BATCH_SIZE + 3


def test_ac4_tokens_without_a_coingecko_id_are_skipped(sessions: sessionmaker[Session]) -> None:
    """AC4: a token without a CoinGecko ID is skipped (System Health lists it)."""
    add_tokens(sessions, ("0xtest01", None))
    fake = FakeMarkets()
    assert run(sessions, fake.adapter()) == "ok"
    assert fake.requests == []
    with sessions() as s:
        assert s.scalars(select(MarketSnapshot)).first() is None


def test_a_coin_coingecko_no_longer_returns_gets_no_row(sessions: sessionmaker[Session]) -> None:
    add_tokens(sessions, ("0xtest01", "test-delisted"), ("0xtest02", "test-coin-b"))
    assert run(sessions, FakeMarkets().adapter()) == "ok"
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(MarketSnapshot)) == 1


def test_ac5_rate_limit_pauses_and_missing_key_degrades(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC5: a 429 → Paused with a resume time; a missing key → Degraded with the message."""
    add_tokens(sessions, ("0xtest01", "test-coin-a"))
    fake = FakeMarkets()
    fake.status = 429
    assert run(sessions, fake.adapter()) == "paused"
    with sessions() as s:
        assert get_status(s, "coingecko_markets").paused_until is not None
    monkeypatch.delenv("COINGECKO_API_KEY")
    assert run(sessions, FakeMarkets().adapter(), T0 + timedelta(hours=2)) == "degraded"
    with sessions() as s:
        assert get_status(s, "coingecko_markets").last_error == "COINGECKO_API_KEY is not set"


def test_ac3_every_coingecko_adapter_counts_its_calls(sessions: sessionmaker[Session]) -> None:
    """AC3: calls from all CoinGecko adapters are counted, including failed attempts."""
    add_tokens(sessions, ("0xtest01", "test-coin-a"))

    def ok_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url).split("?")[0]
        if url == LIST_URL:
            return httpx.Response(
                200, json=[{"id": "test-x", "symbol": "x", "name": "X", "platforms": {}}]
            )
        if url == TICKERS_URL:
            return httpx.Response(200, json={"tickers": []})  # no PRL ticker → degraded
        return httpx.Response(200, json=[market("test-coin-a")])

    http = httpx.Client(transport=httpx.MockTransport(ok_handler))
    assert run(sessions, CoinGeckoMarkets(http=http)) == "ok"  # 1 call
    assert run(sessions, CoinGeckoListings(http=http, sleep=lambda _: None)) == "ok"  # 1 call
    assert run(sessions, CoinGecko(http=http)) == "degraded"  # 3 failed attempts = 3 calls
    with sessions() as s:
        total = s.scalar(select(func.sum(CostEntry.calls)).where(CostEntry.source == "coingecko"))
        assert total == 5
        row = s.scalars(select(CostEntry)).first()
        assert row is not None and (row.category, row.amount_usd) == ("data", Decimal(0))


def prl_with_two_sources(sessions: sessionmaker[Session], venue: str, aggregate: str) -> None:
    with sessions.begin() as s:
        token = Token(chain="pearl", contract_address=None, name="Pearl", ticker="PRL")
        s.add(token)
        s.flush()
        for source, price, volume in (
            ("coingecko:safetrade", venue, "4000000"),
            ("coingecko", aggregate, "4500000"),
        ):
            s.add(
                MarketSnapshot(
                    token_id=token.id,
                    source=source,
                    observed_at=T0 - timedelta(minutes=5),
                    available_at=T0 - timedelta(minutes=2),
                    price=Decimal(price),
                    volume_24h=Decimal(volume),
                )
            )


def test_prd33_disagreement_over_5_percent_uses_the_busier_source_and_is_listed(
    sessions: sessionmaker[Session],
) -> None:
    """PRD 3.3: sources >5% apart → use the higher-liquidity (busier) source, log it."""
    prl_with_two_sources(sessions, venue="1.90", aggregate="2.10")
    with sessions() as s:
        token = s.scalars(select(Token)).one()
        choice = preferred_price(s, token.id, T0)
        assert choice is not None and choice.disagrees
        assert (choice.chosen.source, choice.chosen.price) == ("coingecko", Decimal("2.10"))
        [(listed, _)] = disagreements(s, T0)
        assert listed.id == token.id


def test_prd33_within_5_percent_is_not_a_disagreement(sessions: sessionmaker[Session]) -> None:
    prl_with_two_sources(sessions, venue="2.00", aggregate="2.08")
    with sessions() as s:
        assert disagreements(s, T0) == []


def test_prices_only_use_snapshots_available_at_the_time(sessions: sessionmaker[Session]) -> None:
    """Point-in-time rule: a snapshot available after `now` is ignored."""
    prl_with_two_sources(sessions, venue="1.90", aggregate="2.10")
    with sessions() as s:
        assert disagreements(s, T0 - timedelta(minutes=3)) == []


def test_choose_price_with_no_sources_is_none() -> None:
    assert choose_price([]) is None
