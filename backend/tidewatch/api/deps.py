"""Shared request dependencies."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from tidewatch.db.session import make_engine


@lru_cache(maxsize=1)
def _engine() -> Engine:
    return make_engine()


def get_session() -> Iterator[Session]:
    """One database session per request; committed if the request succeeds."""
    with Session(_engine()) as session, session.begin():
        yield session
