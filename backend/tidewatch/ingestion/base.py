"""The common interface every data source implements (ARCHITECTURE.md Section 6).

An adapter only knows how to *fetch* raw records, which Pydantic model they must match, and
how to *store* validated records. Retries, rate limits, timing and health tracking are
handled for every adapter alike by `tidewatch.ingestion.runner`.

Point-in-time rule (ARCHITECTURE.md Section 4): each stored row carries
- `observed_at`: the moment the data describes (from the record itself), and
- `available_at`: the moment Tidewatch received it (set by the runner, never by the source).
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime
from typing import Any, ClassVar

from pydantic import AwareDatetime, BaseModel
from sqlalchemy.orm import Session


class SourceRecord(BaseModel):
    """Base for every adapter's record model. `observed_at` must include a time zone."""

    observed_at: AwareDatetime


class SourceUnavailable(Exception):  # noqa: N818 - reads naturally at the raise site
    """A temporary failure (network error, server error). The runner retries."""


class RateLimited(Exception):  # noqa: N818
    """The provider refused because a rate or credit limit was reached."""

    def __init__(self, resume_at: datetime, message: str = "limit reached") -> None:
        super().__init__(message)
        self.resume_at = resume_at


class Adapter(ABC):
    """One data source. Subclasses set the class attributes and implement fetch/store."""

    #: Stored on every row as `source` and used as the key on System Health.
    name: str
    #: The Settings key holding this source's refresh interval in minutes (`refresh.*`).
    interval_setting: ClassVar[str]
    #: The Pydantic model each raw record must match before anything is stored.
    record_model: ClassVar[type[SourceRecord]]

    @abstractmethod
    def fetch(self, session: Session) -> Sequence[Any]:
        """Return raw records. Raise SourceUnavailable or RateLimited on failure.

        `session` is for reading settings or control state only; don't write data here.
        """

    @abstractmethod
    def store(
        self, session: Session, records: Sequence[SourceRecord], available_at: datetime
    ) -> int:
        """Save validated records with source, observed_at and available_at. Return the count."""
