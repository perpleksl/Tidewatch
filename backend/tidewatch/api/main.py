"""FastAPI application entry point.

Run locally with:  uv run uvicorn tidewatch.api.main:app --reload
"""

from fastapi import FastAPI

app = FastAPI(title="Tidewatch API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Public liveness check. The only route that does not require sign-in (CLAUDE.md §4)."""
    return {"status": "ok"}
