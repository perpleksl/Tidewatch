"""`pow_pearl`: Pearl ($PRL) network stats from the 2Miners pool API (spike R1, PER-15).

Source: https://prl.2miners.com/api/stats, a public JSON endpoint 2Miners documents for its
pools (apidoc.2miners.com); robots.txt allows /api/stats. No key needed.

Stored as a FundamentalSnapshot for the native PRL coin (chain "pearl"):
- hashrate: network hashrate in H/s (`nodes[0].networkhashps`)
- miners: miners on **2Miners only** (`minersTotal`), not the whole network; PoW chains
  publish no network-wide miner count. Treat as a proxy (see docs/spikes/R1-pow-data.md).
- emissions_per_month: block reward * blocks per day (from the average block time) * 365.25/12
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, ClassVar

import httpx
from pydantic import Field
from sqlalchemy.orm import Session

from tidewatch.db.models import FundamentalSnapshot
from tidewatch.identity.tokens import native_token
from tidewatch.ingestion.base import Adapter, SourceRecord, SourceUnavailable
from tidewatch.ingestion.http import get_json

STATS_URL = "https://prl.2miners.com/api/stats"
PEARL_CHAIN = "pearl"
#: Block rewards are reported in the smallest unit (1 PRL = 10^8, Bitcoin-style).
BASE_UNITS_PER_PRL = Decimal(100_000_000)
SECONDS_PER_DAY = Decimal(86_400)
DAYS_PER_MONTH = Decimal("365.25") / Decimal(12)


class PearlNetworkRecord(SourceRecord):
    network_hashrate: Decimal = Field(gt=0)
    difficulty: Decimal = Field(gt=0)
    height: int = Field(gt=0)
    block_reward_prl: Decimal = Field(gt=0)
    avg_block_time_s: Decimal = Field(gt=0)
    pool_miners: int = Field(ge=0)

    @property
    def emissions_per_day(self) -> Decimal:
        return self.block_reward_prl * SECONDS_PER_DAY / self.avg_block_time_s


def parse_stats(body: Any) -> dict[str, Any]:
    """Turn the 2Miners response into a raw record (validated afterwards by Pydantic)."""
    try:
        node = body["nodes"][0]
        return {
            "observed_at": datetime.fromtimestamp(int(body["now"]) / 1000, tz=UTC),
            "network_hashrate": node["networkhashps"],
            "difficulty": node["difficulty"],
            "height": node["height"],
            "block_reward_prl": Decimal(str(node["blockReward"])) / BASE_UNITS_PER_PRL,
            "avg_block_time_s": node["avgBlockTime"],
            "pool_miners": body["minersTotal"],
        }
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise SourceUnavailable(f"unexpected 2Miners response: {type(exc).__name__}") from exc


class PowPearl(Adapter):
    name = "pow_pearl"
    interval_setting: ClassVar[str] = "refresh.standard_minutes"
    record_model: ClassVar[type[SourceRecord]] = PearlNetworkRecord

    def __init__(self, http: httpx.Client | None = None) -> None:
        self._http = http

    def fetch(self, session: Session) -> Sequence[Any]:
        return [parse_stats(get_json(STATS_URL, self._http))]

    def store(
        self, session: Session, records: Sequence[SourceRecord], available_at: datetime
    ) -> int:
        token = native_token(session, PEARL_CHAIN, name="Pearl", ticker="PRL")
        for record in records:
            if not isinstance(record, PearlNetworkRecord):
                raise TypeError("pow_pearl received a record of the wrong type")
            session.add(
                FundamentalSnapshot(
                    token_id=token.id,
                    source="2miners",
                    observed_at=record.observed_at,
                    available_at=available_at,
                    hashrate=record.network_hashrate,
                    miners=record.pool_miners,
                    emissions_per_month=record.emissions_per_day * DAYS_PER_MONTH,
                )
            )
        return len(records)
