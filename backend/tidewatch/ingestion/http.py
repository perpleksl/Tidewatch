"""Shared HTTP helper for adapters: maps provider answers onto the framework's errors."""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from tidewatch.ingestion.base import RateLimited, SourceUnavailable

TIMEOUT_SECONDS = 20.0
#: Pause after a 429 without a Retry-After header (technical default).
DEFAULT_RATE_LIMIT_PAUSE = timedelta(minutes=15)
USER_AGENT = "Tidewatch/0.1 (private research dashboard)"


def get_json(url: str, http: httpx.Client | None = None, **params: Any) -> Any:
    client = http or httpx.Client(timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})
    try:
        response = client.get(url, params=params or None)
    except httpx.HTTPError as exc:
        raise SourceUnavailable(f"request failed: {type(exc).__name__}") from exc
    finally:
        if http is None:
            client.close()
    if response.status_code == 429:
        retry = response.headers.get("Retry-After", "")
        pause = timedelta(seconds=int(retry)) if retry.isdigit() else DEFAULT_RATE_LIMIT_PAUSE
        raise RateLimited(resume_at=datetime.now(UTC) + pause)
    if response.status_code != 200:
        raise SourceUnavailable(f"HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise SourceUnavailable("response was not JSON") from exc
