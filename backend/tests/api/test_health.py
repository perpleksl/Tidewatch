from fastapi.testclient import TestClient

from tidewatch.api.main import app

client = TestClient(app)


def test_get_health_returns_200_with_status_ok() -> None:
    """PER-6 AC1: GET /health returns HTTP 200 with {"status": "ok"}."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "BROKEN ON PURPOSE"}


def test_health_requires_no_authentication() -> None:
    """/health is public: no auth header is needed (CLAUDE.md §4)."""
    response = client.get("/health", headers={})

    assert response.status_code == 200
