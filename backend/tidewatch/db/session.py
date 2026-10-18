"""Database connection setup. The address comes from the DATABASE_URL environment variable."""

import os

from sqlalchemy import Engine, create_engine


def normalise_url(url: str) -> str:
    """Use the psycopg 3 driver for plain `postgres://` addresses (the form Render gives)."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return normalise_url(url)


def make_engine(url: str | None = None) -> Engine:
    """Create an engine whose sessions always run in UTC (CLAUDE.md: all times stored in UTC)."""
    return create_engine(
        normalise_url(url) if url else database_url(),
        pool_pre_ping=True,
        connect_args={"options": "-c timezone=UTC"},
    )
