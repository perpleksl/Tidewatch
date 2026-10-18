"""PER-13: System Health API (signed in with a test token, against a real database)."""

from collections.abc import Iterator

import pytest
from clerk_backend_api.security.types import VerifyTokenOptions
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import tidewatch.api.auth as auth
from tidewatch.api.deps import get_session
from tidewatch.api.main import app

from .test_auth import PUBLIC_PEM, bearer, make_token


@pytest.fixture
def api(session: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(auth, "verify_options", lambda: VerifyTokenOptions(jwt_key=PUBLIC_PEM))
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.setenv("APP_ENV", "staging")

    def test_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = test_session
    with TestClient(app, headers=bearer(make_token())) as client:
        yield client
    app.dependency_overrides.clear()


def test_system_health_requires_sign_in() -> None:
    with TestClient(app) as client:
        assert client.get("/system-health").status_code == 401
        assert client.post("/system-health/fake_source/run").status_code == 401
        test_mode = client.post("/system-health/fake_source/test-mode", json={"mode": "fail"})
        assert test_mode.status_code == 401


def test_lists_fake_source_with_status_last_success_and_error_count(api: TestClient) -> None:
    body = api.get("/system-health").json()
    assert body["test_controls"] is True
    fake = next(s for s in body["sources"] if s["source"] == "fake_source")
    assert fake["status"] == "ok"
    assert fake["last_success_at"] is None
    assert fake["errors_24h"] == 0


def test_test_mode_and_run_now_are_recorded(api: TestClient) -> None:
    response = api.post("/system-health/fake_source/test-mode", json={"mode": "fail"})
    assert response.json()["test_mode"] == "fail"
    assert api.post("/system-health/fake_source/run").json()["run_requested"] is True
    back = api.post("/system-health/fake_source/test-mode", json={"mode": "normal"})
    assert back.json()["test_mode"] is None


def test_unknown_mode_and_source_are_refused(api: TestClient) -> None:
    assert api.post("/system-health/fake_source/test-mode", json={"mode": "x"}).status_code == 422
    assert api.post("/system-health/nansen/run").status_code == 404


def test_production_has_no_fake_source_and_no_test_controls(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    body = api.get("/system-health").json()
    assert body["test_controls"] is False
    assert all(s["source"] != "fake_source" for s in body["sources"])
    assert (
        api.post("/system-health/fake_source/test-mode", json={"mode": "fail"}).status_code == 404
    )
