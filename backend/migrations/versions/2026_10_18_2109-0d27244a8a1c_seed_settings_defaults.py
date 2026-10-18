"""seed settings defaults

Revision ID: 0d27244a8a1c
Revises: 291dc87dae82
Create Date: 2026-10-18 21:09:18.882845

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0d27244a8a1c"
down_revision: str | Sequence[str] | None = "291dc87dae82"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# PER-12 defaults, copied here on purpose: a migration must keep seeding exactly these values
# even if the settings code changes later. tests/db/test_settings.py checks them against the
# ticket's table.
DEFAULTS: list[dict[str, object]] = [
    {"key": "refresh.launches_minutes", "default": 5},
    {"key": "refresh.standard_minutes", "default": 60},
    {
        "key": "scoring.risk_weights",
        "default": {
            "holder_concentration": "0.09090909090909090909090909091",
            "unlocking_supply": "0.09090909090909090909090909091",
            "team": "0.09090909090909090909090909091",
            "revenue_quality": "0.09090909090909090909090909091",
            "social_authenticity": "0.09090909090909090909090909091",
            "roadmap_realism": "0.09090909090909090909090909091",
            "liquidity_depth": "0.09090909090909090909090909091",
            "emissions_dilution": "0.09090909090909090909090909091",
            "valuation_gap": "0.09090909090909090909090909091",
            "contract_security": "0.09090909090909090909090909091",
            "code_activity": "0.09090909090909090909090909091",
        },
    },
    {
        "key": "scoring.opportunity_weights",
        "default": {
            "valuation_gap": "0.25",
            "fundamentals_momentum": "0.25",
            "smart_wallet_accumulation": "0.25",
            "narrative_fit": "0.25",
        },
    },
    {"key": "hardstop.liquidity_lock_max_age_hours", "default": 72},
    {"key": "mispriced.market_cap_min_usd", "default": "1000000"},
    {"key": "mispriced.market_cap_max_usd", "default": "500000000"},
    {"key": "mispriced.fee_mc_top_percent", "default": 20},
    {"key": "mispriced.growth_min_percent_30d", "default": 50},
    {"key": "mispriced.pow_growth_min_percent_30d", "default": 30},
    {"key": "mispriced.dev_growth_min_percent_30d", "default": 50},
    {"key": "code.max_repos_per_project", "default": 10},
    {"key": "code.fork_min_own_commits", "default": 20},
    {"key": "code.burst_share_percent_48h", "default": 50},
    {"key": "code.low_activity_days", "default": 90},
    {"key": "code.abandoned_days", "default": 180},
    {"key": "code.young_account_days", "default": 90},
    {"key": "narratives.heating_up_points_7d", "default": 20},
    {"key": "launches.max_age_hours", "default": 72},
    {"key": "launches.min_liquidity_usd", "default": "50000"},
    {"key": "launches.min_smart_wallets", "default": 3},
    {"key": "launches.min_x_mentions", "default": 2},
    {"key": "launches.holder_growth_percent_6h", "default": 100},
    {"key": "lifecycle.change_points", "default": 15},
    {"key": "lifecycle.invalidation_drop_percent", "default": 40},
    {"key": "xaccounts.bottom_percent", "default": 20},
    {"key": "xaccounts.bottom_days", "default": 60},
    {"key": "costs.monthly_subscriptions_usd", "default": {}},
    {"key": "ai.tier.worker", "default": {"provider": "surplus", "model": "deepseek-v4.1-flash"}},
    {
        "key": "ai.tier.reviewer",
        "default": {"provider": "surplus", "model": "deepseek-v4-pro-0813"},
    },
    {
        "key": "ai.tier.professor_deep",
        "default": {"provider": "anthropic", "model": "claude-sonnet-5-5"},
    },
    {
        "key": "ai.tier.professor_synthesis",
        "default": {"provider": "anthropic", "model": "claude-opus-5-5"},
    },
    {"key": "ai.tier.fallback", "default": {"provider": "anthropic", "model": "claude-haiku-5-5"}},
    {"key": "ai.max_deep_dives_per_day", "default": 30},
]

setting = sa.table(
    "setting",
    sa.column("id", sa.Uuid()),
    sa.column("key", sa.String()),
    sa.column("value", postgresql.JSONB()),
    sa.column("default_value", postgresql.JSONB()),
)


def upgrade() -> None:
    """Insert every setting with its default value (skips keys that already exist)."""
    conn = op.get_bind()
    existing = {row[0] for row in conn.execute(sa.select(setting.c.key))}
    rows = [
        {"id": uuid.uuid4(), "key": d["key"], "value": d["default"], "default_value": d["default"]}
        for d in DEFAULTS
        if d["key"] not in existing
    ]
    if rows:
        op.bulk_insert(setting, rows)


def downgrade() -> None:
    """Remove the seeded settings and their change log (development and tests only)."""
    keys = [str(d["key"]) for d in DEFAULTS]
    seeded = sa.select(setting.c.id).where(setting.c.key.in_(keys))
    setting_change = sa.table("setting_change", sa.column("setting_id", sa.Uuid()))
    op.execute(setting_change.delete().where(setting_change.c.setting_id.in_(seeded)))
    op.execute(setting.delete().where(setting.c.key.in_(keys)))
