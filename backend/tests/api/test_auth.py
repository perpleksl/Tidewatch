"""PER-10: sign-in on the API. Each test names the acceptance criterion it proves.

Tokens here are signed by a throwaway test key, and the API is pointed at that key's public
half, so the real Clerk SDK verification path runs without contacting Clerk.
"""

import time
from collections.abc import Iterator
from typing import Any

import jwt
import pytest
from clerk_backend_api.security.types import VerifyTokenOptions
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import tidewatch.api.auth as auth
from tidewatch.api.main import PUBLIC_PATHS, app, protected

DASHBOARD = "http://localhost:5173"


def _keypair() -> tuple[Any, str]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private, public_pem


SIGNING_KEY, PUBLIC_PEM = _keypair()
OTHER_KEY, _ = _keypair()


def make_token(key: Any = None, **claims: Any) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": "user_TEST123",
        "sid": "sess_TEST123",
        "azp": DASHBOARD,
        "iat": now,
        "nbf": now,
        "exp": now + 60,
    }
    payload.update(claims)
    payload = {k: v for k, v in payload.items() if v is not None}
    return jwt.encode(payload, key or SIGNING_KEY, algorithm="RS256", headers={"kid": "test"})


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(auth, "verify_options", lambda: VerifyTokenOptions(jwt_key=PUBLIC_PEM))
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_ALLOWED_ORIGIN_REGEX", raising=False)
    with TestClient(app) as c:
        yield c


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- AC4 -------------------------------------------------------------------------------


def test_ac4_me_without_token_returns_401(client: TestClient) -> None:
    """AC4: GET /me without a session token returns HTTP 401."""
    response = client.get("/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_ac4_me_with_valid_token_returns_200_and_user_id(client: TestClient) -> None:
    """AC4: with a valid token, GET /me returns 200 and the user ID."""
    response = client.get("/me", headers=bearer(make_token()))
    assert response.status_code == 200
    assert response.json() == {"user_id": "user_TEST123"}


@pytest.mark.parametrize(
    ("label", "headers"),
    [
        ("expired", bearer(make_token(exp=int(time.time()) - 600, iat=int(time.time()) - 900))),
        ("signed by another key", bearer(make_token(key=OTHER_KEY))),
        ("issued to another site", bearer(make_token(azp="https://evil.example"))),
        ("no azp claim", bearer(make_token(azp=None))),
        ("no user id", bearer(make_token(sub=None))),
        ("not a JWT", bearer("not-a-token")),
        ("API key instead of session", bearer("ak_TEST")),
        ("machine token instead of session", bearer("mt_TEST")),
        ("wrong scheme", {"Authorization": f"Basic {make_token()}"}),
        ("empty bearer", {"Authorization": "Bearer "}),
    ],
)
def test_ac4_me_rejects_invalid_tokens_with_401(
    client: TestClient, label: str, headers: dict[str, str]
) -> None:
    """AC4 (supporting): anything but a valid session token for our dashboard gets 401."""
    response = client.get("/me", headers=headers)
    assert response.status_code == 401, label


def test_ac4_token_from_preview_dashboard_is_accepted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC4 (supporting): tokens issued to a Vercel preview matching the pattern are accepted."""
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGIN_REGEX", r"https://tidewatch-[a-z0-9-]+-test\.vercel\.app"
    )
    token = make_token(azp="https://tidewatch-git-feat-x-test.vercel.app")
    assert client.get("/me", headers=bearer(token)).status_code == 200
    lookalike = make_token(azp="https://tidewatch-git-feat-x-test.vercel.app.evil.example")
    assert client.get("/me", headers=bearer(lookalike)).status_code == 401


def test_missing_secret_key_returns_503_not_200(monkeypatch: pytest.MonkeyPatch) -> None:
    """Misconfiguration fails closed: without CLERK_SECRET_KEY nothing gets through."""
    monkeypatch.delenv("CLERK_SECRET_KEY", raising=False)
    with TestClient(app) as c:
        response = c.get("/me", headers=bearer(make_token()))
    assert response.status_code == 503


# --- AC5 -------------------------------------------------------------------------------


def test_ac5_health_stays_public(client: TestClient) -> None:
    """AC5: GET /health stays public and returns 200 without a token."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- AC6 -------------------------------------------------------------------------------


def _depends_on_require_user(dependant: Dependant) -> bool:
    return any(
        dep.call is auth.require_user or _depends_on_require_user(dep)
        for dep in dependant.dependencies
    )


def _served_endpoints() -> list[tuple[str, str]]:
    """Every (method, path) the app actually serves, from FastAPI's public route schema.

    The schema is generated even though /openapi.json itself is not published.
    """
    app.openapi_schema = None  # rebuild, in case routes were added since
    paths: dict[str, dict[str, Any]] = app.openapi()["paths"]
    return [(method.upper(), path) for path, ops in paths.items() for method in ops]


def test_ac6_every_route_except_health_requires_sign_in() -> None:
    """AC6: every registered API route except /health requires authentication.

    Each served endpoint must be either /health or declared on the `protected` router,
    whose routes all depend on the sign-in check.
    """
    served = _served_endpoints()
    assert ("GET", "/health") in served
    assert ("GET", "/me") in served

    protected_paths = {r.path for r in protected.routes if isinstance(r, APIRoute)}
    for route in protected.routes:
        assert isinstance(route, APIRoute)
        assert _depends_on_require_user(route.dependant) or any(
            getattr(d, "dependency", None) is auth.require_user for d in protected.dependencies
        ), route.path

    unprotected = [
        f"{method} {path}"
        for method, path in served
        if path not in PUBLIC_PATHS and path not in protected_paths
    ]
    assert unprotected == [], f"Routes without sign-in: {unprotected}"


def test_ac6_every_route_except_health_answers_401_without_token(client: TestClient) -> None:
    """AC6: checked by calling each served route too, not only by inspecting it."""
    checked = 0
    for method, path in _served_endpoints():
        if path in PUBLIC_PATHS:
            continue
        response = client.request(method, path.replace("{", "").replace("}", ""))
        assert response.status_code == 401, f"{method} {path}"
        checked += 1
    assert checked >= 1  # guards against a test that silently checks nothing


def test_ac6_only_health_is_public() -> None:
    """AC6 (supporting): the public list is exactly /health."""
    assert frozenset({"/health"}) == PUBLIC_PATHS


def test_api_docs_are_not_exposed(client: TestClient) -> None:
    """The private API does not publish its schema or docs pages."""
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path
