"""Bearer-token authentication for the HTTP API.

Every protected request carries `Authorization: Bearer <jwt>`. The customer is the token's `sub`:
it never comes from the request body or from the model. Tokens are short-lived (a session that
expires is one of the failure cases the challenge asks to test).

Who issues tokens is a separate concern. Here `POST /api/auth/token` is a *test identity service*
that only serves listed demo customers (see http.py). In production it is replaced by the bank's
real identity provider; `customer_from_token` is what stays.
"""

from datetime import UTC, datetime, timedelta
from secrets import compare_digest
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

ALGORITHM = "HS256"  # pinned on decode: a token cannot choose its own algorithm (no "none")
ISSUER = "factored-demo-idp"
AUDIENCE = "factored-api"

bearer = HTTPBearer(auto_error=False, description="Token from POST /api/auth/token")


class AuthError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason  # "token_expired" | "invalid_token"


def issue_token(customer_id: str) -> tuple[str, int]:
    """A signed token for `customer_id` and its lifetime in seconds."""
    settings = get_settings()
    lifetime = timedelta(minutes=settings.access_token_ttl_minutes)
    now = datetime.now(UTC)
    claims = {"sub": customer_id, "iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + lifetime}
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM), int(
        lifetime.total_seconds()
    )


def customer_from_token(token: str) -> str:
    try:
        claims = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise AuthError("token_expired") from None
    except jwt.InvalidTokenError:
        raise AuthError("invalid_token") from None
    return claims["sub"]


def token_customer(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str | None:
    """FastAPI dependency: the customer proven by the token, or None when there is no token."""
    if credentials is None:
        return None
    try:
        return customer_from_token(credentials.credentials)
    except AuthError as error:
        raise HTTPException(
            401,
            detail=error.reason,
            headers={"WWW-Authenticate": f'Bearer error="{error.reason}"'},
        ) from None


def operator(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    """FastAPI dependency for the operator console: the bearer must be the shared OPERATOR_KEY."""
    key = get_settings().operator_key.encode()
    if credentials is None or not compare_digest(credentials.credentials.encode(), key):
        raise HTTPException(401, "Operator key required.", headers={"WWW-Authenticate": "Bearer"})
