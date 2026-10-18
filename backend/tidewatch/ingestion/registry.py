"""Which adapters the worker runs. Real providers are added here from M1 onward."""

import os

from tidewatch.ingestion.base import Adapter
from tidewatch.ingestion.fake import FakeSource


def test_controls_enabled() -> bool:
    """fake_source and its controls exist everywhere except production."""
    return os.environ.get("APP_ENV", "local") != "production"


def registered_adapters() -> list[Adapter]:
    adapters: list[Adapter] = []
    if test_controls_enabled():
        adapters.append(FakeSource())
    return adapters
