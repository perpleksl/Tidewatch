"""Declarative base and shared column conventions (ARCHITECTURE.md AD3, Section 4).

Conventions every table follows:
- `id`: UUID primary key.
- `created_at`: when the row was written (UTC).
- `archived_at`: soft delete. Nothing is hard-deleted (CLAUDE.md Section 7, rule 3).
- Money, prices and amounts: `Decimal` stored as PostgreSQL `numeric` with no fixed
  precision, so values like 0.000002202006771721795 round-trip exactly.
- Times: `timestamptz`; the connection runs in UTC, so values read back in UTC.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, MetaData, Numeric, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Stable constraint names, so Alembic migrations are predictable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

JsonValue = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {  # noqa: RUF012 - SQLAlchemy reads this class attribute
        Decimal: Numeric(asdecimal=True),
        datetime: DateTime(timezone=True),
        dict[str, Any]: JsonValue,
        uuid.UUID: Uuid(),
    }


class TableMixin:
    """Columns every Tidewatch table has."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(default=None)
