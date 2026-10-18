"""Sign-in check for every API route except /health (PRD 3.1, ARCHITECTURE.md AD6).

The dashboard signs in with Clerk and sends the Clerk session token as
`Authorization: Bearer <token>`. This module verifies it with Clerk's official SDK.
No password, session or token-signing code lives here (PER-10 constraint).
"""

import logging
import os
from dataclasses import dataclass
from typing import Any

from clerk_backend_api.security.machine import get_token_type
from clerk_backend_api.security.types import (
    TokenType,
    TokenVerificationError,
    TokenVerificationErrorReason,
    VerifyTokenOptions,
)
from clerk_backend_api.security.verifytoken import verify_token_async
from fastapi import APIRouter, Depends, HTTPException, Request, status

from tidewatch.api.origins import is_allowed_origin

logger = logging.getLogger(__name__)

# Problems on our side (configuration, Clerk unreachable), not a bad token.
_SERVICE_ERRORS = {
    TokenVerificationErrorReason.SECRET_KEY_MISSING,
    TokenVerificationErrorReason.JWK_FAILED_TO_LOAD,
    TokenVerificationErrorReason.SERVER_ERROR,
}


@dataclass(frozen=True)
class SignedInUser:
    user_id: str
    session_id: str | None


def verify_options() -> VerifyTokenOptions:
    """How tokens are verified: Clerk's public keys, fetched using CLERK_SECRET_KEY."""
    return VerifyTokenOptions(secret_key=os.environ.get("CLERK_SECRET_KEY") or None)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def require_user(request: Request) -> SignedInUser:
    """FastAPI dependency: the request must carry a valid Clerk session token."""
    token = _bearer_token(request)
    if token is None:
        raise _unauthorized("Sign-in required")

    # Only browser session tokens are accepted; no API keys or machine tokens.
    if get_token_type(token) != TokenType.SESSION_TOKEN:
        raise _unauthorized("Sign-in required")

    try:
        claims: dict[str, Any] = await verify_token_async(token, verify_options())
    except TokenVerificationError as exc:
        if exc.reason in _SERVICE_ERRORS:
            logger.error("Sign-in check unavailable: %s", exc.reason.value[0])
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Sign-in check unavailable",
            ) from exc
        logger.info("Rejected session token: %s", exc.reason.value[0])
        raise _unauthorized("Sign-in required") from exc
    except Exception as exc:  # anything unexpected from token parsing is a bad token
        logger.info("Rejected session token: %s", type(exc).__name__)
        raise _unauthorized("Sign-in required") from exc

    # The token must have been issued to one of our own dashboards.
    azp = claims.get("azp")
    if not isinstance(azp, str) or not is_allowed_origin(azp):
        logger.info("Rejected session token: unknown dashboard origin")
        raise _unauthorized("Sign-in required")

    user_id = claims.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise _unauthorized("Sign-in required")

    session_id = claims.get("sid")
    return SignedInUser(
        user_id=user_id, session_id=session_id if isinstance(session_id, str) else None
    )


def protected_router() -> APIRouter:
    """A router whose every route requires sign-in. Use this for all new API routes."""
    return APIRouter(dependencies=[Depends(require_user)])
