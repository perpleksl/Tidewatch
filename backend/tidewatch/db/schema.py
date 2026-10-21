"""Is the database schema up to date with this code's migrations?

On Render the API applies migrations before its new version goes live (`preDeployCommand`),
but the worker deploys at the same moment and could start running new code against the old
schema (seen on 21 Oct 2026: `security_check` didn't exist yet for a minute after PR #36).
The worker therefore checks this before each run and waits while it's False.
"""

from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@lru_cache(maxsize=1)
def expected_heads() -> frozenset[str]:
    """The migration revision(s) this version of the code needs."""
    config = Config(str(ALEMBIC_INI))
    return frozenset(ScriptDirectory.from_config(config).get_heads())


def applied_heads(bind: Engine | Connection) -> frozenset[str]:
    if isinstance(bind, Connection):
        return frozenset(MigrationContext.configure(bind).get_current_heads())
    with bind.connect() as connection:
        return frozenset(MigrationContext.configure(connection).get_current_heads())


def schema_is_current(bind: Engine | Connection) -> bool:
    return applied_heads(bind) == expected_heads()
