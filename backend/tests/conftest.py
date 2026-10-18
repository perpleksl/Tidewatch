"""Database test fixtures.

Tests run against a real PostgreSQL database named by TEST_DATABASE_URL (CI provides one).
The schema is rebuilt from the Alembic migrations, and every test runs inside a transaction
that is rolled back, so tests never see each other's rows.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, text
from sqlalchemy.orm import Session, sessionmaker

from tidewatch.db.session import make_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config(connection: Connection) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["connection"] = connection
    config.attributes["configure_logger"] = False
    return config


def reset_schema(connection: Connection) -> None:
    """Drop everything in the throwaway test database and start empty."""
    connection.execute(text("DROP SCHEMA public CASCADE"))
    connection.execute(text("CREATE SCHEMA public"))
    connection.commit()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        if os.environ.get("CI"):
            pytest.fail("TEST_DATABASE_URL must be set in CI")
        pytest.skip("TEST_DATABASE_URL not set; database tests need PostgreSQL")
    eng = make_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def migrated(engine: Engine) -> Engine:
    """An empty database with the migrations applied once for the whole test run."""
    with engine.connect() as conn:
        reset_schema(conn)
        command.upgrade(alembic_config(conn), "head")
        conn.commit()
    return engine


@pytest.fixture
def session(migrated: Engine) -> Iterator[Session]:
    with migrated.connect() as conn:
        trans = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield db
        finally:
            db.close()
            trans.rollback()


@pytest.fixture
def sessions(migrated: Engine) -> Iterator[sessionmaker[Session]]:
    """A session factory (as the worker uses) whose writes are all rolled back afterwards."""
    with migrated.connect() as conn:
        trans = conn.begin()
        try:
            yield sessionmaker(bind=conn, join_transaction_mode="create_savepoint")
        finally:
            trans.rollback()
