"""Which adapters the worker runs. Real providers are added here from M1 onward."""

import os

from tidewatch.ingestion.base import Adapter
from tidewatch.ingestion.coingecko import CoinGecko
from tidewatch.ingestion.coingecko_listings import CoinGeckoListings
from tidewatch.ingestion.fake import FakeSource
from tidewatch.ingestion.pow_pearl import PowPearl

#: Sources that were replaced. Their System Health entries are archived (soft delete), and
#: the rows they stored are kept. `safetrade` was replaced by `coingecko` (PER-18).
RETIRED_SOURCES = ("safetrade",)


def test_controls_enabled() -> bool:
    """fake_source and its controls exist everywhere except production."""
    return os.environ.get("APP_ENV", "local") != "production"


def registered_adapters() -> list[Adapter]:
    adapters: list[Adapter] = [PowPearl(), CoinGecko(), CoinGeckoListings()]
    if test_controls_enabled():
        adapters.append(FakeSource())
    return adapters
