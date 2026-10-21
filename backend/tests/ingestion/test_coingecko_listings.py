"""PER-19: CoinGecko new-listing discovery (PRD 3.2). Mocked responses, synthetic coin IDs."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from tidewatch.db.models import CoinGeckoListing, Token
from tidewatch.db.settings import update_setting
from tidewatch.ingestion.coingecko import API_BASE, KEY_HEADER
from tidewatch.ingestion.coingecko_listings import (
    LIST_URL,
    NATIVE_CHECKS_PER_RUN,
    OUTSIDE,
    CoinGeckoListings,
)
from tidewatch.ingestion.runner import get_status, run_adapter

T0 = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)
T1 = T0 + timedelta(days=1)
EVM = "0xTEST000000000000000000000000000000000001"

STARTING = [
    {"id": "test-old-coin", "symbol": "old", "name": "Test Old Coin", "platforms": {}},
    {
        "id": "test-old-token",
        "symbol": "otk",
        "name": "Test Old Token",
        "platforms": {"ethereum": "0xTEST00000000000000000000000000000000000f"},
    },
]


def coin(coin_id: str, platforms: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "id": coin_id,
        "symbol": coin_id[-3:],
        "name": coin_id.title(),
        "platforms": platforms or {},
    }


class FakeCoinGecko:
    """Serves the coin list plus per-coin tickers and details; records every request."""

    def __init__(self) -> None:
        self.coins: list[dict[str, Any]] = list(STARTING)
        self.safetrade: set[str] = set()
        self.pow: set[str] = set()
        self.genesis: dict[str, str] = {}
        self.fail: set[str] = set()
        self.list_status = 200
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = str(request.url).split("?")[0]
        if path == LIST_URL:
            if self.list_status != 200:
                return httpx.Response(self.list_status, headers={"Retry-After": "120"})
            return httpx.Response(200, json=self.coins)
        coin_id = path.removeprefix(f"{API_BASE}/coins/").split("/")[0]
        if coin_id in self.fail:
            return httpx.Response(500)
        if path.endswith("/tickers"):
            listed = coin_id in self.safetrade
            tickers = [{"market": {"identifier": "safetrade"}}] if listed else []
            return httpx.Response(200, json={"name": coin_id, "tickers": tickers})
        categories = (
            ["Proof of Work (PoW)", "Layer 1 (L1)"] if coin_id in self.pow else ["Layer 1 (L1)"]
        )
        return httpx.Response(
            200,
            json={
                "id": coin_id,
                "categories": categories,
                "genesis_date": self.genesis.get(coin_id),
            },
        )

    def adapter(self) -> CoinGeckoListings:
        http = httpx.Client(transport=httpx.MockTransport(self.handler))
        return CoinGeckoListings(http=http, sleep=lambda _: None)


@pytest.fixture(autouse=True)
def coingecko_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COINGECKO_API_KEY", "test-key")


@pytest.fixture
def cg() -> FakeCoinGecko:
    return FakeCoinGecko()


def run(sessions: sessionmaker[Session], cg: FakeCoinGecko, at: datetime) -> str:
    return run_adapter(sessions, cg.adapter(), lambda: at, lambda _: None)


def listing(s: Session, coin_id: str) -> CoinGeckoListing:
    return s.scalars(select(CoinGeckoListing).where(CoinGeckoListing.coingecko_id == coin_id)).one()


def started(sessions: sessionmaker[Session], cg: FakeCoinGecko) -> None:
    assert run(sessions, cg, T0) == "ok"


def test_ac1_first_run_records_the_starting_list_and_flags_nothing(
    sessions: sessionmaker[Session], cg: FakeCoinGecko
) -> None:
    """AC1: the first run records the starting list and flags nothing as new; source OK."""
    started(sessions, cg)
    with sessions() as s:
        rows = s.scalars(select(CoinGeckoListing)).all()
        assert {r.coingecko_id for r in rows} == {"test-old-coin", "test-old-token"}
        assert all(r.in_starting_list and r.outcome is None for r in rows)
        assert s.scalars(select(Token)).first() is None
        assert get_status(s, "coingecko_listings").status == "ok"
    # One list call, with the Demo key, and no per-coin calls.
    assert len(cg.requests) == 1
    assert cg.requests[0].headers[KEY_HEADER] == "test-key"
    assert cg.requests[0].url.params["include_platform"] == "true"


def test_ac2_a_coin_not_in_the_previous_list_is_a_new_listing(
    sessions: sessionmaker[Session], cg: FakeCoinGecko
) -> None:
    """AC2: on the next run, a coin not in the previous list is recorded as a new listing."""
    started(sessions, cg)
    cg.coins.append(coin("test-new-token", {"base": EVM}))
    assert run(sessions, cg, T1) == "ok"
    with sessions() as s:
        row = listing(s, "test-new-token")
        assert not row.in_starting_list
        assert row.first_seen_at == T1
        assert (row.outcome, row.chains, row.candidate_tab) == ("assessed", ["base"], "mispriced")
        assert listing(s, "test-old-coin").outcome is None  # starting list untouched


def test_ac3_contract_listing_creates_a_token_by_chain_and_contract_never_by_ticker(
    sessions: sessionmaker[Session], cg: FakeCoinGecko
) -> None:
    """AC3: a contract on a covered chain creates a Token by chain + contract address; an
    existing token is reused, and a same-ticker token on another contract stays separate."""
    started(sessions, cg)
    with sessions.begin() as s:
        s.add(Token(chain="ethereum", contract_address=EVM.lower(), name="Existing", ticker="DUP"))
        s.add(Token(chain="ethereum", contract_address="0xtestother", name="Other", ticker="NEW"))
    cg.coins.append(
        {
            "id": "test-multi",
            "symbol": "new",
            "name": "Test Multi",
            "platforms": {"ethereum": EVM, "solana": "TestSoLMint111", "tron": "TTEST"},
        }
    )
    assert run(sessions, cg, T1) == "ok"
    with sessions() as s:
        row = listing(s, "test-multi")
        assert row.chains == ["ethereum", "solana"]  # tron is outside the universe
        eth = s.scalars(
            select(Token).where(Token.chain == "ethereum", Token.contract_address == EVM.lower())
        ).one()
        assert eth.name == "Existing"  # reused, not duplicated
        assert eth.coingecko_id == "test-multi"  # PER-20: market data can find it
        sol = s.scalars(select(Token).where(Token.chain == "solana")).one()
        assert sol.contract_address == "TestSoLMint111"  # Solana keeps its case
        assert (
            len(s.scalars(select(Token).where(Token.ticker == "NEW")).all()) == 2
        )  # ticker ignored


def test_ac4_native_pow_coin_on_safetrade_is_assessed(
    sessions: sessionmaker[Session], cg: FakeCoinGecko
) -> None:
    """AC4: a native PoW coin listed on SafeTrade is assessed and gets a native Token."""
    started(sessions, cg)
    cg.coins.append(coin("test-powcoin"))
    cg.safetrade.add("test-powcoin")
    cg.pow.add("test-powcoin")
    assert run(sessions, cg, T1) == "ok"
    with sessions() as s:
        row = listing(s, "test-powcoin")
        assert row.outcome == "assessed"
        token = s.scalars(select(Token).where(Token.chain == "test-powcoin")).one()
        assert token.contract_address is None and row.token_id == token.id
    tickers = [r for r in cg.requests if r.url.path.endswith("/tickers")]
    assert tickers[0].url.params["exchange_ids"] == "safetrade"


@pytest.mark.parametrize(("on_safetrade", "is_pow"), [(False, True), (True, False), (False, False)])
def test_ac4_native_coin_not_on_safetrade_or_not_pow_is_outside_the_universe(
    sessions: sessionmaker[Session], cg: FakeCoinGecko, on_safetrade: bool, is_pow: bool
) -> None:
    """AC4: a native coin not on SafeTrade, or not PoW, shows "Outside the covered universe"
    and no Token is created."""
    started(sessions, cg)
    cg.coins.append(coin("test-l1"))
    if on_safetrade:
        cg.safetrade.add("test-l1")
    if is_pow:
        cg.pow.add("test-l1")
    assert run(sessions, cg, T1) == "ok"
    with sessions() as s:
        row = listing(s, "test-l1")
        assert (row.outcome, row.reason, row.token_id) == ("outside_universe", OUTSIDE, None)
        assert s.scalars(select(Token)).first() is None


def test_contract_token_on_uncovered_chains_only_is_outside_the_universe(
    sessions: sessionmaker[Session], cg: FakeCoinGecko
) -> None:
    started(sessions, cg)
    cg.coins.append(coin("test-tron-only", {"tron": "TTEST"}))
    assert run(sessions, cg, T1) == "ok"
    with sessions() as s:
        assert listing(s, "test-tron-only").reason == OUTSIDE


@pytest.mark.parametrize(
    ("genesis", "expected"),
    [
        ("2026-10-18", "launches"),  # 30 hours before T1
        ("2026-10-15", "mispriced"),  # 4.25 days before T1
        (None, "mispriced"),  # unknown launch time counts as older
    ],
)
def test_ac5_candidate_tab_follows_the_launches_window(
    sessions: sessionmaker[Session], cg: FakeCoinGecko, genesis: str | None, expected: str
) -> None:
    """AC5: launched less than 72 hours ago → launches; older or unknown → mispriced."""
    started(sessions, cg)
    cg.coins.append(coin("test-fresh"))
    cg.safetrade.add("test-fresh")
    cg.pow.add("test-fresh")
    if genesis:
        cg.genesis["test-fresh"] = genesis
    assert run(sessions, cg, T1) == "ok"
    with sessions() as s:
        assert listing(s, "test-fresh").candidate_tab == expected


def test_ac5_the_window_comes_from_the_launches_setting(
    sessions: sessionmaker[Session], cg: FakeCoinGecko
) -> None:
    """AC5: the 72 hours is the Launches window setting, not a hardcoded value."""
    started(sessions, cg)
    with sessions.begin() as s:
        update_setting(s, "launches.max_age_hours", "24")
    cg.coins.append(coin("test-fresh"))
    cg.safetrade.add("test-fresh")
    cg.pow.add("test-fresh")
    cg.genesis["test-fresh"] = "2026-10-18"  # 30 hours before T1: over a 24-hour window
    assert run(sessions, cg, T1) == "ok"
    with sessions() as s:
        assert listing(s, "test-fresh").candidate_tab == "mispriced"


def test_native_checks_are_capped_per_run_and_the_rest_retried_next_run(
    sessions: sessionmaker[Session], cg: FakeCoinGecko
) -> None:
    started(sessions, cg)
    ids = [f"test-native-{i:02d}" for i in range(NATIVE_CHECKS_PER_RUN + 2)]
    cg.coins.extend(coin(i) for i in ids)
    assert run(sessions, cg, T1) == "ok"
    with sessions() as s:
        outcomes = [listing(s, i).outcome for i in ids]
        assert outcomes.count("outside_universe") == NATIVE_CHECKS_PER_RUN
        assert outcomes.count("unresolved") == 2
    assert run(sessions, cg, T1 + timedelta(days=1)) == "ok"
    with sessions() as s:
        assert {listing(s, i).outcome for i in ids} == {"outside_universe"}
        # Retried rows keep the day they were first seen.
        assert listing(s, ids[-1]).first_seen_at == T1


def test_a_failed_native_check_is_unresolved_and_retried(
    sessions: sessionmaker[Session], cg: FakeCoinGecko
) -> None:
    started(sessions, cg)
    cg.coins.append(coin("test-flaky"))
    cg.fail.add("test-flaky")
    assert run(sessions, cg, T1) == "ok"
    with sessions() as s:
        row = listing(s, "test-flaky")
        assert row.outcome == "unresolved" and "retried next run" in (row.reason or "")


def test_ac6_rate_limit_pauses_the_source(
    sessions: sessionmaker[Session], cg: FakeCoinGecko
) -> None:
    """AC6: a 429 marks the source Paused with a resume time."""
    cg.list_status = 429
    assert run(sessions, cg, T0) == "paused"
    with sessions() as s:
        status = get_status(s, "coingecko_listings")
        assert status.status == "paused" and status.paused_until is not None
        assert s.scalars(select(CoinGeckoListing)).first() is None


def test_ac6_missing_key_is_degraded_with_the_message(
    sessions: sessionmaker[Session], cg: FakeCoinGecko, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC6: a missing key shows Degraded with "COINGECKO_API_KEY is not set"."""
    monkeypatch.delenv("COINGECKO_API_KEY")
    assert run(sessions, cg, T0) == "degraded"
    assert cg.requests == []
    with sessions() as s:
        assert get_status(s, "coingecko_listings").last_error == "COINGECKO_API_KEY is not set"


def test_runs_once_a_day_by_default(sessions: sessionmaker[Session], cg: FakeCoinGecko) -> None:
    """PRD 3.2: discovery runs once a day (refresh.discovery_minutes = 1440)."""
    from tidewatch.ingestion.runner import is_due

    adapter: Callable[[], CoinGeckoListings] = cg.adapter
    started(sessions, cg)
    with sessions() as s:
        assert not is_due(s, adapter(), T0 + timedelta(hours=23))
        assert is_due(s, adapter(), T0 + timedelta(hours=24))
