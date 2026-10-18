"""PER-12: the settings API, signed in with a test token, against a real database."""

from collections.abc import Iterator

import pytest
from clerk_backend_api.security.types import VerifyTokenOptions
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import tidewatch.api.auth as auth
from tidewatch.api.deps import get_session
from tidewatch.api.main import app
from tidewatch.db.settings import SPECS

from .test_auth import PUBLIC_PEM, bearer, make_token


@pytest.fixture
def api(session: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(auth, "verify_options", lambda: VerifyTokenOptions(jwt_key=PUBLIC_PEM))
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)

    def test_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = test_session
    with TestClient(app, headers=bearer(make_token())) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/settings"),
        ("PUT", "/settings/refresh.launches_minutes"),
        ("POST", "/settings/refresh.launches_minutes/reset"),
        ("GET", "/settings-changes"),
    ],
)
def test_ac8_settings_api_returns_401_without_sign_in(method: str, path: str) -> None:
    """AC8: the settings API returns 401 without sign-in."""
    with TestClient(app) as client:
        response = client.request(method, path, json={"value": 1})
    assert response.status_code == 401


def test_ac1_lists_every_key_with_its_default(api: TestClient) -> None:
    """AC1: every key is listed, with its default value."""
    items = api.get("/settings").json()
    assert [i["key"] for i in items] == [s.key for s in SPECS]
    by_key = {i["key"]: i for i in items}
    assert by_key["refresh.launches_minutes"]["default_value"] == 5
    assert by_key["refresh.launches_minutes"]["valid_range"] == "1–60"
    assert by_key["scoring.risk_weights"]["factors"][0] == "holder_concentration"
    assert all(i["is_default"] for i in items)


def test_ac2_change_is_returned_on_next_read(api: TestClient) -> None:
    """AC2: after saving, a fresh read (as after a page reload) shows the new value."""
    response = api.put("/settings/refresh.standard_minutes", json={"value": 30})
    assert response.status_code == 200
    assert response.json()["value"] == 30
    by_key = {i["key"]: i for i in api.get("/settings").json()}
    assert by_key["refresh.standard_minutes"]["value"] == 30
    assert by_key["refresh.standard_minutes"]["is_default"] is False


def test_ac3_reset_restores_default_and_logs_it(api: TestClient) -> None:
    """AC3: "Reset to default" restores the default and records the change."""
    api.put("/settings/code.low_activity_days", json={"value": 120})
    response = api.post("/settings/code.low_activity_days/reset")
    assert response.json()["value"] == 90
    log = api.get("/settings-changes").json()
    assert log[0]["key"] == "code.low_activity_days"
    assert log[0]["reason"] == "reset to default"


def test_ac4_out_of_range_returns_message_naming_the_range(api: TestClient) -> None:
    """AC4: -5 is rejected with a message naming the valid range; nothing is saved."""
    response = api.put("/settings/refresh.launches_minutes", json={"value": -5})
    assert response.status_code == 422
    assert response.json()["detail"] == "Enter a whole number from 1 to 60."
    assert api.get("/settings-changes").json() == []


def test_ac5_bad_weights_and_non_anthropic_professor_are_rejected(api: TestClient) -> None:
    """AC5: weights not summing to 1, and a non-Anthropic professor tier, are rejected."""
    weights = dict.fromkeys(
        ["valuation_gap", "fundamentals_momentum", "smart_wallet_accumulation", "narrative_fit"],
        "0.3",
    )
    r1 = api.put("/settings/scoring.opportunity_weights", json={"value": weights})
    assert r1.status_code == 422
    assert "add up to 1" in r1.json()["detail"]
    tier = {"provider": "surplus", "model": "claude-opus-5-5"}
    r2 = api.put("/settings/ai.tier.professor_synthesis", json={"value": tier})
    assert r2.status_code == 422
    assert "official Anthropic API" in r2.json()["detail"]


def test_ac6_change_log_shows_time_old_and_new_value(api: TestClient) -> None:
    """AC6: each saved change appears with time, old value and new value."""
    api.put("/settings/launches.min_x_mentions", json={"value": 4})
    entry = api.get("/settings-changes").json()[0]
    assert entry["key"] == "launches.min_x_mentions"
    assert entry["label"] == "Mentioned by at least"
    assert (entry["old_value"], entry["new_value"]) == (2, 4)
    assert entry["changed_at"].endswith(("Z", "+00:00"))


def test_unknown_setting_is_404(api: TestClient) -> None:
    assert api.put("/settings/made.up", json={"value": 1}).status_code == 404
    assert api.post("/settings/made.up/reset").status_code == 404
