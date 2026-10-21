"""Hard stops and contract-security inputs from GoPlus results (PER-23; PRD 3.4).

Pure functions: given one GoPlus token-security result, decide which hard stops fire and
compute the inputs for risk factors 1 (holder concentration) and 7 (liquidity depth). The
adapter stores the outcome; nothing here calls the network or the database.

PRD 3.4 hard stops, as decided with the Owner (PER-23 comments, 21 Oct 2026):
- Mint function enabled by a non-renounced owner.
- Honeypot detected (cannot sell).
- Owner can modify balances, blacklist holders, or change transfer tax above 10%: a hard
  stop if today's buy/sell/transfer tax is over 10%, OR an un-renounced owner can change the
  tax at all (GoPlus can't show the maximum, so it can't be proven to stay at or below 10%).
- Liquidity not locked or burned (tokens under 72h): **not applied in M1**. Under-72h tokens go
  to Launches (M3), never Mispriced; the rule is redefined and decided in M3. The pool data
  is recorded now (`lp_*` shares).

GoPlus reports flags as "1"/"0" strings, and taxes and percentages on a 0-1 scale where
1 = 100% (docs.gopluslabs.io "Response Details", checked 21 Oct 2026). A missing flag means
"unknown", never "safe".
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

#: PRD 3.4 rule (not a [CALIBRATE] value): transfer tax above 10% is a hard stop.
MAX_TAX = Decimal("0.10")
#: Solana transfer fees are in basis points: 1,000 bps = 10%.
MAX_TAX_BPS = Decimal(1000)
BURN_ADDRESSES = frozenset(
    {
        "0x0000000000000000000000000000000000000000",
        "0x000000000000000000000000000000000000dead",
        "11111111111111111111111111111111",
    }
)
BURN_WORDS = ("burn", "dead", "null", "black hole")
#: Holder tags that are the project's own wallets, so they stay in the concentration figure.
OWN_WALLET_WORDS = ("deployer", "creator", "owner", "team")


@dataclass
class SecurityResult:
    status: str  # "passed" | "avoid" | "unknown"
    reason: str | None = None
    hard_stops: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    top10_holder_share: Decimal | None = None
    dex_liquidity_usd: Decimal | None = None
    lp_locked_or_burned_share: Decimal | None = None
    lp_creator_owner_unlocked_share: Decimal | None = None


def _flag(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    return str(value).strip() == "1"


def _num(value: Any) -> Decimal | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _pct(value: Decimal) -> str:
    return f"{(value * 100).quantize(Decimal('0.1')).normalize():f}%"


def _is_burn(holder: dict[str, Any]) -> bool:
    address = str(holder.get("address") or holder.get("token_account") or "").lower()
    tag = str(holder.get("tag") or "").lower()
    return address in BURN_ADDRESSES or any(w in tag for w in BURN_WORDS)


def _locked(holder: dict[str, Any]) -> bool:
    return _flag(holder.get("is_locked")) is True


def top10_share(holders: Any, pool_addresses: Iterable[str]) -> Decimal | None:
    """Share held by the top 10 holders, excluding pools, burns, locks and tagged exchanges.

    PRD 3.4 factor 1 excludes "known pools, burns and exchanges". GoPlus tags known entities
    (pools, exchanges, burn addresses); any tagged holder is excluded except the project's own
    wallets (deployer, creator, owner, team), which are exactly what concentration should show.
    """
    if not isinstance(holders, list) or not holders:
        return None
    pools = {a.lower() for a in pool_addresses}
    total = Decimal(0)
    for holder in holders[:10]:
        if not isinstance(holder, dict):
            continue
        address = str(holder.get("address") or holder.get("token_account") or "").lower()
        tag = str(holder.get("tag") or "").lower()
        own_wallet = any(w in tag for w in OWN_WALLET_WORDS)
        if _is_burn(holder) or _locked(holder) or address in pools or (tag and not own_wallet):
            continue
        total += _num(holder.get("percent")) or Decimal(0)
    return total


def _lp_shares(lp_holders: Any, insiders: set[str]) -> tuple[Decimal | None, Decimal | None]:
    if not isinstance(lp_holders, list) or not lp_holders:
        return None, None
    locked = Decimal(0)
    insider_unlocked = Decimal(0)
    for holder in lp_holders:
        if not isinstance(holder, dict):
            continue
        share = _num(holder.get("percent")) or Decimal(0)
        if _is_burn(holder) or _locked(holder):
            locked += share
        elif str(holder.get("address") or "").lower() in insiders:
            insider_unlocked += share
    return locked, insider_unlocked


def _stop(result: SecurityResult, code: str, reason: str) -> None:
    result.hard_stops.append({"code": code, "reason": reason})


def evaluate_evm(data: dict[str, Any]) -> SecurityResult:
    """Hard stops and inputs from a GoPlus EVM token-security result."""
    result = SecurityResult(status="passed")
    owner = data.get("owner_address")
    owner_known = owner is not None
    owner_text = str(owner or "").lower()
    renounced = (
        owner_known
        and (owner_text == "" or owner_text in BURN_ADDRESSES)
        and _flag(data.get("can_take_back_ownership")) is not True
        and _flag(data.get("hidden_owner")) is not True
    )

    if _flag(data.get("is_mintable")) and not renounced:
        _stop(result, "mint", "Mint function enabled by a non-renounced owner")
    if _flag(data.get("is_honeypot")):
        _stop(result, "honeypot", "Honeypot detected: the token may be impossible to sell")
    if _flag(data.get("owner_change_balance")):
        _stop(result, "balance", "Owner can modify holders' balances")
    if _flag(data.get("is_blacklisted")) and not renounced:
        _stop(result, "blacklist", "Owner can blacklist holders")
    taxes = {name: _num(data.get(f"{name}_tax")) for name in ("buy", "sell", "transfer")}
    for name, tax in taxes.items():
        if tax is not None and tax > MAX_TAX:
            _stop(result, "tax", f"{name.capitalize()} tax is {_pct(tax)}, above 10%")
    if (
        _flag(data.get("slippage_modifiable")) or _flag(data.get("personal_slippage_modifiable"))
    ) and not renounced:
        _stop(
            result, "tax_changeable", "Owner can change the tax (no proof it stays at or below 10%)"
        )

    if _flag(data.get("cannot_sell_all")):
        result.warnings.append(
            {"code": "cannot_sell_all", "reason": "Holders can't sell their whole balance at once"}
        )
    if _flag(data.get("hidden_owner")):
        result.warnings.append({"code": "hidden_owner", "reason": "Contract has a hidden owner"})

    raw_dex = data.get("dex")
    dex: list[Any] = raw_dex if isinstance(raw_dex, list) else []
    pools = [str(d.get("pair") or "") for d in dex if isinstance(d, dict)]
    liquidity = [_num(d.get("liquidity")) for d in dex if isinstance(d, dict)]
    result.dex_liquidity_usd = (
        sum((v for v in liquidity if v is not None), Decimal(0)) if dex else None
    )
    result.top10_holder_share = top10_share(data.get("holders"), pools)
    insiders = {a for a in (owner_text, str(data.get("creator_address") or "").lower()) if a}
    result.lp_locked_or_burned_share, result.lp_creator_owner_unlocked_share = _lp_shares(
        data.get("lp_holders"), insiders
    )

    if result.hard_stops:
        result.status = "avoid"
    elif _flag(data.get("is_open_source")) is False:
        result.status, result.reason = (
            "unknown",
            "Contract source code isn't verified, so it can't be checked",
        )
    elif all(
        _flag(data.get(k)) is None for k in ("is_honeypot", "is_mintable", "owner_change_balance")
    ):
        result.status, result.reason = (
            "unknown",
            "GoPlus returned no security data for this contract",
        )
    return result


def _authority_active(item: Any) -> bool:
    """Solana: a function is usable when its status is "1" and it still has an authority."""
    if not isinstance(item, dict) or _flag(item.get("status")) is not True:
        return False
    authority = item.get("authority")
    if authority is None:
        return True
    return isinstance(authority, list) and len(authority) > 0


def evaluate_solana(data: dict[str, Any]) -> SecurityResult:
    """Hard stops and inputs from a GoPlus Solana token-security result.

    Solana equivalents of the PRD 3.4 hard stops: mint authority (mint), freeze authority or a
    transfer hook / non-transferable token (holders can be stopped from selling = honeypot),
    balance-mutable authority (modify balances), transfer fee above 10% or upgradable fee (tax).
    """
    result = SecurityResult(status="passed")
    if _authority_active(data.get("mintable")):
        _stop(result, "mint", "Mint authority is still active")
    if _authority_active(data.get("freezable")):
        _stop(result, "honeypot", "Freeze authority is active: holders can be blocked from selling")
    hook = data.get("transfer_hook")
    if (isinstance(hook, list) and hook) or (isinstance(hook, dict) and hook.get("address")):
        _stop(result, "honeypot", "Transfer hook can block transfers")
    if _flag(data.get("non_transferable")):
        _stop(result, "honeypot", "Token is non-transferable")
    if _authority_active(data.get("balance_mutable_authority")):
        _stop(result, "balance", "An authority can modify holders' balances")
    fee = data.get("transfer_fee")
    rate = None
    if isinstance(fee, dict) and isinstance(fee.get("current_fee_rate"), dict):
        rate = _num(fee["current_fee_rate"].get("fee_rate"))
    if rate is not None and rate > MAX_TAX_BPS:
        _stop(result, "tax", f"Transfer fee is {_pct(rate / 10000)}, above 10%")
    if _authority_active(data.get("transfer_fee_upgradable")):
        _stop(
            result,
            "tax_changeable",
            "Transfer fee can be changed (no proof it stays at or below 10%)",
        )

    raw_dex = data.get("dex")
    dex: list[Any] = raw_dex if isinstance(raw_dex, list) else []
    pools = [str(d.get("id") or "") for d in dex if isinstance(d, dict)]
    tvl = [_num(d.get("tvl")) for d in dex if isinstance(d, dict)]
    result.dex_liquidity_usd = sum((v for v in tvl if v is not None), Decimal(0)) if dex else None
    result.top10_holder_share = top10_share(data.get("holders"), pools)
    creator = data.get("creator")
    insiders = set()
    if isinstance(creator, dict) and creator.get("address"):
        insiders.add(str(creator["address"]).lower())
    lp_source = next(
        (d.get("lp_holders") for d in dex if isinstance(d, dict) and d.get("lp_holders")), None
    )
    result.lp_locked_or_burned_share, result.lp_creator_owner_unlocked_share = _lp_shares(
        lp_source, insiders
    )

    if result.hard_stops:
        result.status = "avoid"
    elif data.get("mintable") is None and data.get("freezable") is None:
        result.status, result.reason = "unknown", "GoPlus returned no security data for this token"
    return result
