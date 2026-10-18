"""Which dashboard addresses may talk to the API.

Used twice: by CORS (which browsers may call the API) and by sign-in (which dashboard a
Clerk session token was issued for, its `azp` claim). Both read the same settings.
"""

import os
import re

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


def is_allowed_origin(origin: str) -> bool:
    """True if `origin` is one of the exact addresses or fully matches the pattern."""
    if origin in allowed_origins():
        return True
    pattern = allowed_origin_regex()
    return pattern is not None and re.fullmatch(pattern, origin) is not None
