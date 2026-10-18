"""FastAPI application entry point.

Run locally with:  uv run uvicorn tidewatch.api.main:app --reload

Sign-in is on by default: every route lives on a router made by `protected_router()`,
which requires a Clerk session token, and is listed in PROTECTED_ROUTERS. `/health` is the
only public route (CLAUDE.md §4). A test fails if a route is ever added without sign-in.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tidewatch.api import settings as settings_api
from tidewatch.api.auth import SignedInUser, protected_router, require_user
from tidewatch.api.origins import DEFAULT_ALLOWED_ORIGINS, allowed_origin_regex, allowed_origins

__all__ = ["DEFAULT_ALLOWED_ORIGINS", "allowed_origin_regex", "allowed_origins", "app"]

PUBLIC_PATHS = frozenset({"/health"})

# The interactive API docs (/docs, /redoc, /openapi.json) are switched off: the API is private.
app = FastAPI(
    title="Tidewatch API", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_origin_regex=allowed_origin_regex(),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

public = APIRouter()
protected = protected_router()

CurrentUser = Annotated[SignedInUser, Depends(require_user)]


@public.get("/health")
def health() -> dict[str, str]:
    """Public liveness check. The only route that does not require sign-in (CLAUDE.md §4)."""
    return {"status": "ok"}


@protected.get("/me")
def me(user: CurrentUser) -> dict[str, str]:
    """Who is signed in. Used to verify sign-in end to end (PER-10)."""
    return {"user_id": user.user_id}


PROTECTED_ROUTERS = (protected, settings_api.router)

app.include_router(public)
for _router in PROTECTED_ROUTERS:
    app.include_router(_router)
