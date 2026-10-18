"""Every tunable value Tidewatch uses, with its PRD default and valid range (PER-12).

This is the only way to read or change settings. Later code calls `get_setting(session, key)`;
nothing else reads the `setting` table directly (CLAUDE.md §4: thresholds are never hardcoded).

How values are stored as JSON:
- whole numbers           → JSON integer               e.g. 60
- USD amounts             → decimal string             e.g. "1000000"
- weights                 → {factor: decimal string}   values each 0–1, summing to 1
- AI tier                 → {"provider": ..., "model": ...}
- monthly subscriptions   → {service: decimal string}  each ≥ 0

The defaults below must match PER-12 and PRD.md exactly; a test enforces it.
"""

import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tidewatch.db.models import Setting, SettingChange

# --- Factor and tier names ---------------------------------------------------------------

#: The 11 risk factors, in PRD 3.4 order.
RISK_FACTORS: tuple[str, ...] = (
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
)

#: The opportunity score drivers (PRD 3.5).
OPPORTUNITY_FACTORS: tuple[str, ...] = (
    "valuation_gap",
    "fundamentals_momentum",
    "smart_wallet_accumulation",
    "narrative_fit",
)

AI_PROVIDERS: tuple[str, ...] = ("surplus", "anthropic")

#: Rounding allowance when checking that weights sum to 1. Equal weights such as 1/11 can't be
#: written exactly as decimals, so an exact check would reject the PRD's own default.
WEIGHT_SUM_TOLERANCE = Decimal("0.000001")


class SettingError(ValueError):
    """A value the Owner entered is not allowed. The message is shown on the Settings page."""


@dataclass(frozen=True)
class AiTier:
    provider: str
    model: str


# --- Validators ---------------------------------------------------------------------------


def _as_decimal(raw: Any, what: str) -> Decimal:
    if isinstance(raw, bool):
        raise SettingError(f"{what} must be a number.")
    try:
        value = Decimal(str(raw).strip().replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise SettingError(f"{what} must be a number.") from exc
    if not value.is_finite():
        raise SettingError(f"{what} must be a number.")
    return value


def _integer(lo: int, hi: int | None) -> Callable[[Any], int]:
    def check(raw: Any) -> int:
        value = _as_decimal(raw, "The value")
        if value != value.to_integral_value():
            raise SettingError("Enter a whole number.")
        number = int(value)
        if number < lo or (hi is not None and number > hi):
            raise SettingError(f"Enter a whole number from {lo} to {hi}.")
        return number

    return check


def _usd_min(lo: Decimal) -> Callable[[Any], str]:
    def check(raw: Any) -> str:
        value = _as_decimal(raw, "The amount")
        if value < lo:
            raise SettingError(f"Enter an amount of {lo} or more (USD).")
        return _plain(value)

    return check


def _plain(value: Decimal) -> str:
    """A decimal as plain digits: no exponent, no trailing zeros after the point."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _weights(factors: tuple[str, ...]) -> Callable[[Any], dict[str, str]]:
    def check(raw: Any) -> dict[str, str]:
        if not isinstance(raw, Mapping) or set(raw) != set(factors):
            raise SettingError(f"Give a weight for each of the {len(factors)} factors.")
        out: dict[str, str] = {}
        total = Decimal(0)
        for name in factors:
            value = _as_decimal(raw[name], f"The weight for {name}")
            if not Decimal(0) <= value <= Decimal(1):
                raise SettingError("Each weight must be between 0 and 1.")
            out[name] = _plain(value)
            total += value
        if abs(total - Decimal(1)) > WEIGHT_SUM_TOLERANCE:
            raise SettingError(f"Weights must add up to 1 (they add up to {_plain(total)}).")
        return out

    return check


def _ai_tier(anthropic_only: bool) -> Callable[[Any], dict[str, str]]:
    def check(raw: Any) -> dict[str, str]:
        if not isinstance(raw, Mapping):
            raise SettingError("Choose a provider and a model.")
        provider = str(raw.get("provider", "")).strip().lower()
        model = str(raw.get("model", "")).strip()
        if anthropic_only and provider != "anthropic":
            raise SettingError(
                "This tier must use the official Anthropic API (ARCHITECTURE.md AD9)."
            )
        if provider not in AI_PROVIDERS:
            raise SettingError(f"Provider must be one of: {', '.join(AI_PROVIDERS)}.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", model):
            raise SettingError("Enter a model ID (letters, digits, '.', '-', '_', ':' or '/').")
        return {"provider": provider, "model": model}

    return check


def _usd_map(raw: Any) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        raise SettingError("Enter one amount per service.")
    out: dict[str, str] = {}
    for name, amount in raw.items():
        service = str(name).strip()
        if not service or len(service) > 64:
            raise SettingError("Each service needs a name (up to 64 characters).")
        value = _as_decimal(amount, f"The amount for {service}")
        if value < 0:
            raise SettingError("Each amount must be 0 or more (USD per month).")
        out[service] = _plain(value)
    return out


# --- The registry -------------------------------------------------------------------------


@dataclass(frozen=True)
class SettingSpec:
    key: str
    area: str
    label: str
    kind: str  # integer | usd | weights | ai_tier | usd_map (tells the dashboard which editor)
    default: Any
    valid_range: str  # shown to the Owner
    validate: Callable[[Any], Any] = field(repr=False)
    unit: str = ""
    prd: str = ""


def _equal(factors: tuple[str, ...]) -> dict[str, str]:
    return {name: _plain(Decimal(1) / Decimal(len(factors))) for name in factors}


def _int_spec(
    key: str, area: str, label: str, default: int, lo: int, hi: int, unit: str, prd: str
) -> SettingSpec:
    return SettingSpec(
        key, area, label, "integer", default, f"{lo}–{hi}", _integer(lo, hi), unit, prd
    )


def _tier(key: str, label: str, provider: str, model: str, anthropic_only: bool) -> SettingSpec:
    valid = "Anthropic only" if anthropic_only else "provider + model"
    return SettingSpec(
        key,
        "AI models",
        label,
        "ai_tier",
        {"provider": provider, "model": model},
        valid,
        _ai_tier(anthropic_only),
        prd="ARCH AD9",
    )


SPECS: tuple[SettingSpec, ...] = (
    _int_spec(
        "refresh.launches_minutes",
        "Data refresh",
        "Launches refresh interval",
        5,
        1,
        60,
        "minutes",
        "3.3",
    ),
    _int_spec(
        "refresh.standard_minutes",
        "Data refresh",
        "Mispriced and Narratives refresh interval",
        60,
        5,
        1440,
        "minutes",
        "3.3",
    ),
    _int_spec(
        "refresh.discovery_minutes",
        "Data refresh",
        "New-listing discovery interval (CoinGecko)",
        1440,
        60,
        10080,
        "minutes",
        "3.2",
    ),
    SettingSpec(
        "scoring.risk_weights",
        "Scoring",
        "Risk factor weights",
        "weights",
        _equal(RISK_FACTORS),
        "each 0–1, sum 1",
        _weights(RISK_FACTORS),
        prd="3.4",
    ),
    SettingSpec(
        "scoring.opportunity_weights",
        "Scoring",
        "Opportunity factor weights",
        "weights",
        _equal(OPPORTUNITY_FACTORS),
        "each 0–1, sum 1",
        _weights(OPPORTUNITY_FACTORS),
        prd="3.4/3.5",
    ),
    _int_spec(
        "hardstop.liquidity_lock_max_age_hours",
        "Hard stops",
        "Liquidity-lock hard stop applies to tokens younger than",
        72,
        1,
        720,
        "hours",
        "3.4",
    ),
    SettingSpec(
        "mispriced.market_cap_min_usd",
        "Mispriced",
        "Minimum market cap",
        "usd",
        "1000000",
        "≥ 0",
        _usd_min(Decimal(0)),
        "USD",
        "3.5",
    ),
    SettingSpec(
        "mispriced.market_cap_max_usd",
        "Mispriced",
        "Maximum market cap",
        "usd",
        "500000000",
        "greater than the minimum",
        _usd_min(Decimal(0)),
        "USD",
        "3.5",
    ),
    _int_spec(
        "mispriced.fee_mc_top_percent",
        "Mispriced",
        "Revenue signal: fee/market-cap in the top",
        20,
        1,
        100,
        "%",
        "3.5",
    ),
    _int_spec(
        "mispriced.growth_min_percent_30d",
        "Mispriced",
        "Growth signal: minimum 30-day growth",
        50,
        1,
        1000,
        "%",
        "3.5",
    ),
    _int_spec(
        "mispriced.pow_growth_min_percent_30d",
        "Mispriced",
        "PoW signal: minimum 30-day hashrate or miner growth",
        30,
        1,
        1000,
        "%",
        "3.5",
    ),
    _int_spec(
        "mispriced.dev_growth_min_percent_30d",
        "Mispriced",
        "Developer momentum: minimum 30-day growth",
        50,
        1,
        1000,
        "%",
        "3.5",
    ),
    _int_spec(
        "code.max_repos_per_project",
        "Code review",
        "Repositories reviewed per project",
        10,
        1,
        50,
        "repos",
        "3.4",
    ),
    _int_spec(
        "code.fork_min_own_commits",
        "Code review",
        "Fork fails with fewer own commits than",
        20,
        0,
        10000,
        "commits",
        "3.4",
    ),
    _int_spec(
        "code.burst_share_percent_48h",
        "Code review",
        "Fail if this share of 90-day commits lands in 48 hours",
        50,
        1,
        100,
        "%",
        "3.4",
    ),
    _int_spec(
        "code.low_activity_days",
        "Code review",
        "Warning after no commits for",
        90,
        1,
        365,
        "days",
        "3.4",
    ),
    _int_spec(
        "code.abandoned_days",
        "Code review",
        "Abandoned after no commits for",
        180,
        1,
        1095,
        "days",
        "3.4",
    ),
    _int_spec(
        "code.young_account_days",
        "Code review",
        "Contributor accounts count as young under",
        90,
        1,
        1095,
        "days",
        "3.4",
    ),
    _int_spec(
        "narratives.heating_up_points_7d",
        "Narratives",
        '"Heating up" when momentum rises in 7 days by',
        20,
        1,
        100,
        "points",
        "3.6",
    ),
    _int_spec("launches.max_age_hours", "Launches", "Launched within", 72, 1, 720, "hours", "3.7"),
    SettingSpec(
        "launches.min_liquidity_usd",
        "Launches",
        "Minimum liquidity",
        "usd",
        "50000",
        "≥ 0",
        _usd_min(Decimal(0)),
        "USD",
        "3.7",
    ),
    _int_spec(
        "launches.min_smart_wallets",
        "Launches",
        "Smart wallets bought at least",
        3,
        1,
        100,
        "wallets",
        "3.7",
    ),
    _int_spec(
        "launches.min_x_mentions",
        "Launches",
        "Mentioned by at least",
        2,
        1,
        100,
        "X accounts",
        "3.7",
    ),
    _int_spec(
        "launches.holder_growth_percent_6h",
        "Launches",
        "Holder growth in 6 hours of at least",
        100,
        1,
        10000,
        "%",
        "3.7",
    ),
    _int_spec(
        "lifecycle.change_points",
        "Signal lifecycle",
        "Upgrade/downgrade when a score moves by",
        15,
        1,
        100,
        "points",
        "3.8",
    ),
    _int_spec(
        "lifecycle.invalidation_drop_percent",
        "Signal lifecycle",
        "Invalidate when price falls from first flag by",
        40,
        1,
        99,
        "%",
        "3.8",
    ),
    _int_spec(
        "xaccounts.bottom_percent",
        "X accounts",
        "Suggest removal when early-call score is in the bottom",
        20,
        1,
        100,
        "%",
        "3.13",
    ),
    _int_spec("xaccounts.bottom_days", "X accounts", "…for at least", 60, 1, 365, "days", "3.13"),
    SettingSpec(
        "costs.monthly_subscriptions_usd",
        "Costs",
        "Monthly subscriptions",
        "usd_map",
        {},
        "each ≥ 0",
        _usd_map,
        "USD / month",
        "ARCH §9",
    ),
    _tier("ai.tier.worker", "Worker tier", "surplus", "deepseek-v4.1-flash", anthropic_only=False),
    _tier(
        "ai.tier.reviewer", "Reviewer tier", "surplus", "deepseek-v4-pro-0813", anthropic_only=False
    ),
    _tier(
        "ai.tier.professor_deep",
        "Professor (deep dives)",
        "anthropic",
        "claude-sonnet-5-5",
        anthropic_only=True,
    ),
    _tier(
        "ai.tier.professor_synthesis",
        "Professor (synthesis)",
        "anthropic",
        "claude-opus-5-5",
        anthropic_only=True,
    ),
    _tier("ai.tier.fallback", "Fallback", "anthropic", "claude-haiku-5-5", anthropic_only=True),
    _int_spec(
        "ai.max_deep_dives_per_day",
        "AI models",
        "Maximum professor deep dives per day",
        30,
        0,
        500,
        "per day",
        "ARCH AD9",
    ),
)

SPECS_BY_KEY: dict[str, SettingSpec] = {spec.key: spec for spec in SPECS}


def spec_for(key: str) -> SettingSpec:
    try:
        return SPECS_BY_KEY[key]
    except KeyError:
        raise KeyError(f"Unknown setting: {key}") from None


# --- Reading ------------------------------------------------------------------------------


def _row(session: Session, key: str) -> Setting:
    spec_for(key)
    row = session.scalars(
        select(Setting).where(Setting.key == key, Setting.archived_at.is_(None))
    ).one_or_none()
    if row is None:
        raise LookupError(f"Setting {key} is missing from the database (run the migrations)")
    return row


def parse(spec: SettingSpec, stored: Any) -> Any:
    """Turn a stored JSON value into the Python type code should use."""
    if spec.kind == "integer":
        return int(stored)
    if spec.kind == "usd":
        return Decimal(str(stored))
    if spec.kind in ("weights", "usd_map"):
        return {name: Decimal(str(v)) for name, v in stored.items()}
    if spec.kind == "ai_tier":
        return AiTier(provider=stored["provider"], model=stored["model"])
    raise AssertionError(f"unknown kind {spec.kind}")  # pragma: no cover


def get_setting(session: Session, key: str) -> Any:
    """The current value of a setting, as int, Decimal, dict of Decimals or AiTier.

    This is the one function later code uses to read thresholds, weights and model tiers.
    """
    return parse(spec_for(key), _row(session, key).value)


def all_settings(session: Session) -> list[tuple[SettingSpec, Setting]]:
    rows = {
        r.key: r
        for r in session.scalars(select(Setting).where(Setting.archived_at.is_(None))).all()
    }
    return [(spec, rows[spec.key]) for spec in SPECS if spec.key in rows]


# --- Changing -----------------------------------------------------------------------------


def _check_cross_field(session: Session, key: str, value: Any) -> None:
    """Rules that involve two settings (market-cap band)."""
    if key == "mispriced.market_cap_max_usd":
        low = Decimal(str(_row(session, "mispriced.market_cap_min_usd").value))
        if Decimal(value) <= low:
            raise SettingError(f"Must be greater than the minimum market cap ({_plain(low)} USD).")
    if key == "mispriced.market_cap_min_usd":
        high = Decimal(str(_row(session, "mispriced.market_cap_max_usd").value))
        if Decimal(value) >= high:
            raise SettingError(f"Must be less than the maximum market cap ({_plain(high)} USD).")


def _record(session: Session, row: Setting, new_value: Any, reason: str) -> Setting:
    if new_value == row.value:
        return row
    session.add(
        SettingChange(
            setting_id=row.id,
            old_value=row.value,
            new_value=new_value,
            changed_at=datetime.now(UTC),
            reason=reason,
        )
    )
    row.value = new_value
    session.flush()
    return row


def update_setting(session: Session, key: str, raw_value: Any) -> Setting:
    """Validate and save a new value, logging the change. Raises SettingError if not allowed."""
    spec = spec_for(key)
    value = spec.validate(raw_value)
    _check_cross_field(session, key, value)
    return _record(session, _row(session, key), value, "edited")


def reset_setting(session: Session, key: str) -> Setting:
    """Put a setting back to its default, logging the change."""
    spec = spec_for(key)
    row = _row(session, key)
    _check_cross_field(session, key, spec.default)
    return _record(session, row, spec.default, "reset to default")


@dataclass(frozen=True)
class ChangeEntry:
    id: uuid.UUID
    key: str
    old_value: Any
    new_value: Any
    changed_at: datetime
    reason: str | None


def recent_changes(session: Session, limit: int = 100) -> list[ChangeEntry]:
    rows = session.execute(
        select(SettingChange, Setting.key)
        .join(Setting, Setting.id == SettingChange.setting_id)
        .where(SettingChange.archived_at.is_(None))
        .order_by(SettingChange.changed_at.desc(), SettingChange.created_at.desc())
        .limit(limit)
    ).all()
    return [
        ChangeEntry(c.id, key, c.old_value, c.new_value, c.changed_at, c.reason) for c, key in rows
    ]
