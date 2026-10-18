"""Alembic environment for Tidewatch.

The database address comes from DATABASE_URL (never from alembic.ini). Tests can pass an
open connection through `config.attributes["connection"]` instead.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection

from tidewatch.db import models  # noqa: F401 - registers every table on Base.metadata
from tidewatch.db.base import Base
from tidewatch.db.session import database_url, make_engine

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Render the migration as SQL without connecting (alembic upgrade --sql)."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_with(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run_with(connection)
        return
    engine = make_engine()
    with engine.connect() as conn:
        _run_with(conn)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
