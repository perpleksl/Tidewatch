import pytest
from fastapi.testclient import TestClient

from tidewatch.api.main import allowed_origins, app

client = TestClient(app)


def test_local_dashboard_origin_is_allowed_by_default() -> None:
    """The local dashboard (http://localhost:5173) can call the API from a browser."""
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_unknown_origin_is_not_allowed() -> None:
    response = client.get("/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers


def test_allowed_origins_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://staging.example, https://app.example ,")

    assert allowed_origins() == ["https://staging.example", "https://app.example"]
