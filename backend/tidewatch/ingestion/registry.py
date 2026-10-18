"""Which adapters the worker runs. Real providers are added here from M1 onward."""

import os

from tidewatch.ingestion.base import Adapter
from tidewatch.ingestion.fake import FakeSource
from tidewatch.ingestion.pow_pearl import PowPearl
from tidewatch.ingestion.safetrade import SafeTrade


def test_controls_enabled() -> bool:
    """fake_source and its controls exist everywhere except production."""
    return os.environ.get("APP_ENV", "local") != "production"


def registered_adapters() -> list[Adapter]:
    adapters: list[Adapter] = [PowPearl(), SafeTrade()]
    if test_controls_enabled():
        adapters.append(FakeSource())
    return adapters
