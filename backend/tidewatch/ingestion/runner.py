"""Runs adapters: retry with backoff, rate-limit pauses, validation and health tracking.

PRD 3.3: a failing source is retried 3 times with backoff, then marked Degraded. A rate or
credit limit marks it Paused until the provider says it can resume. One source failing never
affects another (each run is isolated, ARCHITECTURE.md Section 5).
"""

import logging
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from tidewatch.db.models import SourceStatus
from tidewatch.db.settings import get_setting
from tidewatch.ingestion.base import Adapter, RateLimited, SourceRecord, SourceUnavailable

log = logging.getLogger("tidewatch.ingestion")

ATTEMPTS = 3
#: Waits between attempts, in seconds (technical choice, not a product threshold).
BACKOFF_SECONDS = (2.0, 4.0)
ERROR_WINDOW = timedelta(hours=24)

Clock = Callable[[], datetime]
Sleep = Callable[[float], None]


def utc_now() -> datetime:
    return datetime.now(UTC)


class InvalidData(Exception):  # noqa: N818
    """The source answered, but the records failed validation. Nothing is stored."""


def get_status(session: Session, source: str) -> SourceStatus:
    row = session.scalars(select(SourceStatus).where(SourceStatus.source == source)).one_or_none()
    if row is None:
        row = SourceStatus(source=source, status="ok", recent_errors=[])
        session.add(row)
        session.flush()
    return row


def errors_last_24h(row: SourceStatus, now: datetime) -> int:
    cutoff = now - ERROR_WINDOW
    return sum(1 for t in row.recent_errors or [] if datetime.fromisoformat(t) >= cutoff)


def _record_error(row: SourceStatus, now: datetime, message: str) -> None:
    cutoff = now - ERROR_WINDOW
    kept = [t for t in row.recent_errors or [] if datetime.fromisoformat(t) >= cutoff]
    row.recent_errors = [*kept, now.isoformat()]
    row.last_error = message[:500]


def is_due(session: Session, adapter: Adapter, now: datetime) -> bool:
    """True if the adapter should run now (interval from Settings, pauses, "Run now")."""
    row = get_status(session, adapter.name)
    if row.run_requested_at is not None:
        return True
    if row.status == "paused" and row.paused_until is not None and now < row.paused_until:
        return False
    if row.last_attempt_at is None:
        return True
    minutes = int(get_setting(session, adapter.interval_setting))
    return now >= row.last_attempt_at + timedelta(minutes=minutes)


def _validate(adapter: Adapter, raw: Sequence[Any]) -> list[SourceRecord]:
    try:
        return [adapter.record_model.model_validate(item) for item in raw]
    except ValidationError as exc:
        raise InvalidData(f"invalid data: {exc.error_count()} validation error(s)") from exc


def run_adapter(
    sessions: sessionmaker[Session],
    adapter: Adapter,
    clock: Clock = utc_now,
    sleep: Sleep = time.sleep,
) -> str:
    """Run one adapter once, with retries. Returns the resulting status."""
    with sessions.begin() as session:
        row = get_status(session, adapter.name)
        row.run_requested_at = None
        row.last_attempt_at = clock()

    last_message = ""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with sessions.begin() as session:
                raw = adapter.fetch(session)
            received_at = clock()  # point-in-time rule: when Tidewatch had the data
            records = _validate(adapter, raw)
            with sessions.begin() as session:
                count = adapter.store(session, records, received_at)
                row = get_status(session, adapter.name)
                row.status = "ok"
                row.paused_until = None
                row.last_success_at = received_at
                row.last_error = None
            log.info("%s: stored %d record(s)", adapter.name, count)
            return "ok"
        except RateLimited as exc:
            with sessions.begin() as session:
                row = get_status(session, adapter.name)
                row.status = "paused"
                row.paused_until = exc.resume_at
                _record_error(row, clock(), f"Paused — limit reached: {exc}")
            log.warning("%s: rate limited until %s", adapter.name, exc.resume_at.isoformat())
            return "paused"
        except (SourceUnavailable, InvalidData) as exc:
            last_message = str(exc) or type(exc).__name__
        except Exception as exc:  # an unexpected bug in one adapter must not stop the others
            last_message = f"{type(exc).__name__}: {exc}"
            log.exception("%s: unexpected error", adapter.name)

        with sessions.begin() as session:
            _record_error(get_status(session, adapter.name), clock(), last_message)
        log.warning("%s: attempt %d/%d failed: %s", adapter.name, attempt, ATTEMPTS, last_message)
        if attempt < ATTEMPTS:
            sleep(BACKOFF_SECONDS[attempt - 1])

    with sessions.begin() as session:
        get_status(session, adapter.name).status = "degraded"
    return "degraded"


def run_due(
    sessions: sessionmaker[Session],
    adapters: Sequence[Adapter],
    clock: Clock = utc_now,
    sleep: Sleep = time.sleep,
) -> dict[str, str]:
    """One scheduler check: run every adapter that is due. Each is isolated from the others."""
    results: dict[str, str] = {}
    for adapter in adapters:
        try:
            with sessions.begin() as session:
                due = is_due(session, adapter, clock())
            if due:
                results[adapter.name] = run_adapter(sessions, adapter, clock, sleep)
        except Exception:
            log.exception("%s: could not be scheduled", adapter.name)
            results[adapter.name] = "error"
    return results
