import importlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

import tidewatch.api.main as main_module
from tidewatch.api.main import allowed_origin_regex, allowed_origins, app

client = TestClient(app)

PREVIEW_REGEX = r"https://tidewatch-[a-z0-9-]+-perpleksl\.vercel\.app"


@pytest.fixture
def app_with_preview_regex(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Rebuild the app with a preview-URL pattern configured, then restore the default app."""
    monkeypatch.setenv("CORS_ALLOWED_ORIGIN_REGEX", PREVIEW_REGEX)
    reloaded = importlib.reload(main_module)
    yield TestClient(reloaded.app)
    monkeypatch.delenv("CORS_ALLOWED_ORIGIN_REGEX")
    importlib.reload(main_module)


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


def test_origin_regex_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ALLOWED_ORIGIN_REGEX", raising=False)

    assert allowed_origin_regex() is None


def test_vercel_preview_origin_allowed_when_regex_set(
    app_with_preview_regex: TestClient,
) -> None:
    """PER-8: preview dashboards (changing Vercel URLs) can reach the staging API."""
    origin = "https://tidewatch-git-feat-per-8-abc123-perpleksl.vercel.app"
    response = app_with_preview_regex.get("/health", headers={"Origin": origin})

    assert response.headers.get("access-control-allow-origin") == origin


def test_lookalike_origin_rejected_when_regex_set(app_with_preview_regex: TestClient) -> None:
    response = app_with_preview_regex.get(
        "/health",
        headers={"Origin": "https://tidewatch-evil-perpleksl.vercel.app.attacker.example"},
    )

    assert "access-control-allow-origin" not in response.headers
