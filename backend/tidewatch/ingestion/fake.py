"""`fake_source`: a test adapter with synthetic data that can be told to misbehave (PER-13).

Its behaviour comes from `source_status.test_mode`, set from System Health on non-production
environments: None (normal), "fail", "rate_limit" or "invalid".
"""

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, ClassVar

from sqlalchemy.orm import Session

from tidewatch.db.models import IngestionTestRow
from tidewatch.ingestion.base import Adapter, RateLimited, SourceRecord, SourceUnavailable
from tidewatch.ingestion.runner import get_status, utc_now

#: How long a simulated rate limit lasts.
FAKE_PAUSE = timedelta(minutes=10)


class FakeRecord(SourceRecord):
    label: str
    value: Decimal


class FakeSource(Adapter):
    name: str = "fake_source"
    interval_setting: ClassVar[str] = "refresh.standard_minutes"
    record_model: ClassVar[type[SourceRecord]] = FakeRecord

    def __init__(self, name: str | None = None) -> None:
        if name is not None:
            self.name = name  # tests register two independent fakes

    def fetch(self, session: Session) -> Sequence[Any]:
        mode = get_status(session, self.name).test_mode
        now = utc_now()
        if mode == "fail":
            raise SourceUnavailable("simulated failure (test mode)")
        if mode == "rate_limit":
            raise RateLimited(resume_at=now + FAKE_PAUSE, message="simulated rate limit")
        if mode == "invalid":
            return [{"label": "synthetic", "value": "not-a-number", "observed_at": now}]
        observed = now.replace(second=0, microsecond=0)
        return [{"label": "synthetic", "value": str(observed.minute), "observed_at": observed}]

    def store(
        self, session: Session, records: Sequence[SourceRecord], available_at: datetime
    ) -> int:
        for record in records:
            if not isinstance(record, FakeRecord):
                raise TypeError("fake_source received a record of the wrong type")
            session.add(
                IngestionTestRow(
                    source=self.name,
                    observed_at=record.observed_at,
                    available_at=available_at,
                    label=record.label,
                    value=record.value,
                )
            )
        return len(records)
