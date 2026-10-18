"""PER-13: ingestion framework. Each test names the acceptance criterion it proves."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from tidewatch.db.models import IngestionTestRow, SourceStatus
from tidewatch.db.settings import update_setting
from tidewatch.ingestion.base import Adapter, SourceRecord
from tidewatch.ingestion.fake import FakeSource
from tidewatch.ingestion.runner import (
    BACKOFF_SECONDS,
    errors_last_24h,
    get_status,
    run_adapter,
    run_due,
)

T0 = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def waits() -> list[float]:
    return []


def status(sessions: sessionmaker[Session], name: str) -> SourceStatus:
    with sessions() as s:
        row = get_status(s, name)
        s.expunge(row)
        return row


def set_mode(sessions: sessionmaker[Session], name: str, mode: str | None) -> None:
    with sessions.begin() as s:
        get_status(s, name).test_mode = mode


def rows(sessions: sessionmaker[Session], name: str = "fake_source") -> list[IngestionTestRow]:
    with sessions() as s:
        found = list(
            s.scalars(select(IngestionTestRow).where(IngestionTestRow.source == name)).all()
        )
        s.expunge_all()
        return found


def test_ac1_fetches_on_the_settings_interval_and_stores_point_in_time_fields(
    sessions: sessionmaker[Session], clock: Clock, waits: list[float]
) -> None:
    """AC1: the worker fetches on the Settings interval; rows get source, observed_at and
    available_at (available_at = when Tidewatch received the data)."""
    fake = FakeSource()
    assert run_due(sessions, [fake], clock, waits.append) == {"fake_source": "ok"}
    stored = rows(sessions)
    assert len(stored) == 1
    assert stored[0].source == "fake_source"
    assert stored[0].observed_at is not None
    assert stored[0].available_at == T0

    clock.advance(minutes=59)  # refresh.standard_minutes defaults to 60
    assert run_due(sessions, [fake], clock, waits.append) == {}
    clock.advance(minutes=1)
    assert run_due(sessions, [fake], clock, waits.append) == {"fake_source": "ok"}
    assert len(rows(sessions)) == 2


def test_ac2_three_failures_mark_the_source_degraded(
    sessions: sessionmaker[Session], clock: Clock, waits: list[float]
) -> None:
    """AC2: after failing 3 times in a row, the source is Degraded."""
    set_mode(sessions, "fake_source", "fail")
    assert run_adapter(sessions, FakeSource(), clock, waits.append) == "degraded"
    row = status(sessions, "fake_source")
    assert row.status == "degraded"
    assert errors_last_24h(row, clock()) == 3
    assert waits == list(BACKOFF_SECONDS)  # retried with backoff between attempts
    assert "simulated failure" in (row.last_error or "")
    assert rows(sessions) == []


def test_ac3_rate_limit_pauses_the_source_until_its_resume_time(
    sessions: sessionmaker[Session], clock: Clock, waits: list[float]
) -> None:
    """AC3: a rate-limit response marks the source Paused with a resume time."""
    set_mode(sessions, "fake_source", "rate_limit")
    assert run_adapter(sessions, FakeSource(), clock, waits.append) == "paused"
    row = status(sessions, "fake_source")
    assert row.status == "paused"
    assert row.paused_until is not None
    assert waits == []  # no retries against a limit

    set_mode(sessions, "fake_source", None)
    clock.now = row.paused_until - timedelta(seconds=1)
    assert run_due(sessions, [FakeSource()], clock, waits.append) == {}
    clock.now = row.paused_until
    assert run_due(sessions, [FakeSource()], clock, waits.append) == {"fake_source": "ok"}


def test_ac4_recovery_returns_to_ok_and_updates_last_success(
    sessions: sessionmaker[Session], clock: Clock, waits: list[float]
) -> None:
    """AC4: when the source recovers it is OK again and last successful fetch updates."""
    run_adapter(sessions, FakeSource(), clock, waits.append)
    first_success = status(sessions, "fake_source").last_success_at
    clock.advance(hours=1)
    set_mode(sessions, "fake_source", "fail")
    run_adapter(sessions, FakeSource(), clock, waits.append)
    assert status(sessions, "fake_source").status == "degraded"

    clock.advance(hours=1)
    set_mode(sessions, "fake_source", None)
    assert run_adapter(sessions, FakeSource(), clock, waits.append) == "ok"
    row = status(sessions, "fake_source")
    assert row.status == "ok"
    assert row.last_success_at == clock()
    assert row.last_success_at != first_success
    assert row.last_error is None


class BrokenAdapter(Adapter):
    """An adapter with a bug (raises something unexpected)."""

    name = "broken_source"
    interval_setting: ClassVar[str] = "refresh.standard_minutes"
    record_model: ClassVar[type[SourceRecord]] = SourceRecord

    def fetch(self, session: Session) -> Sequence[Any]:
        raise ZeroDivisionError("bug")

    def store(
        self, session: Session, records: Sequence[SourceRecord], available_at: datetime
    ) -> int:
        return 0


def test_ac5_one_failing_adapter_does_not_stop_another(
    sessions: sessionmaker[Session], clock: Clock, waits: list[float]
) -> None:
    """AC5: with two fake adapters, one failing, the other still runs and stores data."""
    failing, healthy = FakeSource("fake_a"), FakeSource("fake_b")
    set_mode(sessions, "fake_a", "fail")
    results = run_due(sessions, [failing, BrokenAdapter(), healthy], clock, waits.append)
    assert results == {"fake_a": "degraded", "broken_source": "degraded", "fake_b": "ok"}
    assert len(rows(sessions, "fake_b")) == 1
    assert rows(sessions, "fake_a") == []


def test_ac6_changing_the_interval_in_settings_changes_the_schedule(
    sessions: sessionmaker[Session], clock: Clock, waits: list[float]
) -> None:
    """AC6: changing refresh.standard_minutes changes the schedule without a redeploy."""
    run_due(sessions, [FakeSource()], clock, waits.append)
    clock.advance(minutes=10)
    assert run_due(sessions, [FakeSource()], clock, waits.append) == {}
    with sessions.begin() as s:
        update_setting(s, "refresh.standard_minutes", 5)
    assert run_due(sessions, [FakeSource()], clock, waits.append) == {"fake_source": "ok"}


def test_ac7_invalid_data_is_rejected_counted_and_not_stored(
    sessions: sessionmaker[Session], clock: Clock, waits: list[float]
) -> None:
    """AC7: invalid data fails Pydantic validation, counts as an error, and is not stored."""
    set_mode(sessions, "fake_source", "invalid")
    run_adapter(sessions, FakeSource(), clock, waits.append)
    row = status(sessions, "fake_source")
    assert rows(sessions) == []
    assert errors_last_24h(row, clock()) == 3
    assert "invalid data" in (row.last_error or "")


def test_run_now_makes_a_source_due_immediately(
    sessions: sessionmaker[Session], clock: Clock, waits: list[float]
) -> None:
    run_due(sessions, [FakeSource()], clock, waits.append)
    clock.advance(minutes=1)
    with sessions.begin() as s:
        get_status(s, "fake_source").run_requested_at = clock()
    assert run_due(sessions, [FakeSource()], clock, waits.append) == {"fake_source": "ok"}
    assert status(sessions, "fake_source").run_requested_at is None


def test_errors_older_than_24_hours_drop_out_of_the_count(
    sessions: sessionmaker[Session], clock: Clock, waits: list[float]
) -> None:
    set_mode(sessions, "fake_source", "fail")
    run_adapter(sessions, FakeSource(), clock, waits.append)
    clock.advance(hours=25)
    assert errors_last_24h(status(sessions, "fake_source"), clock()) == 0
    run_adapter(sessions, FakeSource(), clock, waits.append)
    assert errors_last_24h(status(sessions, "fake_source"), clock()) == 3


def test_test_rows_never_touch_real_tables(sessions: sessionmaker[Session], clock: Clock) -> None:
    from tidewatch.db.models import MarketSnapshot

    run_adapter(sessions, FakeSource(), clock, lambda _: None)
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(MarketSnapshot)) == 0
