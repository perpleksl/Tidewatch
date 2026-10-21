"""PER-21: DefiLlama fees, revenue, TVL and token identity. Mocked responses, synthetic data."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from tidewatch.db.models import FundamentalSnapshot, Token
from tidewatch.ingestion.defillama import (
    API_BASE,
    BACKFILL_PER_RUN,
    FEES_URL,
    PROTOCOLS_URL,
    DefiLlama,
    parse_address,
)
from tidewatch.ingestion.runner import get_status, run_adapter

T0 = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
DAY = 86400
TODAY = int(datetime(2026, 10, 21, tzinfo=UTC).timestamp())
ADDR = "0xTEST000000000000000000000000000000000001"


def protocol(slug: str, address: str | None, **extra: Any) -> dict[str, Any]:
    return {
        "name": slug.title(),
        "slug": slug,
        "symbol": "TST",
        "address": address,
        "gecko_id": f"test-{slug}",
        "category": "Dexs",
        "chain": "Ethereum",
        "url": f"https://{slug}.example",
        "twitter": f"{slug}_test",
        "github": [f"{slug}-org"],
        "tvl": 1_000_000,
        "mcap": 20_000_000,
        **extra,
    }


class FakeLlama:
    def __init__(self) -> None:
        self.protocols: list[dict[str, Any]] = [protocol("alpha", ADDR)]
        self.fees: dict[str, float] = {"alpha": 1200.0}
        self.revenue: dict[str, float] = {"alpha": 300.0}
        self.history_fail: set[str] = set()
        self.status = 200
        self.requests: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url).split("?")[0]
        self.requests.append(url)
        if self.status != 200:
            return httpx.Response(self.status, headers={"Retry-After": "60"})
        if url == PROTOCOLS_URL:
            return httpx.Response(200, json=self.protocols)
        if url == FEES_URL:
            source = self.fees if request.url.params["dataType"] == "dailyFees" else self.revenue
            return httpx.Response(
                200,
                json={"protocols": [{"slug": s, "total24h": v} for s, v in source.items()]},
            )
        slug = url.rsplit("/", 1)[-1]
        if slug in self.history_fail:
            return httpx.Response(500)
        if url.startswith(f"{API_BASE}/summary/fees/"):
            base = 100 if request.url.params["dataType"] == "dailyFees" else 25
            chart = [[TODAY - d * DAY, base + d] for d in range(0, 90)]
            return httpx.Response(200, json={"totalDataChart": chart})
        if url.startswith(f"{API_BASE}/protocol/"):
            series = [{"date": TODAY - d * DAY, "totalLiquidityUSD": 5000 + d} for d in range(90)]
            return httpx.Response(200, json={"tvl": series})
        return httpx.Response(404)

    def adapter(self) -> DefiLlama:
        return DefiLlama(
            http=httpx.Client(transport=httpx.MockTransport(self.handler)), sleep=lambda _: None
        )


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch: pytest.MonkeyPatch) -> None:
    import tidewatch.ingestion.defillama as module

    class _Clock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> "datetime":  # type: ignore[override]
            return T0

    monkeypatch.setattr(module, "datetime", _Clock)


def run(sessions: sessionmaker[Session], fake: FakeLlama, at: datetime = T0) -> str:
    return run_adapter(sessions, fake.adapter(), lambda: at, lambda _: None)


def current_rows(s: Session) -> list[FundamentalSnapshot]:
    return list(s.scalars(select(FundamentalSnapshot).where(FundamentalSnapshot.observed_at == T0)))


def test_ac1_tokens_get_daily_fees_revenue_and_tvl(sessions: sessionmaker[Session]) -> None:
    """AC1: tokens of protocols with a token get fees, revenue and TVL rows with source and
    available_at; System Health shows `defillama` OK."""
    assert run(sessions, FakeLlama()) == "ok"
    with sessions() as s:
        [row] = current_rows(s)
        assert (row.source, row.fees, row.revenue, row.tvl) == (
            "defillama",
            Decimal(1200),
            Decimal(300),
            Decimal(1_000_000),
        )
        assert row.available_at == T0
        assert get_status(s, "defillama").status == "ok"


def test_ac2_token_identity_and_details_are_stored(sessions: sessionmaker[Session]) -> None:
    """AC2: identified by chain + contract, with slug, category, gecko_id and official links."""
    assert run(sessions, FakeLlama()) == "ok"
    with sessions() as s:
        token = s.scalars(select(Token)).one()
        assert (token.chain, token.contract_address) == ("ethereum", ADDR.lower())
        assert (token.defillama_slug, token.category, token.coingecko_id) == (
            "alpha",
            "Dexs",
            "test-alpha",
        )
        assert token.links["website"] == "https://alpha.example"
        assert token.links["twitter"] == "https://x.com/alpha_test"
        assert token.links["github"] == ["https://github.com/alpha-org"]
        assert token.links["defillama_slugs"] == ["alpha"]


def test_protocols_sharing_a_token_are_summed(sessions: sessionmaker[Session]) -> None:
    fake = FakeLlama()
    fake.protocols.append(protocol("alpha-v2", ADDR.lower(), tvl=3_000_000, category="Lending"))
    fake.fees["alpha-v2"] = 800.0
    assert run(sessions, fake) == "ok"
    with sessions() as s:
        token = s.scalars(select(Token)).one()
        [row] = current_rows(s)
        assert (row.fees, row.revenue, row.tvl) == (Decimal(2000), Decimal(300), Decimal(4_000_000))
        assert (token.defillama_slug, token.category) == ("alpha-v2", "Lending")  # largest TVL


def test_ac4_protocols_without_a_token_create_nothing(sessions: sessionmaker[Session]) -> None:
    """AC4: protocols without a token (or on chains outside the universe) create no Token."""
    fake = FakeLlama()
    fake.protocols = [
        protocol("no-token", None),
        protocol("dash", "-"),
        protocol("tron-only", "tron:TTESTADDR"),
    ]
    assert run(sessions, fake) == "ok"
    with sessions() as s:
        assert s.scalars(select(Token)).first() is None


@pytest.mark.parametrize(
    ("address", "chain_hint", "expected"),
    [
        ("0xABC", None, ("ethereum", "0xabc")),
        ("arbitrum:0xABC", None, ("arbitrum", "0xabc")),
        ("avax:0xABC", None, ("avalanche", "0xabc")),
        ("era:0xABC", None, ("zksync", "0xabc")),
        ("solana:TestMintAbc", None, ("solana", "TestMintAbc")),
        ("TestMintAbc", "Solana", ("solana", "TestMintAbc")),
        ("cosmos:abc", None, None),
        ("", None, None),
    ],
)
def test_address_parsing(address: str, chain_hint: str | None, expected: Any) -> None:
    assert parse_address(address, chain_hint) == expected


def test_ac3_backfill_stores_60_days_with_fetch_time_as_available_at(
    sessions: sessionmaker[Session],
) -> None:
    """AC3: up to 60 days of history per token; backfilled rows carry the fetch time as
    available_at, so no row claims to have been available earlier."""
    assert run(sessions, FakeLlama()) == "ok"
    with sessions() as s:
        history = list(
            s.scalars(select(FundamentalSnapshot).where(FundamentalSnapshot.observed_at < T0))
        )
        assert len(history) == 60
        assert all(r.available_at == T0 for r in history)
        assert min(r.observed_at for r in history) == datetime(2026, 8, 22, tzinfo=UTC)
        assert max(r.observed_at for r in history) == datetime(2026, 10, 20, tzinfo=UTC)
        yesterday = next(r for r in history if r.observed_at == datetime(2026, 10, 20, tzinfo=UTC))
        assert (yesterday.fees, yesterday.revenue, yesterday.tvl) == (
            Decimal(101),
            Decimal(26),
            Decimal(5001),
        )
        assert s.scalars(select(Token)).one().defillama_backfilled_at == T0


def test_backfill_happens_once(sessions: sessionmaker[Session]) -> None:
    fake = FakeLlama()
    assert run(sessions, fake) == "ok"
    fake.requests.clear()
    assert run(sessions, fake, T0 + timedelta(hours=1)) == "ok"
    assert not any("/summary/" in u or "/protocol/" in u for u in fake.requests)


def test_backfill_is_capped_per_run_and_in_range_tokens_go_first(
    sessions: sessionmaker[Session],
) -> None:
    fake = FakeLlama()
    fake.protocols = [
        protocol(f"p{i:03d}", f"0xtest{i:037d}", mcap=900_000_000) for i in range(BACKFILL_PER_RUN)
    ]
    fake.protocols.append(protocol("inrange", "0xtest" + "9" * 37, mcap=20_000_000, tvl=1))
    assert run(sessions, fake) == "ok"
    with sessions() as s:
        done = s.scalars(select(Token).where(Token.defillama_backfilled_at.is_not(None))).all()
        assert len(done) == BACKFILL_PER_RUN
        assert any(t.defillama_slug == "inrange" for t in done)


def test_a_failed_backfill_is_retried_and_doesnt_stop_the_run(
    sessions: sessionmaker[Session],
) -> None:
    fake = FakeLlama()
    fake.history_fail.add("alpha")
    assert run(sessions, fake) == "ok"
    with sessions() as s:
        assert s.scalars(select(Token)).one().defillama_backfilled_at is None
        assert len(current_rows(s)) == 1


def test_unchanged_figures_are_not_written_again_within_a_day(
    sessions: sessionmaker[Session],
) -> None:
    fake = FakeLlama()
    assert run(sessions, fake) == "ok"
    assert run(sessions, fake, T0 + timedelta(hours=1)) == "ok"
    fake.fees["alpha"] = 1500.0  # moved by 25%
    assert run(sessions, fake, T0 + timedelta(hours=2)) == "ok"
    with sessions() as s:
        count = s.scalar(
            select(func.count())
            .select_from(FundamentalSnapshot)
            .where(FundamentalSnapshot.observed_at == T0)
        )
        assert count == 2


def test_ac5_failures_follow_the_framework(sessions: sessionmaker[Session]) -> None:
    """AC5: a failing source → Degraded; a 429 → Paused."""
    fake = FakeLlama()
    fake.status = 500
    assert run(sessions, fake) == "degraded"
    fake.status = 429
    assert run(sessions, fake, T0 + timedelta(hours=2)) == "paused"
