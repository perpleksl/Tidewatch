"""Core tables for identity, ingestion, settings and costs (PER-9).

Field names follow diagrams/er-diagram.md. Further tables are added by the tickets that need them.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from tidewatch.db.base import Base, JsonValue, TableMixin

MEME_CLASSES = ("meme", "not_meme", "unclassified")
ALIAS_RELATIONS = ("wrapped", "shared_ticker")
COST_CATEGORIES = ("data", "ai")


def _in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class Token(TableMixin, Base):
    """One row per chain + contract address, or per chain for a native coin (no contract).

    The ticker is for display only and is never used to identify a token.
    """

    __tablename__ = "token"

    chain: Mapped[str] = mapped_column(String(64))
    contract_address: Mapped[str | None] = mapped_column(String(128), default=None)
    name: Mapped[str] = mapped_column(String(200))
    ticker: Mapped[str] = mapped_column(String(64))
    meme_class: Mapped[str] = mapped_column(String(16), default="unclassified")
    meme_override: Mapped[bool] = mapped_column(default=False)
    # Official links (website, docs, socials, listings); the GitHub review starts from these.
    links: Mapped[dict[str, Any]] = mapped_column(default=dict)
    #: CoinGecko's coin ID (PER-20). Not unique: one coin bridged to several chains is several
    #: tokens with the same ID. Never derived from a ticker.
    coingecko_id: Mapped[str | None] = mapped_column(String(200), default=None, index=True)

    __table_args__ = (
        CheckConstraint(_in("meme_class", MEME_CLASSES), name="meme_class"),
        CheckConstraint("length(chain) > 0", name="chain_not_empty"),
        CheckConstraint(
            "contract_address IS NULL OR length(contract_address) > 0",
            name="contract_address_not_empty",
        ),
        Index(
            "uq_token_chain_contract",
            "chain",
            "contract_address",
            unique=True,
            postgresql_where=text("contract_address IS NOT NULL"),
        ),
        Index(
            "uq_token_native_chain",
            "chain",
            unique=True,
            postgresql_where=text("contract_address IS NULL"),
        ),
    )


class TokenAlias(TableMixin, Base):
    """Links a wrapped token to its native coin, or records two tokens sharing a ticker."""

    __tablename__ = "token_alias"

    token_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("token.id"))
    alias_token_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("token.id"))
    relation: Mapped[str] = mapped_column(String(16))

    __table_args__ = (
        CheckConstraint(_in("relation", ALIAS_RELATIONS), name="relation"),
        CheckConstraint("token_id <> alias_token_id", name="not_self"),
        UniqueConstraint("token_id", "alias_token_id", "relation", name="uq_token_alias_pair"),
    )


class SnapshotMixin(TableMixin):
    """Point-in-time columns every snapshot carries (ARCHITECTURE.md Section 4).

    `observed_at` is the moment the data describes; `available_at` is when Tidewatch
    could first have known it. Backtests only use rows available at the simulated moment.
    """

    source: Mapped[str] = mapped_column(String(64))
    observed_at: Mapped[datetime]
    available_at: Mapped[datetime]


class MarketSnapshot(SnapshotMixin, Base):
    __tablename__ = "market_snapshot"

    token_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("token.id"))
    price: Mapped[Decimal | None] = mapped_column(default=None)
    market_cap: Mapped[Decimal | None] = mapped_column(default=None)
    fdv: Mapped[Decimal | None] = mapped_column(default=None)
    liquidity: Mapped[Decimal | None] = mapped_column(default=None)
    volume_24h: Mapped[Decimal | None] = mapped_column(default=None)
    holders: Mapped[int | None] = mapped_column(default=None)

    __table_args__ = (
        CheckConstraint("length(source) > 0", name="source_not_empty"),
        Index("ix_market_snapshot_token_available", "token_id", "available_at"),
    )


class FundamentalSnapshot(SnapshotMixin, Base):
    __tablename__ = "fundamental_snapshot"

    token_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("token.id"))
    revenue: Mapped[Decimal | None] = mapped_column(default=None)
    fees: Mapped[Decimal | None] = mapped_column(default=None)
    tvl: Mapped[Decimal | None] = mapped_column(default=None)
    active_users: Mapped[int | None] = mapped_column(default=None)
    hashrate: Mapped[Decimal | None] = mapped_column(default=None)
    miners: Mapped[int | None] = mapped_column(default=None)
    emissions_per_month: Mapped[Decimal | None] = mapped_column(default=None)

    __table_args__ = (
        CheckConstraint("length(source) > 0", name="source_not_empty"),
        Index("ix_fundamental_snapshot_token_available", "token_id", "available_at"),
    )


class CostEntry(TableMixin, Base):
    """Spend per data source and per AI call (PRD 3.12). Stands alone."""

    __tablename__ = "cost_entry"

    source: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(8))
    amount_usd: Mapped[Decimal]
    # AI calls only (CLAUDE.md: log provider, model, tokens and cost for every call).
    # `source` holds the provider for AI calls ("surplus" or "anthropic").
    model: Mapped[str | None] = mapped_column(String(128), default=None)
    tier: Mapped[str | None] = mapped_column(String(32), default=None)
    input_tokens: Mapped[int | None] = mapped_column(default=None)
    output_tokens: Mapped[int | None] = mapped_column(default=None)
    cache_read_tokens: Mapped[int | None] = mapped_column(default=None)
    cache_write_tokens: Mapped[int | None] = mapped_column(default=None)
    batch: Mapped[bool] = mapped_column(default=False, server_default=false())
    #: Data sources with a call allowance (PER-20): number of API calls this entry covers.
    calls: Mapped[int | None] = mapped_column(default=None)
    at: Mapped[datetime]

    __table_args__ = (
        CheckConstraint(_in("category", COST_CATEGORIES), name="category"),
        CheckConstraint("length(source) > 0", name="source_not_empty"),
        Index("ix_cost_entry_at", "at"),
    )


class Setting(TableMixin, Base):
    """A tunable value ([CALIBRATE] thresholds, weights, model tiers).

    Read and change settings only through tidewatch.db.settings, which validates them.
    `value` and `default_value` hold JSON: numbers, decimal strings or small objects.
    """

    __tablename__ = "setting"

    key: Mapped[str] = mapped_column(String(128), unique=True)
    value: Mapped[Any] = mapped_column(JsonValue)
    default_value: Mapped[Any] = mapped_column(JsonValue)


class SettingChange(TableMixin, Base):
    """Change log for settings: every edit keeps the old and new value."""

    __tablename__ = "setting_change"

    setting_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("setting.id"))
    old_value: Mapped[Any] = mapped_column(JsonValue, nullable=True, default=None)
    new_value: Mapped[Any] = mapped_column(JsonValue)
    changed_at: Mapped[datetime]
    reason: Mapped[str | None] = mapped_column(Text, default=None)


SOURCE_STATES = ("ok", "degraded", "paused")
TEST_MODES = ("fail", "rate_limit", "invalid")


class SourceStatus(TableMixin, Base):
    """Health of one data source (PRD 3.3, 3.12), shown on System Health.

    `run_requested_at` asks the worker to run the source on its next check ("Run now").
    `test_mode` is used only by the `fake_source` test adapter to simulate failures.
    """

    __tablename__ = "source_status"

    source: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    last_attempt_at: Mapped[datetime | None] = mapped_column(default=None)
    last_success_at: Mapped[datetime | None] = mapped_column(default=None)
    paused_until: Mapped[datetime | None] = mapped_column(default=None)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    # Times of recent errors (ISO 8601, UTC), trimmed to the last 24 hours.
    recent_errors: Mapped[Any] = mapped_column(JsonValue, default=list)
    run_requested_at: Mapped[datetime | None] = mapped_column(default=None)
    test_mode: Mapped[str | None] = mapped_column(String(16), default=None)

    __table_args__ = (
        CheckConstraint(_in("status", SOURCE_STATES), name="status"),
        CheckConstraint(f"test_mode IS NULL OR {_in('test_mode', TEST_MODES)}", name="test_mode"),
    )


LISTING_OUTCOMES = ("assessed", "outside_universe", "unresolved")
CANDIDATE_TABS = ("launches", "mispriced")


class CoinGeckoListing(TableMixin, Base):
    """Every CoinGecko coin ID Tidewatch has seen (PER-19; PRD 3.2 "New-listing discovery").

    The first daily run records the starting list (`in_starting_list`), with no outcome. Coins
    that appear later are new listings: each gets an outcome with a reason and, when it is in
    the covered universe, a candidate tab and a link to its Token.
    """

    __tablename__ = "coingecko_listing"

    coingecko_id: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(300))
    #: Display only; never used to identify a token.
    symbol: Mapped[str] = mapped_column(String(64))
    first_seen_at: Mapped[datetime]
    in_starting_list: Mapped[bool] = mapped_column(default=False)
    outcome: Mapped[str | None] = mapped_column(String(24), default=None)
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    #: Tidewatch chain names this listing resolved to (display; tokens hold the identity).
    chains: Mapped[Any] = mapped_column(JsonValue, default=list)
    candidate_tab: Mapped[str | None] = mapped_column(String(16), default=None)
    launched_at: Mapped[datetime | None] = mapped_column(default=None)
    token_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("token.id"), default=None)

    __table_args__ = (
        CheckConstraint(f"outcome IS NULL OR {_in('outcome', LISTING_OUTCOMES)}", name="outcome"),
        CheckConstraint(
            f"candidate_tab IS NULL OR {_in('candidate_tab', CANDIDATE_TABS)}",
            name="candidate_tab",
        ),
        Index("ix_coingecko_listing_first_seen", "first_seen_at"),
    )


class IngestionTestRow(SnapshotMixin, Base):
    """Synthetic rows written only by the `fake_source` test adapter (PER-13).

    Kept apart from real data so nothing downstream has to filter out fake tokens.
    """

    __tablename__ = "ingestion_test_row"

    label: Mapped[str] = mapped_column(String(64))
    value: Mapped[Decimal]

    __table_args__ = (CheckConstraint("length(source) > 0", name="source_not_empty"),)
