"""PER-23: GoPlus adapter: who gets checked, how often, and how failures show. Synthetic data."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from tidewatch.db.models import MarketSnapshot, SecurityCheck, Token
from tidewatch.db.settings import update_setting
from tidewatch.ingestion.goplus import API_BASE, CHECKS_PER_RUN, GoPlus, eligible_tokens
from tidewatch.ingestion.runner import get_status, run_adapter

T0 = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
CLEAN = {
    "is_open_source": "1",
    "is_honeypot": "0",
    "is_mintable": "0",
    "owner_address": "",
    "owner_change_balance": "0",
    "holders": [{"address": "0xtestwhale", "tag": "", "is_locked": "0", "percent": "0.2"}],
    "dex": [{"pair": "0xtestpair", "liquidity": "500000", "name": "UniswapV2"}],
}


class FakeGoPlus:
    def __init__(self) -> None:
        self.answers: dict[str, Any] = {}
        self.code = 1
        self.fail: set[str] = set()
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        address = request.url.params["contract_addresses"]
        if address in self.fail:
            return httpx.Response(503)
        if self.code != 1:
            return httpx.Response(200, json={"code": self.code, "message": "limit", "result": {}})
        result = (
            {address.lower(): self.answers.get(address, CLEAN)}
            if address not in ("0xtestnodata",)
            else {}
        )
        return httpx.Response(200, json={"code": 1, "message": "OK", "result": result})

    def adapter(self) -> GoPlus:
        http = httpx.Client(transport=httpx.MockTransport(self.handler))
        return GoPlus(http=http, sleep=lambda _: None)


def token(
    sessions: sessionmaker[Session],
    contract: str | None,
    market_cap: str | None = "50000000",
    chain: str = "ethereum",
) -> Token:
    with sessions.begin() as s:
        t = Token(chain=chain, contract_address=contract, name=f"T {contract}", ticker="TST")
        s.add(t)
        s.flush()
        if market_cap is not None:
            s.add(
                MarketSnapshot(
                    token_id=t.id,
                    source="coingecko",
                    observed_at=T0 - timedelta(hours=1),
                    available_at=T0 - timedelta(hours=1),
                    price=Decimal(1),
                    market_cap=Decimal(market_cap),
                )
            )
        s.expunge(t)
        return t


def run(sessions: sessionmaker[Session], fake: FakeGoPlus, at: datetime = T0) -> str:
    return run_adapter(sessions, fake.adapter(), lambda: at, lambda _: None)


def checks(sessions: sessionmaker[Session]) -> list[SecurityCheck]:
    with sessions() as s:
        rows = list(s.scalars(select(SecurityCheck).order_by(SecurityCheck.available_at)))
        for r in rows:
            s.expunge(r)
        return rows


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch: pytest.MonkeyPatch) -> None:
    import tidewatch.ingestion.goplus as goplus

    class _Clock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> "datetime":  # type: ignore[override]
            return _NOW[0]

    monkeypatch.setattr(goplus, "datetime", _Clock)


_NOW = [T0]


def at(moment: datetime) -> None:
    _NOW[0] = moment


@pytest.fixture(autouse=True)
def reset_clock() -> None:
    at(T0)


def test_ac1_in_range_contract_token_gets_a_time_stamped_check(
    sessions: sessionmaker[Session],
) -> None:
    """AC1: tracked contract tokens in range get a time-stamped security check; source OK."""
    t = token(sessions, "0xtest01")
    fake = FakeGoPlus()
    assert run(sessions, fake) == "ok"
    [row] = checks(sessions)
    assert (row.token_id, row.status, row.source, row.available_at) == (
        t.id,
        "passed",
        "goplus",
        T0,
    )
    assert str(fake.requests[0].url).startswith(f"{API_BASE}/token_security/1?")
    with sessions() as s:
        assert get_status(s, "goplus").status == "ok"


def test_ac4_holder_share_and_liquidity_are_stored(sessions: sessionmaker[Session]) -> None:
    """AC4: top-10 share and DEX liquidity are stored per check."""
    token(sessions, "0xtest01")
    assert run(sessions, FakeGoPlus()) == "ok"
    [row] = checks(sessions)
    assert (row.top10_holder_share, row.dex_liquidity_usd) == (Decimal("0.2"), Decimal(500000))
    assert row.raw["is_honeypot"] == "0"


def test_ac2_hard_stop_is_recorded_as_avoid_with_its_reason(
    sessions: sessionmaker[Session],
) -> None:
    """AC2: a hard stop from GoPlus → status "avoid" with the reason."""
    token(sessions, "0xtest01")
    fake = FakeGoPlus()
    fake.answers["0xtest01"] = {**CLEAN, "is_honeypot": "1"}
    assert run(sessions, fake) == "ok"
    [row] = checks(sessions)
    assert row.status == "avoid"
    assert row.hard_stops[0]["code"] == "honeypot"


def test_only_tokens_in_mispriced_market_cap_range_are_checked(
    sessions: sessionmaker[Session],
) -> None:
    """Owner decision 21 Oct 2026: only tokens in Mispriced's market-cap range."""
    token(sessions, "0xtestsmall", market_cap="500000")
    token(sessions, "0xtestbig", market_cap="900000000")
    token(sessions, "0xtestnocap", market_cap=None)
    inside = token(sessions, "0xtestinside")
    assert run(sessions, FakeGoPlus()) == "ok"
    assert [r.token_id for r in checks(sessions)] == [inside.id]


def test_the_range_comes_from_settings(sessions: sessionmaker[Session]) -> None:
    small = token(sessions, "0xtestsmall", market_cap="500000")
    with sessions.begin() as s:
        update_setting(s, "mispriced.market_cap_min_usd", "100000")
    assert run(sessions, FakeGoPlus()) == "ok"
    assert [r.token_id for r in checks(sessions)] == [small.id]


def test_rechecked_once_a_day_not_sooner(sessions: sessionmaker[Session]) -> None:
    """Owner decision 21 Oct 2026: re-check once a day."""
    token(sessions, "0xtest01")
    fake = FakeGoPlus()
    assert run(sessions, fake) == "ok"
    at(T0 + timedelta(hours=23))
    assert run(sessions, fake, T0 + timedelta(hours=23)) == "ok"
    assert len(checks(sessions)) == 1
    at(T0 + timedelta(hours=24))
    assert run(sessions, fake, T0 + timedelta(hours=24)) == "ok"
    assert len(checks(sessions)) == 2


def test_ac6_native_coins_are_never_checked(sessions: sessionmaker[Session]) -> None:
    """AC6: native coins (e.g. PRL) aren't checked; contract security is Not applicable."""
    token(sessions, None, chain="pearl")
    fake = FakeGoPlus()
    assert run(sessions, fake) == "ok"
    assert fake.requests == [] and checks(sessions) == []


def test_solana_uses_the_solana_endpoint(sessions: sessionmaker[Session]) -> None:
    token(sessions, "TestMint111", chain="solana")
    fake = FakeGoPlus()
    fake.answers["TestMint111"] = {
        "mintable": {"status": "0", "authority": []},
        "freezable": {"status": "0", "authority": []},
    }
    assert run(sessions, fake) == "ok"
    assert str(fake.requests[0].url).startswith(f"{API_BASE}/solana/token_security?")
    assert checks(sessions)[0].status == "passed"


def test_ac5_a_failed_check_is_unknown_and_others_continue(sessions: sessionmaker[Session]) -> None:
    """AC5: if a check fails, that token's contract security is "Unknown"."""
    token(sessions, "0xtestbad")
    token(sessions, "0xtestgood")
    fake = FakeGoPlus()
    fake.fail.add("0xtestbad")
    assert run(sessions, fake) == "ok"
    by_status = sorted(r.status for r in checks(sessions))
    assert by_status == ["passed", "unknown"]


def test_ac5_every_check_failing_degrades_the_source(sessions: sessionmaker[Session]) -> None:
    token(sessions, "0xtestbad")
    fake = FakeGoPlus()
    fake.fail.add("0xtestbad")
    assert run(sessions, fake) == "degraded"


def test_no_data_for_a_contract_is_unknown(sessions: sessionmaker[Session]) -> None:
    token(sessions, "0xtestnodata")
    assert run(sessions, FakeGoPlus()) == "ok"
    assert checks(sessions)[0].reason == "GoPlus has no data for this contract"


def test_goplus_limit_code_pauses_the_source(sessions: sessionmaker[Session]) -> None:
    token(sessions, "0xtest01")
    fake = FakeGoPlus()
    fake.code = 4029
    assert run(sessions, fake) == "paused"


def test_checks_per_run_are_capped_and_never_checked_go_first(
    sessions: sessionmaker[Session],
) -> None:
    for i in range(CHECKS_PER_RUN + 5):
        token(sessions, f"0xtest{i:04d}")
    with sessions() as s:
        assert len(eligible_tokens(s, T0)) == CHECKS_PER_RUN + 5
    assert run(sessions, FakeGoPlus()) == "ok"
    assert len(checks(sessions)) == CHECKS_PER_RUN
    at(T0 + timedelta(hours=1))
    with sessions() as s:
        assert len(eligible_tokens(s, T0 + timedelta(hours=1))) == 5
