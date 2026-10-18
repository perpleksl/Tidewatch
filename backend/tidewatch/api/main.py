"""FastAPI application entry point.

Run locally with:  uv run uvicorn tidewatch.api.main:app --reload
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

DEFAULT_ALLOWED_ORIGINS = "http://localhost:5173"


def allowed_origins() -> list[str]:
    """Exact dashboard addresses allowed to call the API from a browser.

    Read from CORS_ALLOWED_ORIGINS (comma-separated). Defaults to the local dev dashboard.
    """
    raw = os.environ.get("CORS_ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def allowed_origin_regex() -> str | None:
    """Pattern for dashboard addresses that change per deployment (Vercel preview links).

    Read from CORS_ALLOWED_ORIGIN_REGEX. Unset or empty means no pattern is allowed.
    """
    pattern = os.environ.get("CORS_ALLOWED_ORIGIN_REGEX", "").strip()
    return pattern or None


app = FastAPI(title="Tidewatch API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_origin_regex=allowed_origin_regex(),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Public liveness check. The only route that does not require sign-in (CLAUDE.md §4)."""
    return {"status": "ok"}
