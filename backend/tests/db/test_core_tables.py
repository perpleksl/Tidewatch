"""PER-9: database foundation. Each test names the acceptance criterion it proves."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import Engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.conftest import alembic_config, reset_schema
from tidewatch.db.models import (
    CostEntry,
    FundamentalSnapshot,
    MarketSnapshot,
    Setting,
    SettingChange,
    Token,
    TokenAlias,
)
from tidewatch.db.session import normalise_url

EXPECTED_TABLES = {
    "token",
    "token_alias",
    "market_snapshot",
    "fundamental_snapshot",
    "cost_entry",
    "setting",
    "setting_change",
}
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


def make_token(db: Session, **overrides: Any) -> Token:
    fields: dict[str, Any] = {
        "chain": "ethereum",
        "contract_address": "0xTEST0000000000000000000000000000000000001",
        "name": "Test Token",
        "ticker": "TEST",
    }
    fields.update(overrides)
    token = Token(**fields)
    db.add(token)
    db.flush()
    return token


# --- AC1 -------------------------------------------------------------------------------


def test_ac1_migration_on_empty_database_creates_exactly_the_scoped_tables(
    migrated: Engine,
) -> None:
    """AC1: Running the migration on an empty database creates exactly the tables in Scope."""
    with migrated.connect() as conn:
        reset_schema(conn)
        command.upgrade(alembic_config(conn), "head")
        conn.commit()
        tables = set(inspect(conn).get_table_names()) - {"alembic_version"}
    assert tables == EXPECTED_TABLES


def test_ac1_migration_can_be_rolled_back_and_reapplied(migrated: Engine) -> None:
    """AC1 (supporting): the migration downgrades cleanly to empty and upgrades again."""
    with migrated.connect() as conn:
        config = alembic_config(conn)
        command.downgrade(config, "base")
        conn.commit()
        assert set(inspect(conn).get_table_names()) - {"alembic_version"} == set()
        command.upgrade(config, "head")
        conn.commit()
        assert set(inspect(conn).get_table_names()) - {"alembic_version"} == EXPECTED_TABLES


# --- AC2 -------------------------------------------------------------------------------


def test_ac2_same_chain_and_contract_twice_fails(session: Session) -> None:
    """AC2: Inserting two Token rows with the same chain and contract address fails."""
    make_token(session)
    with pytest.raises(IntegrityError):
        make_token(session, name="Copy", ticker="COPY")


def test_ac2_same_native_chain_twice_fails(session: Session) -> None:
    """AC2 (native coins): only one native coin per chain."""
    make_token(session, chain="testchain-pow", contract_address=None)
    with pytest.raises(IntegrityError):
        make_token(session, chain="testchain-pow", contract_address=None)


def test_ac2_native_coins_on_different_chains_succeed(session: Session) -> None:
    """AC2: Two native coins on different chains succeed."""
    make_token(session, chain="testchain-a", contract_address=None, ticker="NATA")
    make_token(session, chain="testchain-b", contract_address=None, ticker="NATB")
    count = len(session.scalars(select(Token).where(Token.contract_address.is_(None))).all())
    assert count == 2


def test_ac2_same_contract_on_different_chains_succeeds(session: Session) -> None:
    """AC2 (supporting): identity is chain + contract, so another chain is another token."""
    make_token(session, chain="ethereum")
    make_token(session, chain="base")


# --- AC3 -------------------------------------------------------------------------------


def test_ac3_same_ticker_on_different_contracts_succeeds(session: Session) -> None:
    """AC3: Two tokens with the same ticker on different contracts succeed."""
    make_token(session, contract_address="0xTEST000000000000000000000000000000000000A")
    make_token(session, contract_address="0xTEST000000000000000000000000000000000000B")
    tickers = session.scalars(select(Token.ticker)).all()
    assert tickers == ["TEST", "TEST"]


def test_ac3_shared_ticker_can_be_recorded_as_alias(session: Session) -> None:
    """AC3 (supporting): a shared ticker is a relationship between two tokens."""
    a = make_token(session, contract_address="0xTEST000000000000000000000000000000000000A")
    b = make_token(session, contract_address="0xTEST000000000000000000000000000000000000B")
    session.add(TokenAlias(token_id=a.id, alias_token_id=b.id, relation="shared_ticker"))
    session.flush()


def test_alias_rejects_unknown_relation(session: Session) -> None:
    a = make_token(session, contract_address="0xTEST000000000000000000000000000000000000A")
    b = make_token(session, contract_address="0xTEST000000000000000000000000000000000000B")
    session.add(TokenAlias(token_id=a.id, alias_token_id=b.id, relation="cousin"))
    with pytest.raises(IntegrityError):
        session.flush()


# --- AC4 -------------------------------------------------------------------------------

SNAPSHOT_MODELS = [MarketSnapshot, FundamentalSnapshot]


@pytest.mark.parametrize("model", SNAPSHOT_MODELS, ids=lambda m: m.__tablename__)
@pytest.mark.parametrize("missing", ["source", "available_at"])
def test_ac4_snapshot_rejects_missing_source_or_available_at(
    session: Session, model: type[MarketSnapshot | FundamentalSnapshot], missing: str
) -> None:
    """AC4: Every snapshot table rejects a row with a missing source or available_at."""
    token = make_token(session)
    fields: dict[str, Any] = {
        "token_id": token.id,
        "source": "test-source",
        "observed_at": NOW,
        "available_at": NOW,
    }
    fields[missing] = None
    session.add(model(**fields))
    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.parametrize("model", SNAPSHOT_MODELS, ids=lambda m: m.__tablename__)
def test_ac4_snapshot_rejects_empty_source(
    session: Session, model: type[MarketSnapshot | FundamentalSnapshot]
) -> None:
    """AC4 (supporting): an empty source name counts as missing."""
    token = make_token(session)
    session.add(model(token_id=token.id, source="", observed_at=NOW, available_at=NOW))
    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.parametrize("model", SNAPSHOT_MODELS, ids=lambda m: m.__tablename__)
def test_ac4_complete_snapshot_is_accepted(
    session: Session, model: type[MarketSnapshot | FundamentalSnapshot]
) -> None:
    token = make_token(session)
    session.add(model(token_id=token.id, source="test-source", observed_at=NOW, available_at=NOW))
    session.flush()


# --- AC5 -------------------------------------------------------------------------------

TINY_PRICE = Decimal("0.000002202006771721795")


def test_ac5_decimal_price_round_trips_without_loss(session: Session) -> None:
    """AC5: Prices are exact decimals; 0.000002202006771721795 round-trips without loss."""
    token = make_token(session)
    snap = MarketSnapshot(
        token_id=token.id,
        price=TINY_PRICE,
        market_cap=Decimal("123456789012345678901234.5"),
        source="test-source",
        observed_at=NOW,
        available_at=NOW,
    )
    session.add(snap)
    session.flush()
    session.expire_all()
    stored = session.get(MarketSnapshot, snap.id)
    assert stored is not None
    assert isinstance(stored.price, Decimal)
    assert stored.price == TINY_PRICE
    assert str(stored.price) == "0.000002202006771721795"
    assert stored.market_cap == Decimal("123456789012345678901234.5")


def test_ac5_cost_amount_round_trips_without_loss(session: Session) -> None:
    """AC5: amounts (costs) are exact decimals too."""
    entry = CostEntry(
        source="test-ai",
        category="ai",
        amount_usd=Decimal("0.000002202006771721795"),
        model="test-model",
        input_tokens=1200,
        output_tokens=300,
        at=NOW,
    )
    session.add(entry)
    session.flush()
    session.expire_all()
    stored = session.get(CostEntry, entry.id)
    assert stored is not None
    assert stored.amount_usd == TINY_PRICE


# --- AC6 -------------------------------------------------------------------------------


def test_ac6_copenhagen_time_is_stored_and_read_back_as_utc(session: Session) -> None:
    """AC6: Times are stored in UTC; a Copenhagen-time value reads back as its UTC equivalent."""
    copenhagen = datetime(2026, 10, 18, 10, 0, tzinfo=ZoneInfo("Europe/Copenhagen"))
    token = make_token(session)
    snap = MarketSnapshot(
        token_id=token.id, source="test-source", observed_at=copenhagen, available_at=copenhagen
    )
    session.add(snap)
    session.flush()
    session.expire_all()
    stored = session.get(MarketSnapshot, snap.id)
    assert stored is not None
    assert stored.available_at.utcoffset() == timedelta(0)
    assert stored.available_at == datetime(2026, 10, 18, 8, 0, tzinfo=UTC)


# --- Soft delete, settings ---------------------------------------------------------------


def test_every_table_has_archived_at_for_soft_delete(migrated: Engine) -> None:
    """Scope: soft-delete (archived_at) on all tables; nothing is hard-deleted."""
    with migrated.connect() as conn:
        inspector = inspect(conn)
        for table in EXPECTED_TABLES:
            columns = {c["name"] for c in inspector.get_columns(table)}
            assert "archived_at" in columns, table


def test_setting_change_keeps_old_and_new_value(session: Session) -> None:
    setting = Setting(key="test.threshold", value={"v": 1}, default_value={"v": 1})
    session.add(setting)
    session.flush()
    session.add(
        SettingChange(
            setting_id=setting.id,
            old_value={"v": 1},
            new_value={"v": 2},
            changed_at=NOW,
            reason="test",
        )
    )
    session.flush()
    with pytest.raises(IntegrityError):
        session.add(Setting(key="test.threshold", value={"v": 3}, default_value={"v": 3}))
        session.flush()


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgres://u@h/db", "postgresql+psycopg://u@h/db"),
        ("postgresql://u@h/db", "postgresql+psycopg://u@h/db"),
        ("postgresql+psycopg://u@h/db", "postgresql+psycopg://u@h/db"),
    ],
)
def test_render_style_database_url_uses_psycopg_driver(url: str, expected: str) -> None:
    assert normalise_url(url) == expected
