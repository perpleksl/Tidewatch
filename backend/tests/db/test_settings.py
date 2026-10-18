"""PER-12: settings defaults, validation and change log (database level)."""

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tidewatch.db.models import Setting, SettingChange
from tidewatch.db.settings import (
    SPECS,
    AiTier,
    SettingError,
    get_setting,
    recent_changes,
    reset_setting,
    update_setting,
)

RISK = [
    "holder_concentration",
    "unlocking_supply",
    "team",
    "revenue_quality",
    "social_authenticity",
    "roadmap_realism",
    "liquidity_depth",
    "emissions_dilution",
    "valuation_gap",
    "contract_security",
    "code_activity",
]
OPPORTUNITY = [
    "valuation_gap",
    "fundamentals_momentum",
    "smart_wallet_accumulation",
    "narrative_fit",
]

# The PER-12 ticket table, written out independently of the code under test.
TICKET_DEFAULTS: dict[str, Any] = {
    "refresh.launches_minutes": 5,
    "refresh.standard_minutes": 60,
    "scoring.risk_weights": "equal:11",
    "scoring.opportunity_weights": "equal:4",
    "hardstop.liquidity_lock_max_age_hours": 72,
    "mispriced.market_cap_min_usd": Decimal(1_000_000),
    "mispriced.market_cap_max_usd": Decimal(500_000_000),
    "mispriced.fee_mc_top_percent": 20,
    "mispriced.growth_min_percent_30d": 50,
    "mispriced.pow_growth_min_percent_30d": 30,
    "mispriced.dev_growth_min_percent_30d": 50,
    "code.max_repos_per_project": 10,
    "code.fork_min_own_commits": 20,
    "code.burst_share_percent_48h": 50,
    "code.low_activity_days": 90,
    "code.abandoned_days": 180,
    "code.young_account_days": 90,
    "narratives.heating_up_points_7d": 20,
    "launches.max_age_hours": 72,
    "launches.min_liquidity_usd": Decimal(50_000),
    "launches.min_smart_wallets": 3,
    "launches.min_x_mentions": 2,
    "launches.holder_growth_percent_6h": 100,
    "lifecycle.change_points": 15,
    "lifecycle.invalidation_drop_percent": 40,
    "xaccounts.bottom_percent": 20,
    "xaccounts.bottom_days": 60,
    "costs.monthly_subscriptions_usd": {},
    "ai.tier.worker": AiTier("surplus", "deepseek-v4.1-flash"),
    "ai.tier.reviewer": AiTier("surplus", "deepseek-v4-pro-0813"),
    "ai.tier.professor_deep": AiTier("anthropic", "claude-sonnet-5-5"),
    "ai.tier.professor_synthesis": AiTier("anthropic", "claude-opus-5-5"),
    "ai.tier.fallback": AiTier("anthropic", "claude-haiku-5-5"),
    "ai.max_deep_dives_per_day": 30,
}


def test_ac7_seeded_defaults_exactly_match_the_ticket_table(session: Session) -> None:
    """AC7: the seeded defaults (from the migration) exactly match the PER-12 table."""
    keys = set(session.scalars(select(Setting.key)).all())
    assert keys == set(TICKET_DEFAULTS), "seeded keys differ from the ticket table"
    assert {s.key for s in SPECS} == set(TICKET_DEFAULTS)

    for key, expected in TICKET_DEFAULTS.items():
        actual = get_setting(session, key)
        if isinstance(expected, str) and expected.startswith("equal:"):
            names = RISK if expected == "equal:11" else OPPORTUNITY
            assert set(actual) == set(names), key  # JSONB does not keep key order
            assert len(set(actual.values())) == 1, f"{key}: weights are not equal"
            assert abs(sum(actual.values()) - 1) < Decimal("0.000001"), key
        else:
            assert actual == expected, key
        row = session.scalars(select(Setting).where(Setting.key == key)).one()
        assert row.value == row.default_value, f"{key}: value differs from default when seeded"


def test_seeded_default_value_column_matches_code_defaults(session: Session) -> None:
    for spec in SPECS:
        row = session.scalars(select(Setting).where(Setting.key == spec.key)).one()
        assert row.default_value == spec.default, spec.key


def test_ac2_changed_value_is_stored(session: Session) -> None:
    """AC2: a saved change is what the database returns afterwards."""
    update_setting(session, "refresh.standard_minutes", "30")
    session.expire_all()
    assert get_setting(session, "refresh.standard_minutes") == 30


def test_ac3_reset_restores_default_and_is_logged(session: Session) -> None:
    """AC3: "Reset to default" restores the default and records the change."""
    update_setting(session, "launches.min_smart_wallets", 7)
    reset_setting(session, "launches.min_smart_wallets")
    assert get_setting(session, "launches.min_smart_wallets") == 3
    log = recent_changes(session)
    assert log[0].key == "launches.min_smart_wallets"
    assert (log[0].old_value, log[0].new_value, log[0].reason) == (7, 3, "reset to default")


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("refresh.launches_minutes", -5, "from 1 to 60"),
        ("refresh.launches_minutes", 61, "from 1 to 60"),
        ("refresh.launches_minutes", "2.5", "whole number"),
        ("refresh.launches_minutes", "abc", "must be a number"),
        ("lifecycle.invalidation_drop_percent", 100, "from 1 to 99"),
        ("ai.max_deep_dives_per_day", 501, "from 0 to 500"),
        ("mispriced.market_cap_min_usd", "-1", "0 or more"),
        ("launches.min_liquidity_usd", "NaN", "must be a number"),
        ("costs.monthly_subscriptions_usd", {"Nansen": "-1"}, "0 or more"),
    ],
)
def test_ac4_out_of_range_value_is_rejected_and_nothing_saved(
    session: Session, key: str, value: Any, message: str
) -> None:
    """AC4: a value outside its range is rejected with a message naming the range."""
    before = get_setting(session, key)
    with pytest.raises(SettingError, match=message):
        update_setting(session, key, value)
    assert get_setting(session, key) == before
    assert session.scalar(select(func.count()).select_from(SettingChange)) == 0


def test_ac4_market_cap_max_must_exceed_min(session: Session) -> None:
    with pytest.raises(SettingError, match="greater than the minimum"):
        update_setting(session, "mispriced.market_cap_max_usd", "1000000")
    with pytest.raises(SettingError, match="less than the maximum"):
        update_setting(session, "mispriced.market_cap_min_usd", "600000000")


def test_ac5_weights_not_summing_to_one_are_rejected(session: Session) -> None:
    """AC5: weights that don't sum to 1 are rejected."""
    weights = {name: "0.25" for name in OPPORTUNITY}
    weights["narrative_fit"] = "0.3"
    with pytest.raises(SettingError, match="add up to 1"):
        update_setting(session, "scoring.opportunity_weights", weights)


def test_ac5_weights_summing_to_one_are_accepted(session: Session) -> None:
    weights = {"valuation_gap": "0.4", "fundamentals_momentum": "0.3"}
    weights |= {"smart_wallet_accumulation": "0.2", "narrative_fit": "0.1"}
    update_setting(session, "scoring.opportunity_weights", weights)
    assert get_setting(session, "scoring.opportunity_weights")["valuation_gap"] == Decimal("0.4")


@pytest.mark.parametrize(
    "bad",
    [
        {name: "0.5" for name in OPPORTUNITY[:3]},  # a factor missing
        {**{name: "0.25" for name in OPPORTUNITY}, "extra": "0"},  # an unknown factor
        {
            **{name: "0.5" for name in OPPORTUNITY[:2]},
            OPPORTUNITY[2]: "1.5",
            OPPORTUNITY[3]: "-1.5",
        },
    ],
)
def test_ac5_malformed_weights_are_rejected(session: Session, bad: dict[str, str]) -> None:
    with pytest.raises(SettingError):
        update_setting(session, "scoring.opportunity_weights", bad)


@pytest.mark.parametrize(
    "key", ["ai.tier.professor_deep", "ai.tier.professor_synthesis", "ai.tier.fallback"]
)
def test_ac5_professor_and_fallback_tiers_must_be_anthropic(session: Session, key: str) -> None:
    """AC5: a professor or fallback tier on any provider other than Anthropic is rejected."""
    with pytest.raises(SettingError, match="official Anthropic API"):
        update_setting(session, key, {"provider": "surplus", "model": "claude-opus-5-5"})
    assert get_setting(session, key).provider == "anthropic"


def test_worker_tier_can_switch_provider(session: Session) -> None:
    update_setting(
        session, "ai.tier.worker", {"provider": "anthropic", "model": "claude-haiku-5-5"}
    )
    assert get_setting(session, "ai.tier.worker") == AiTier("anthropic", "claude-haiku-5-5")
    with pytest.raises(SettingError, match="Provider must be one of"):
        update_setting(session, "ai.tier.worker", {"provider": "openrouter", "model": "x"})
    with pytest.raises(SettingError, match="model ID"):
        update_setting(session, "ai.tier.worker", {"provider": "surplus", "model": "bad model!"})


def test_ac6_every_saved_change_is_logged_with_old_and_new_value(session: Session) -> None:
    """AC6: every saved change appears in the change log with time, old and new value."""
    update_setting(session, "code.abandoned_days", 200)
    update_setting(session, "costs.monthly_subscriptions_usd", {"Birdeye": "99", "Nansen": "49.5"})
    log = recent_changes(session)
    assert [c.key for c in log[:2]] == ["costs.monthly_subscriptions_usd", "code.abandoned_days"]
    assert (log[1].old_value, log[1].new_value) == (180, 200)
    assert log[0].new_value == {"Birdeye": "99", "Nansen": "49.5"}
    assert all(c.changed_at.tzinfo is not None for c in log)


def test_saving_the_same_value_does_not_add_a_log_entry(session: Session) -> None:
    update_setting(session, "refresh.launches_minutes", 5)
    assert recent_changes(session) == []


def test_usd_amounts_are_kept_exact(session: Session) -> None:
    update_setting(session, "launches.min_liquidity_usd", "12,345.678900")
    assert get_setting(session, "launches.min_liquidity_usd") == Decimal("12345.6789")


def test_unknown_key_is_refused(session: Session) -> None:
    with pytest.raises(KeyError):
        get_setting(session, "made.up")
