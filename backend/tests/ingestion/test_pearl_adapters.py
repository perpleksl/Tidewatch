"""PER-15 and PER-18: Pearl ($PRL) adapters. Responses are shaped like the real ones seen on
18 Oct 2026; the transport is mocked, so no real provider is called."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from tidewatch.db.models import FundamentalSnapshot, MarketSnapshot, Token
from tidewatch.ingestion.coingecko import KEY_HEADER, TICKERS_URL, CoinGecko
from tidewatch.ingestion.pow_pearl import STATS_URL, PowPearl
from tidewatch.ingestion.registry import registered_adapters
from tidewatch.ingestion.runner import get_status, run_adapter, run_due

T0 = datetime(2026, 10, 18, 20, 45, tzinfo=UTC)

TWO_MINERS_STATS = {
    "apiVersion": 200,
    "hashrate": 30526273975746572,
    "minersTotal": 75,
    "workersTotal": 117,
    "now": 1792356230181,
    "nodes": [
        {
            "avgBlockTime": "171.94",
            "blockReward": "224384910421",
            "difficulty": "38259377",
            "height": "129865",
            "name": "prl_pplns",
            "networkhashps": "61299157384157080000",
        }
    ],
}


def cg_ticker(venue: str, usd_last: str, usd_volume: str, **extra: Any) -> dict[str, Any]:
    """A ticker shaped like CoinGecko's /coins/{id}/tickers response (synthetic values)."""
    return {
        "base": "PRL",
        "target": "USDT",
        "market": {"name": venue.title(), "identifier": venue, "has_trading_incentive": False},
        "last": float(usd_last),
        "volume": 1000.0,
        "converted_last": {"btc": 0.00002, "eth": 0.0005, "usd": float(usd_last)},
        "converted_volume": {"btc": 1.0, "eth": 20.0, "usd": float(usd_volume)},
        "timestamp": "2026-10-18T20:40:00+00:00",
        "last_traded_at": "2026-10-18T20:40:00+00:00",
        "last_fetch_at": "2026-10-18T20:41:00+00:00",
        "is_anomaly": False,
        "is_stale": False,
        "target_coin_id": "tether",
        **extra,
    }


CG_TICKERS = {
    "name": "Pearl",
    "tickers": [
        cg_ticker("bigone", "1.95", "400000"),
        cg_ticker("safetrade", "1.92", "4653931.7"),
        cg_ticker("safetrade", "0.00002", "50", target="BTC", target_coin_id="bitcoin"),
    ],
}


@pytest.fixture(autouse=True)
def coingecko_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COINGECKO_API_KEY", "test-key")


def client(routes: dict[str, httpx.Response]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url).split("?")[0]
        return routes.get(url, httpx.Response(404))

    return httpx.Client(transport=httpx.MockTransport(handler))


def ok(body: Any) -> httpx.Response:
    return httpx.Response(200, json=body)


def pearl(session: Session) -> Token:
    return session.scalars(
        select(Token).where(Token.chain == "pearl", Token.contract_address.is_(None))
    ).one()


def test_ac2_pow_pearl_stores_hashrate_miners_and_emissions(
    sessions: sessionmaker[Session],
) -> None:
    """AC2: pow_pearl stores hashrate, miner count and emissions, with source and available_at."""
    adapter = PowPearl(http=client({STATS_URL: ok(TWO_MINERS_STATS)}))
    assert run_adapter(sessions, adapter, lambda: T0, lambda _: None) == "ok"
    with sessions() as s:
        token = pearl(s)
        assert (token.name, token.ticker) == ("Pearl", "PRL")
        [row] = s.scalars(select(FundamentalSnapshot)).all()
        assert row.token_id == token.id
        assert row.source == "2miners"
        assert row.available_at == T0
        assert row.observed_at == datetime.fromtimestamp(1792356230.181, tz=UTC)
        assert row.hashrate == Decimal("61299157384157080000")
        assert row.miners == 75
        # 2243.84910421 PRL per block x (86400 / 171.94) blocks per day x 365.25/12 days.
        per_day = Decimal("2243.84910421") * Decimal(86400) / Decimal("171.94")
        assert row.emissions_per_month == per_day * Decimal("365.25") / Decimal(12)
        assert round(per_day) == 1127536  # ~1.13M PRL per day


def test_per18_ac1_coingecko_stores_safetrade_prl_price_and_volume(
    sessions: sessionmaker[Session],
) -> None:
    """PER-18 AC1: PRL price and volume rows are stored with source and available_at,
    taken from SafeTrade's PRL/USDT ticker even when another venue is listed first."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=CG_TICKERS)

    adapter = CoinGecko(http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert run_adapter(sessions, adapter, lambda: T0, lambda _: None) == "ok"
    assert str(seen[0].url) == TICKERS_URL
    assert seen[0].headers[KEY_HEADER] == "test-key"
    with sessions() as s:
        [row] = s.scalars(select(MarketSnapshot)).all()
        assert row.token_id == pearl(s).id
        assert (row.source, row.price, row.volume_24h) == (
            "coingecko:safetrade",
            Decimal("1.92"),
            Decimal("4653931.7"),
        )
        assert pearl(s).coingecko_id == "pearl-2"  # PER-20: used for market data
        assert row.available_at == T0
        assert row.observed_at == datetime(2026, 10, 18, 20, 40, tzinfo=UTC)


def test_per18_without_safetrade_uses_highest_volume_usdt_venue(
    sessions: sessionmaker[Session],
) -> None:
    """PER-18: if SafeTrade is missing, the highest-volume USDT ticker is used and named."""
    body = {
        "tickers": [
            cg_ticker("coinex", "1.90", "1000"),
            cg_ticker("bigone", "1.95", "400000"),
            cg_ticker("stalex", "9.99", "9000000", is_stale=True),
            cg_ticker("oddex", "9.99", "9000000", is_anomaly=True),
            cg_ticker("safetrade", "0.00002", "9000000", target_coin_id="bitcoin"),
        ]
    }
    adapter = CoinGecko(http=client({TICKERS_URL: ok(body)}))
    assert run_adapter(sessions, adapter, lambda: T0, lambda _: None) == "ok"
    with sessions() as s:
        [row] = s.scalars(select(MarketSnapshot)).all()
        assert (row.source, row.price) == ("coingecko:bigone", Decimal("1.95"))


def test_per18_ac2_without_the_key_the_source_is_degraded_with_a_clear_message(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    """PER-18 AC2: without the key, the source shows Degraded with
    "COINGECKO_API_KEY is not set", and no request is made."""
    monkeypatch.delenv("COINGECKO_API_KEY")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=CG_TICKERS)

    adapter = CoinGecko(http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert run_adapter(sessions, adapter, lambda: T0, lambda _: None) == "degraded"
    assert calls == []
    with sessions() as s:
        status = get_status(s, "coingecko")
        assert (status.status, status.last_error) == ("degraded", "COINGECKO_API_KEY is not set")


def test_per18_ac3_rate_limit_pauses_the_source_with_a_resume_time(
    sessions: sessionmaker[Session],
) -> None:
    """PER-18 AC3: a 429 from CoinGecko marks the source Paused with a resume time."""
    adapter = CoinGecko(
        http=client({TICKERS_URL: httpx.Response(429, headers={"Retry-After": "60"})})
    )
    assert run_adapter(sessions, adapter, lambda: T0, lambda _: None) == "paused"
    with sessions() as s:
        status = get_status(s, "coingecko")
        assert status.status == "paused"
        assert status.paused_until is not None


def test_both_adapters_reuse_one_prl_token(sessions: sessionmaker[Session]) -> None:
    routes = {STATS_URL: ok(TWO_MINERS_STATS), TICKERS_URL: ok(CG_TICKERS)}
    run_due(
        sessions, [PowPearl(client(routes)), CoinGecko(client(routes))], lambda: T0, lambda _: None
    )
    with sessions() as s:
        assert len(s.scalars(select(Token).where(Token.chain == "pearl")).all()) == 1


@pytest.mark.parametrize(
    ("adapter_factory", "url", "response", "expected"),
    [
        (PowPearl, STATS_URL, httpx.Response(503), "degraded"),
        (PowPearl, STATS_URL, ok({"nodes": []}), "degraded"),
        (PowPearl, STATS_URL, ok({**TWO_MINERS_STATS, "minersTotal": -1}), "degraded"),
        (CoinGecko, TICKERS_URL, ok({"tickers": []}), "degraded"),
        (CoinGecko, TICKERS_URL, ok({"error": "x"}), "degraded"),
        (CoinGecko, TICKERS_URL, httpx.Response(401), "degraded"),
    ],
)
def test_ac4_failures_show_on_system_health_with_the_right_status(
    sessions: sessionmaker[Session],
    adapter_factory: Any,
    url: str,
    response: httpx.Response,
    expected: str,
) -> None:
    """AC4: both adapters report their status (OK / Degraded / Paused) like any source."""
    adapter = adapter_factory(http=client({url: response}))
    assert run_adapter(sessions, adapter, lambda: T0, lambda _: None) == expected
    with sessions() as s:
        assert get_status(s, adapter.name).status == expected
        assert s.scalars(select(FundamentalSnapshot)).first() is None
        assert s.scalars(select(MarketSnapshot)).first() is None


def test_ac4_both_adapters_are_registered_in_every_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    names = [a.name for a in registered_adapters()]
    assert names == ["pow_pearl", "coingecko", "coingecko_listings", "coingecko_markets", "goplus"]
