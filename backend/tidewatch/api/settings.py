"""Settings API (PER-12): read every setting, change one, reset one, and the change log."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from tidewatch.api.auth import protected_router
from tidewatch.api.deps import get_session
from tidewatch.db.models import Setting
from tidewatch.db.settings import (
    SettingError,
    SettingSpec,
    all_settings,
    recent_changes,
    reset_setting,
    spec_for,
    update_setting,
)

router = protected_router()

DbSession = Annotated[Session, Depends(get_session)]


class SettingOut(BaseModel):
    key: str
    area: str
    label: str
    kind: str
    unit: str
    valid_range: str
    prd: str
    value: Any
    default_value: Any
    is_default: bool
    # Weights: the factor names in PRD order (the database does not keep key order).
    factors: list[str] | None = None


class SettingIn(BaseModel):
    value: Any


class ChangeOut(BaseModel):
    key: str
    label: str
    old_value: Any
    new_value: Any
    changed_at: datetime
    reason: str | None


def _out(spec: SettingSpec, row: Setting) -> SettingOut:
    return SettingOut(
        key=spec.key,
        area=spec.area,
        label=spec.label,
        kind=spec.kind,
        unit=spec.unit,
        valid_range=spec.valid_range,
        prd=spec.prd,
        value=row.value,
        default_value=spec.default,
        is_default=row.value == spec.default,
        factors=list(spec.default) if spec.kind == "weights" else None,
    )


def _known(key: str) -> SettingSpec:
    try:
        return spec_for(key)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown setting") from exc


@router.get("/settings")
def list_settings(db: DbSession) -> list[SettingOut]:
    return [_out(spec, row) for spec, row in all_settings(db)]


@router.put("/settings/{key}")
def change_setting(key: str, body: SettingIn, db: DbSession) -> SettingOut:
    spec = _known(key)
    try:
        row = update_setting(db, key, body.value)
    except SettingError as exc:
        # Nothing is saved: the request's transaction is rolled back with the error.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _out(spec, row)


@router.post("/settings/{key}/reset")
def reset_to_default(key: str, db: DbSession) -> SettingOut:
    spec = _known(key)
    try:
        row = reset_setting(db, key)
    except SettingError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _out(spec, row)


@router.get("/settings-changes")
def change_log(db: DbSession, limit: int = 100) -> list[ChangeOut]:
    return [
        ChangeOut(
            key=c.key,
            label=spec_for(c.key).label,
            old_value=c.old_value,
            new_value=c.new_value,
            changed_at=c.changed_at,
            reason=c.reason,
        )
        for c in recent_changes(db, limit=max(1, min(limit, 500)))
    ]
