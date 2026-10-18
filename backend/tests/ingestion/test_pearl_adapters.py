"""PER-15: Pearl ($PRL) adapters. Responses are shaped like the real ones seen on
18 Oct 2026; the transport is mocked, so no real provider is called."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from tidewatch.db.models import FundamentalSnapshot, MarketSnapshot, Token
from tidewatch.ingestion.pow_pearl import STATS_URL, PowPearl
from tidewatch.ingestion.registry import registered_adapters
from tidewatch.ingestion.runner import get_status, run_adapter, run_due
from tidewatch.ingestion.safetrade import TICKERS_URL, SafeTrade

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

SAFETRADE_TICKERS = {
    "aquabtc": {"base_unit": "aqua", "quote_unit": "btc", "last": "0.00000008", "volume": "0"},
    "pearlbtc": {"base_unit": "pearl", "quote_unit": "btc", "last": "0.00002", "volume": "1"},
    "pearlusdt": {
        "amount": "2428522.79839999",
        "avg_price": "1.9",
        "base_unit": "pearl",
        "last": "1.92",
        "quote_unit": "usdt",
        "volume": "4653931.70846995",
    },
}


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


def test_ac3_safetrade_stores_prl_price_and_24h_volume(sessions: sessionmaker[Session]) -> None:
    """AC3: the SafeTrade adapter stores PRL price and 24h volume (USDT)."""
    adapter = SafeTrade(http=client({TICKERS_URL: ok(SAFETRADE_TICKERS)}))
    assert run_adapter(sessions, adapter, lambda: T0, lambda _: None) == "ok"
    with sessions() as s:
        [row] = s.scalars(select(MarketSnapshot)).all()
        assert row.token_id == pearl(s).id
        assert (row.source, row.price, row.volume_24h) == (
            "safetrade",
            Decimal("1.92"),
            Decimal("4653931.70846995"),
        )
        assert row.available_at == T0


def test_safetrade_finds_the_market_under_its_old_name_too(
    sessions: sessionmaker[Session],
) -> None:
    old = {"prlusdt": {**SAFETRADE_TICKERS["pearlusdt"], "base_unit": "prl"}}
    adapter = SafeTrade(http=client({TICKERS_URL: ok(old)}))
    assert run_adapter(sessions, adapter, lambda: T0, lambda _: None) == "ok"


def test_both_adapters_reuse_one_prl_token(sessions: sessionmaker[Session]) -> None:
    routes = {STATS_URL: ok(TWO_MINERS_STATS), TICKERS_URL: ok(SAFETRADE_TICKERS)}
    run_due(
        sessions, [PowPearl(client(routes)), SafeTrade(client(routes))], lambda: T0, lambda _: None
    )
    with sessions() as s:
        assert len(s.scalars(select(Token).where(Token.chain == "pearl")).all()) == 1


@pytest.mark.parametrize(
    ("adapter_factory", "url", "response", "expected"),
    [
        (PowPearl, STATS_URL, httpx.Response(503), "degraded"),
        (PowPearl, STATS_URL, ok({"nodes": []}), "degraded"),
        (PowPearl, STATS_URL, ok({**TWO_MINERS_STATS, "minersTotal": -1}), "degraded"),
        (SafeTrade, TICKERS_URL, ok({"aquabtc": SAFETRADE_TICKERS["aquabtc"]}), "degraded"),
        (SafeTrade, TICKERS_URL, httpx.Response(429, headers={"Retry-After": "60"}), "paused"),
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
    assert names == ["pow_pearl", "safetrade"]
