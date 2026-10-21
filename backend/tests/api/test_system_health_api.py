"""PER-13: System Health API (signed in with a test token, against a real database)."""

from collections.abc import Iterator

import pytest
from clerk_backend_api.security.types import VerifyTokenOptions
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import tidewatch.api.auth as auth
from tidewatch.api.deps import get_session
from tidewatch.api.main import app

from .test_auth import PUBLIC_PEM, bearer, make_token


@pytest.fixture
def api(session: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(auth, "verify_options", lambda: VerifyTokenOptions(jwt_key=PUBLIC_PEM))
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.setenv("APP_ENV", "staging")

    def test_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = test_session
    with TestClient(app, headers=bearer(make_token())) as client:
        yield client
    app.dependency_overrides.clear()


def test_system_health_requires_sign_in() -> None:
    with TestClient(app) as client:
        assert client.get("/system-health").status_code == 401
        assert client.post("/system-health/fake_source/run").status_code == 401
        test_mode = client.post("/system-health/fake_source/test-mode", json={"mode": "fail"})
        assert test_mode.status_code == 401


def test_lists_fake_source_with_status_last_success_and_error_count(api: TestClient) -> None:
    body = api.get("/system-health").json()
    assert body["test_controls"] is True
    fake = next(s for s in body["sources"] if s["source"] == "fake_source")
    assert fake["status"] == "ok"
    assert fake["last_success_at"] is None
    assert fake["errors_24h"] == 0


def test_test_mode_and_run_now_are_recorded(api: TestClient) -> None:
    response = api.post("/system-health/fake_source/test-mode", json={"mode": "fail"})
    assert response.json()["test_mode"] == "fail"
    assert api.post("/system-health/fake_source/run").json()["run_requested"] is True
    back = api.post("/system-health/fake_source/test-mode", json={"mode": "normal"})
    assert back.json()["test_mode"] is None


def test_unknown_mode_and_source_are_refused(api: TestClient) -> None:
    assert api.post("/system-health/fake_source/test-mode", json={"mode": "x"}).status_code == 422
    assert api.post("/system-health/nansen/run").status_code == 404


def test_production_has_no_fake_source_and_no_test_controls(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    body = api.get("/system-health").json()
    assert body["test_controls"] is False
    assert all(s["source"] != "fake_source" for s in body["sources"])
    assert (
        api.post("/system-health/fake_source/test-mode", json={"mode": "fail"}).status_code == 404
    )


def test_per18_old_safetrade_source_is_archived_and_coingecko_is_listed(
    api: TestClient, session: Session
) -> None:
    """PER-18: the replaced `safetrade` source is archived (soft delete), `coingecko` shows."""
    from sqlalchemy import select

    from tidewatch.db.models import SourceStatus

    session.add(SourceStatus(source="safetrade", status="degraded", recent_errors=[]))
    session.flush()
    names = [s["source"] for s in api.get("/system-health").json()["sources"]]
    assert "safetrade" not in names
    assert "coingecko" in names
    old = session.scalars(select(SourceStatus).where(SourceStatus.source == "safetrade")).one()
    assert old.archived_at is not None  # kept, not deleted


def test_per19_ac2_new_listings_section_lists_last_7_days(
    api: TestClient, session: Session
) -> None:
    """PER-19 AC2: System Health lists new listings from the last 7 days with name, chain,
    outcome, candidate tab and first-seen time; the starting list is never listed."""
    from datetime import UTC, datetime, timedelta

    from tidewatch.db.models import CoinGeckoListing

    now = datetime.now(UTC)
    session.add_all(
        [
            CoinGeckoListing(
                coingecko_id="test-start",
                name="Start",
                symbol="st",
                first_seen_at=now - timedelta(days=2),
                in_starting_list=True,
                chains=[],
            ),
            CoinGeckoListing(
                coingecko_id="test-new",
                name="Test New",
                symbol="tn",
                first_seen_at=now - timedelta(hours=3),
                outcome="assessed",
                reason="In the covered universe",
                chains=["base"],
                candidate_tab="mispriced",
            ),
            CoinGeckoListing(
                coingecko_id="test-old",
                name="Test Old",
                symbol="to",
                first_seen_at=now - timedelta(days=8),
                outcome="outside_universe",
                chains=[],
            ),
        ]
    )
    session.flush()
    body = api.get("/system-health").json()["new_listings"]
    assert body["starting_list_at"] is not None
    assert [i["coingecko_id"] for i in body["items"]] == ["test-new"]
    item = body["items"][0]
    assert (item["name"], item["chains"], item["outcome"], item["candidate_tab"]) == (
        "Test New",
        ["base"],
        "assessed",
        "mispriced",
    )
    assert item["first_seen_at"]


def test_per19_before_the_first_run_there_is_no_starting_list(api: TestClient) -> None:
    body = api.get("/system-health").json()["new_listings"]
    assert body == {"starting_list_at": None, "items": []}


def test_per20_coingecko_usage_and_market_data_on_system_health(
    api: TestClient, session: Session
) -> None:
    """PER-20 AC3/AC4: System Health shows CoinGecko calls against the allowance, and lists
    tracked tokens without a CoinGecko ID."""
    from datetime import UTC, datetime
    from decimal import Decimal

    from tidewatch.db.models import CostEntry, Token

    session.add(
        CostEntry(
            source="coingecko",
            category="data",
            amount_usd=Decimal(0),
            calls=40,
            at=datetime.now(UTC),
        )
    )
    session.add(
        Token(
            chain="ethereum",
            contract_address="0xtest01",
            name="Has Id",
            ticker="A",
            coingecko_id="test-a",
        )
    )
    session.add(Token(chain="ethereum", contract_address="0xtest02", name="No Id", ticker="B"))
    session.flush()
    body = api.get("/system-health").json()
    usage = body["coingecko_usage"]
    assert usage["calls_this_month"] == 40
    assert usage["allowance"] == 10_000
    assert usage["projected_month_end"] >= 40
    market = body["market_data"]
    assert market["tokens_with_coingecko_id"] == 1
    assert market["tokens_without_coingecko_id"] == 1
    assert market["without_coingecko_id"] == [{"name": "No Id", "ticker": "B", "chain": "ethereum"}]
    assert market["price_disagreements"] == []


def test_per23_contract_security_section(api: TestClient, session: Session) -> None:
    """PER-23 AC2/AC6: System Health lists avoided tokens with reasons, and native coins as
    "Not applicable"."""
    from datetime import UTC, datetime, timedelta

    from tidewatch.db.models import SecurityCheck, Token

    now = datetime.now(UTC)
    bad = Token(chain="ethereum", contract_address="0xtest01", name="Bad", ticker="BAD")
    ok = Token(chain="ethereum", contract_address="0xtest02", name="Ok", ticker="OK")
    prl = Token(chain="pearl", contract_address=None, name="Pearl", ticker="PRL")
    session.add_all([bad, ok, prl])
    session.flush()
    for t, status, stops, when in (
        (bad, "passed", [], now - timedelta(days=1)),
        (bad, "avoid", [{"code": "honeypot", "reason": "Honeypot detected"}], now),
        (ok, "passed", [], now),
    ):
        session.add(
            SecurityCheck(
                token_id=t.id,
                source="goplus",
                observed_at=when,
                available_at=when,
                status=status,
                hard_stops=stops,
            )
        )
    session.flush()
    body = api.get("/system-health").json()["contract_security"]
    assert body["passed"] == 1
    assert [(i["token"]["name"], i["reasons"]) for i in body["avoid"]] == [
        ("Bad", ["Honeypot detected"])
    ]
    assert body["unknown"] == []
    assert body["not_applicable"] == [{"name": "Pearl", "ticker": "PRL", "chain": "pearl"}]
