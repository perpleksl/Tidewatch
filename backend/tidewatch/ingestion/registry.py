"""Which adapters the worker runs. Real providers are added here from M1 onward."""

import os

from tidewatch.ingestion.base import Adapter
from tidewatch.ingestion.coingecko import CoinGecko
from tidewatch.ingestion.coingecko_listings import CoinGeckoListings
from tidewatch.ingestion.coingecko_markets import CoinGeckoMarkets
from tidewatch.ingestion.defillama import DefiLlama, DefiLlamaHistory
from tidewatch.ingestion.fake import FakeSource
from tidewatch.ingestion.goplus import GoPlus
from tidewatch.ingestion.pow_pearl import PowPearl

#: Sources that were replaced. Their System Health entries are archived (soft delete), and
#: the rows they stored are kept. `safetrade` was replaced by `coingecko` (PER-18).
RETIRED_SOURCES = ("safetrade",)


def test_controls_enabled() -> bool:
    """fake_source and its controls exist everywhere except production."""
    return os.environ.get("APP_ENV", "local") != "production"


def registered_adapters() -> list[Adapter]:
    adapters: list[Adapter] = [
        PowPearl(),
        CoinGecko(),
        CoinGeckoListings(),
        # Order matters within one worker check: DefiLlama adds tokens, CoinGecko then prices
        # them, and GoPlus checks those whose market cap is in range.
        DefiLlama(),
        CoinGeckoMarkets(),
        GoPlus(),
        # Slow one-time backfill last, so it never delays the hourly updates above.
        DefiLlamaHistory(),
    ]
    if test_controls_enabled():
        adapters.append(FakeSource())
    return adapters
