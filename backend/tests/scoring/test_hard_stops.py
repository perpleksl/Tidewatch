"""PER-23 AC2: each PRD 3.4 hard stop is detected from a GoPlus-shaped result (synthetic)."""

from decimal import Decimal
from typing import Any

import pytest

from tidewatch.scoring.hard_stops import evaluate_evm, evaluate_solana, top10_share

OWNER = "0xtest00000000000000000000000000000000000a"
DEAD = "0x000000000000000000000000000000000000dead"


def evm(**overrides: Any) -> dict[str, Any]:
    """A clean, renounced, open-source token; override fields to create each case."""
    base: dict[str, Any] = {
        "is_open_source": "1",
        "is_honeypot": "0",
        "is_mintable": "0",
        "owner_address": "",
        "creator_address": "0xtest00000000000000000000000000000000000c",
        "can_take_back_ownership": "0",
        "hidden_owner": "0",
        "owner_change_balance": "0",
        "is_blacklisted": "0",
        "buy_tax": "0",
        "sell_tax": "0",
        "transfer_tax": "0",
        "slippage_modifiable": "0",
        "personal_slippage_modifiable": "0",
        "cannot_sell_all": "0",
        "holders": [],
        "lp_holders": [],
        "dex": [],
    }
    return {**base, **overrides}


def codes(data: dict[str, Any]) -> list[str]:
    return [h["code"] for h in evaluate_evm(data).hard_stops]


def test_clean_token_passes() -> None:
    result = evaluate_evm(evm())
    assert (result.status, result.hard_stops) == ("passed", [])


def test_mint_by_non_renounced_owner_is_a_hard_stop() -> None:
    """Hard stop: mint function enabled by a non-renounced owner."""
    assert codes(evm(is_mintable="1", owner_address=OWNER)) == ["mint"]
    result = evaluate_evm(evm(is_mintable="1", owner_address=OWNER))
    assert result.status == "avoid"
    assert result.hard_stops[0]["reason"] == "Mint function enabled by a non-renounced owner"


@pytest.mark.parametrize("owner", ["", DEAD])
def test_mint_with_renounced_owner_is_not_a_hard_stop(owner: str) -> None:
    assert codes(evm(is_mintable="1", owner_address=owner)) == []


def test_ownership_that_can_be_taken_back_is_not_renounced() -> None:
    assert codes(evm(is_mintable="1", owner_address="", can_take_back_ownership="1")) == ["mint"]


def test_honeypot_is_a_hard_stop() -> None:
    """Hard stop: honeypot detected (cannot sell)."""
    assert codes(evm(is_honeypot="1")) == ["honeypot"]


def test_owner_can_modify_balances_is_a_hard_stop() -> None:
    assert codes(evm(owner_change_balance="1")) == ["balance"]


def test_blacklist_with_live_owner_is_a_hard_stop() -> None:
    assert codes(evm(is_blacklisted="1", owner_address=OWNER)) == ["blacklist"]
    assert codes(evm(is_blacklisted="1", owner_address="")) == []


@pytest.mark.parametrize("field", ["buy_tax", "sell_tax", "transfer_tax"])
def test_tax_over_10_percent_is_a_hard_stop(field: str) -> None:
    """Owner decision 21 Oct 2026: today's tax over 10% is a hard stop; exactly 10% is not."""
    assert codes(evm(**{field: "0.12"})) == ["tax"]
    assert "12%" in evaluate_evm(evm(**{field: "0.12"})).hard_stops[0]["reason"]
    assert codes(evm(**{field: "0.10"})) == []


@pytest.mark.parametrize("field", ["slippage_modifiable", "personal_slippage_modifiable"])
def test_tax_changeable_by_live_owner_is_a_hard_stop(field: str) -> None:
    """Owner decision 21 Oct 2026: a tax an un-renounced owner can change is a hard stop."""
    assert codes(evm(**{field: "1"}, owner_address=OWNER)) == ["tax_changeable"]
    assert codes(evm(**{field: "1"}, owner_address="")) == []


def test_no_liquidity_lock_hard_stop_in_m1_but_pool_data_is_recorded() -> None:
    """Owner decision 21 Oct 2026: no LP-lock hard stop in M1; pool shares are recorded."""
    result = evaluate_evm(
        evm(
            owner_address=OWNER,
            lp_holders=[
                {"address": DEAD, "tag": "", "is_locked": "0", "percent": "0.30"},
                {"address": "0xtestlocker", "tag": "UNCX", "is_locked": "1", "percent": "0.20"},
                {"address": OWNER, "tag": "", "is_locked": "0", "percent": "0.45"},
                {"address": "0xtestother", "tag": "", "is_locked": "0", "percent": "0.05"},
            ],
        )
    )
    assert result.hard_stops == []
    assert result.lp_locked_or_burned_share == Decimal("0.50")
    assert result.lp_creator_owner_unlocked_share == Decimal("0.45")


def test_holder_share_excludes_pools_burns_locks_and_exchanges() -> None:
    """PER-23 AC4: top-10 share excludes tagged pools, burns, locks and exchanges."""
    holders = [
        {"address": "0xtestpair", "tag": "", "is_locked": "0", "percent": "0.40"},  # the pool
        {"address": DEAD, "tag": "", "is_locked": "0", "percent": "0.10"},  # burn
        {"address": "0xtestlock", "tag": "", "is_locked": "1", "percent": "0.05"},  # locked
        {"address": "0xtestcex", "tag": "Binance 14", "is_locked": "0", "percent": "0.08"},
        {"address": "0xtestdeployer", "tag": "Deployer", "is_locked": "0", "percent": "0.07"},
        {"address": "0xtestwhale", "tag": "", "is_locked": "0", "percent": "0.03"},
    ]
    assert top10_share(holders, ["0xTESTPAIR"]) == Decimal("0.10")
    result = evaluate_evm(
        evm(holders=holders, dex=[{"pair": "0xtestpair", "liquidity": "250000.5", "name": "Uni"}])
    )
    assert result.top10_holder_share == Decimal("0.10")
    assert result.dex_liquidity_usd == Decimal("250000.5")


def test_closed_source_contract_is_unknown_not_passed() -> None:
    result = evaluate_evm({"is_open_source": "0"})
    assert result.status == "unknown"
    assert "isn't verified" in (result.reason or "")


def test_missing_core_fields_is_unknown() -> None:
    assert evaluate_evm({"is_open_source": "1"}).status == "unknown"


def test_cannot_sell_all_is_a_warning_not_a_hard_stop() -> None:
    result = evaluate_evm(evm(cannot_sell_all="1"))
    assert result.status == "passed"
    assert [w["code"] for w in result.warnings] == ["cannot_sell_all"]


# --- Solana -----------------------------------------------------------------------------


def sol(**overrides: Any) -> dict[str, Any]:
    off = {"status": "0", "authority": []}
    base: dict[str, Any] = {
        "mintable": off,
        "freezable": off,
        "balance_mutable_authority": off,
        "transfer_fee_upgradable": off,
        "transfer_fee": {},
        "transfer_hook": [],
        "non_transferable": "0",
        "holders": [],
        "dex": [],
    }
    return {**base, **overrides}


ON = {"status": "1", "authority": [{"address": "TestAuthority111", "malicious_address": 0}]}


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("mintable", "mint"),
        ("freezable", "honeypot"),
        ("balance_mutable_authority", "balance"),
        ("transfer_fee_upgradable", "tax_changeable"),
    ],
)
def test_solana_authorities_are_hard_stops(field: str, code: str) -> None:
    result = evaluate_solana(sol(**{field: ON}))
    assert [h["code"] for h in result.hard_stops] == [code]
    assert result.status == "avoid"


def test_solana_clean_token_passes_and_records_liquidity() -> None:
    result = evaluate_solana(
        sol(dex=[{"id": "TestPool111", "tvl": "120000", "dexname": "Raydium"}])
    )
    assert (result.status, result.dex_liquidity_usd) == ("passed", Decimal(120000))


def test_solana_transfer_fee_over_10_percent_is_a_hard_stop() -> None:
    fee = {"current_fee_rate": {"fee_rate": 1500, "maximum_fee": 0}}
    assert [h["code"] for h in evaluate_solana(sol(transfer_fee=fee)).hard_stops] == ["tax"]
    ok = {"current_fee_rate": {"fee_rate": 1000, "maximum_fee": 0}}
    assert evaluate_solana(sol(transfer_fee=ok)).hard_stops == []


def test_solana_non_transferable_or_hook_is_a_honeypot() -> None:
    assert evaluate_solana(sol(non_transferable="1")).status == "avoid"
    hook = [{"address": "TestHook111", "malicious_address": 0}]
    assert evaluate_solana(sol(transfer_hook=hook)).status == "avoid"
