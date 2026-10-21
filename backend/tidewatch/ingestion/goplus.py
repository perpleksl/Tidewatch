"""`goplus`: contract security, top holders and DEX liquidity (PER-23; PRD 3.4).

GoPlus's free token-security API (anonymous access, ~100 calls a minute on the free plan):
- EVM: GET https://api.gopluslabs.io/api/v1/token_security/{chain_id}?contract_addresses=…
- Solana: GET https://api.gopluslabs.io/api/v1/solana/token_security?contract_addresses=…
Responses look like {"code": 1, "message": "OK", "result": {"<address>": {...}}}; code 2 is
"partial data". Checked against docs.gopluslabs.io on 21 Oct 2026.

Which tokens, how often (Owner decision, 21 Oct 2026, on PER-23):
- Only contract tokens on a covered chain whose latest market cap is inside Mispriced's
  range (`mispriced.market_cap_min_usd` to `_max_usd`). Only those can appear on Mispriced.
- Each is checked when first eligible, then once a day (`RECHECK_AFTER`).
- At most `CHECKS_PER_RUN` per run, spaced out, so one run never blocks the worker for long;
  the adapter runs hourly, so a backlog clears over a few runs.
Native coins (e.g. $PRL) are never checked: contract security is "Not applicable".
"""

import time
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, ClassVar

import httpx
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tidewatch.db.models import MarketSnapshot, SecurityCheck, Token
from tidewatch.db.settings import get_setting
from tidewatch.identity.chains import GOPLUS_EVM_CHAIN_IDS
from tidewatch.ingestion.base import Adapter, RateLimited, SourceRecord, SourceUnavailable
from tidewatch.ingestion.http import get_json
from tidewatch.scoring.hard_stops import SecurityResult, evaluate_evm, evaluate_solana

API_BASE = "https://api.gopluslabs.io/api/v1"
SOURCE = "goplus"
#: Owner decision (21 Oct 2026): re-check each eligible token once a day.
RECHECK_AFTER = timedelta(hours=24)
#: Technical limits for the free plan (~100 calls/minute): ~90 seconds of calls per run.
CHECKS_PER_RUN = 120
CALL_SPACING_SECONDS = 0.7
#: GoPlus answers 200 with this code when the request limit is reached.
LIMIT_CODES = {4029}
PAUSE_ON_LIMIT = timedelta(minutes=5)
#: The GoPlus fields kept on each row, so every result can be traced to its inputs.
RAW_KEYS = (
    "is_open_source",
    "is_honeypot",
    "is_mintable",
    "owner_address",
    "creator_address",
    "can_take_back_ownership",
    "hidden_owner",
    "owner_change_balance",
    "is_blacklisted",
    "buy_tax",
    "sell_tax",
    "transfer_tax",
    "slippage_modifiable",
    "personal_slippage_modifiable",
    "cannot_sell_all",
    "holder_count",
    "mintable",
    "freezable",
    "balance_mutable_authority",
    "transfer_fee",
    "transfer_fee_upgradable",
    "transfer_hook",
    "non_transferable",
)


class SecurityRecord(SourceRecord):
    token_id: str = Field(min_length=1)
    status: str
    reason: str | None = None
    hard_stops: list[dict[str, str]] = Field(default_factory=list)
    warnings: list[dict[str, str]] = Field(default_factory=list)
    top10_holder_share: Decimal | None = None
    dex_liquidity_usd: Decimal | None = None
    lp_locked_or_burned_share: Decimal | None = None
    lp_creator_owner_unlocked_share: Decimal | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


def eligible_tokens(session: Session, now: datetime) -> list[Token]:
    """Covered contract tokens in Mispriced's market-cap range, due for a check, oldest first."""
    low = get_setting(session, "mispriced.market_cap_min_usd")
    high = get_setting(session, "mispriced.market_cap_max_usd")
    chains = [*GOPLUS_EVM_CHAIN_IDS, "solana"]
    usable = (MarketSnapshot.archived_at.is_(None), MarketSnapshot.available_at <= now)
    newest = (
        select(
            MarketSnapshot.token_id,
            func.max(MarketSnapshot.available_at).label("newest"),
        )
        .where(*usable, MarketSnapshot.market_cap.is_not(None))
        .group_by(MarketSnapshot.token_id)
        .subquery()
    )
    latest_cap = (
        select(MarketSnapshot.token_id, func.max(MarketSnapshot.market_cap).label("market_cap"))
        .join(
            newest,
            (newest.c.token_id == MarketSnapshot.token_id)
            & (newest.c.newest == MarketSnapshot.available_at),
        )
        .where(*usable, MarketSnapshot.market_cap.is_not(None))
        .group_by(MarketSnapshot.token_id)
        .subquery()
    )
    last_check = (
        select(SecurityCheck.token_id, func.max(SecurityCheck.available_at).label("checked"))
        .where(SecurityCheck.archived_at.is_(None))
        .group_by(SecurityCheck.token_id)
        .subquery()
    )
    rows = session.execute(
        select(Token, last_check.c.checked)
        .join(latest_cap, latest_cap.c.token_id == Token.id)
        .outerjoin(last_check, last_check.c.token_id == Token.id)
        .where(
            Token.archived_at.is_(None),
            Token.contract_address.is_not(None),
            Token.chain.in_(chains),
            latest_cap.c.market_cap >= low,
            latest_cap.c.market_cap <= high,
        )
    ).all()
    due = [(t, c) for t, c in rows if c is None or now - c >= RECHECK_AFTER]
    due.sort(key=lambda tc: (tc[1] is not None, tc[1] or now))  # never checked first
    return [t for t, _ in due]


def _record(
    token: Token, result: SecurityResult, raw: dict[str, Any], now: datetime
) -> dict[str, Any]:
    return {
        "observed_at": now,
        "token_id": str(token.id),
        "status": result.status,
        "reason": result.reason,
        "hard_stops": result.hard_stops,
        "warnings": result.warnings,
        "top10_holder_share": result.top10_holder_share,
        "dex_liquidity_usd": result.dex_liquidity_usd,
        "lp_locked_or_burned_share": result.lp_locked_or_burned_share,
        "lp_creator_owner_unlocked_share": result.lp_creator_owner_unlocked_share,
        "raw": {k: raw[k] for k in RAW_KEYS if k in raw},
    }


def _unknown(token: Token, reason: str, now: datetime) -> dict[str, Any]:
    return _record(token, SecurityResult(status="unknown", reason=reason), {}, now)


class GoPlus(Adapter):
    name = SOURCE
    interval_setting: ClassVar[str] = "refresh.standard_minutes"
    record_model: ClassVar[type[SourceRecord]] = SecurityRecord

    def __init__(
        self, http: httpx.Client | None = None, sleep: Callable[[float], None] = time.sleep
    ) -> None:
        self._http = http
        self._sleep = sleep

    def _query(self, token: Token) -> dict[str, Any] | None:
        address = str(token.contract_address)
        if token.chain == "solana":
            url = f"{API_BASE}/solana/token_security"
        else:
            url = f"{API_BASE}/token_security/{GOPLUS_EVM_CHAIN_IDS[token.chain]}"
        body = get_json(url, self._http, contract_addresses=address)
        if not isinstance(body, dict):
            raise SourceUnavailable("unexpected GoPlus response")
        code = body.get("code")
        if code in LIMIT_CODES:
            raise RateLimited(resume_at=datetime.now(UTC) + PAUSE_ON_LIMIT)
        if code not in (1, 2):
            raise SourceUnavailable(f"GoPlus error {code}: {body.get('message')}")
        result = body.get("result") or {}
        if not isinstance(result, dict):
            return None
        # Keys may come back lower-cased (EVM) or as sent (Solana).
        found = result.get(address) or result.get(address.lower())
        return found if isinstance(found, dict) else None

    def fetch(self, session: Session) -> Sequence[Any]:
        now = datetime.now(UTC)
        tokens = eligible_tokens(session, now)[:CHECKS_PER_RUN]
        records: list[dict[str, Any]] = []
        failures = 0
        for index, token in enumerate(tokens):
            if index:
                self._sleep(CALL_SPACING_SECONDS)
            try:
                data = self._query(token)
            except RateLimited:
                if not records:
                    raise
                break  # keep what was checked; the rest waits for the next run
            except SourceUnavailable as exc:
                failures += 1
                records.append(
                    _unknown(token, f"Security check failed ({exc}); retried tomorrow", now)
                )
                continue
            if data is None:
                records.append(_unknown(token, "GoPlus has no data for this contract", now))
                continue
            result = evaluate_solana(data) if token.chain == "solana" else evaluate_evm(data)
            records.append(_record(token, result, data, now))
        if tokens and failures == len(tokens):
            raise SourceUnavailable("every GoPlus check failed")
        return records

    def store(
        self, session: Session, records: Sequence[SourceRecord], available_at: datetime
    ) -> int:
        for record in records:
            if not isinstance(record, SecurityRecord):
                raise TypeError("goplus received a record of the wrong type")
            session.add(
                SecurityCheck(
                    token_id=uuid.UUID(record.token_id),
                    source=SOURCE,
                    observed_at=record.observed_at,
                    available_at=available_at,
                    status=record.status,
                    reason=record.reason,
                    hard_stops=record.hard_stops,
                    warnings=record.warnings,
                    top10_holder_share=record.top10_holder_share,
                    dex_liquidity_usd=record.dex_liquidity_usd,
                    lp_locked_or_burned_share=record.lp_locked_or_burned_share,
                    lp_creator_owner_unlocked_share=record.lp_creator_owner_unlocked_share,
                    raw=record.raw,
                )
            )
        return len(records)
