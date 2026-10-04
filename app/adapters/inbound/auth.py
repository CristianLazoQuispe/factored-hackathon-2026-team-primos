"""Bearer-token authentication for the HTTP API.

Every protected request carries `Authorization: Bearer <jwt>`. The customer is the token's `sub`:
it never comes from the request body or from the model. Tokens are short-lived (a session that
expires is one of the failure cases the challenge asks to test).

`POST /api/auth/token` checks one of eight demo emails and its password, then signs that JWT.
In production the bank's identity provider replaces the check; `customer_from_token` is what stays.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from secrets import compare_digest
from time import monotonic
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

ALGORITHM = "HS256"  # pinned on decode: a token cannot choose its own algorithm (no "none")
ISSUER = "factored-demo-idp"
AUDIENCE = "factored-api"

bearer = HTTPBearer(auto_error=False, description="Token from POST /api/auth/token")

# Demo login: the password is the email itself. Hashed at import; the check compares digests.
# Salt is the email. The eight addresses are listed in the README. Not a column in the database.
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
_DEMO_CUSTOMERS = {
    "demo-mx-duplicate@demo.bank": "DEMO-MX-DUPLICATE",
    "demo-mx-fx@demo.bank": "DEMO-MX-FX",
    "demo-co-pending@demo.bank": "DEMO-CO-PENDING",
    "demo-br-portuguese@demo.bank": "DEMO-BR-PORTUGUESE",
    "demo-ar-fraud@demo.bank": "DEMO-AR-FRAUD",
    "demo-co-ambiguous@demo.bank": "DEMO-CO-AMBIGUOUS",
    "demo-mx-own-purchase@demo.bank": "DEMO-MX-OWN-PURCHASE",
    "demo-ar-reversed@demo.bank": "DEMO-AR-REVERSED",
}
_DUMMY_SALT = b"factored-demo-dummy"


def _digest(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)


_LOGINS = {
    email: (customer_id, _digest(email, email.encode()))
    for email, customer_id in _DEMO_CUSTOMERS.items()
}
_DUMMY_DIGEST = _digest("not-a-password", _DUMMY_SALT)

LOGIN_LIMIT = 8  # attempts kept per origin inside the window; the next one is refused
LOGIN_WINDOW_S = 60
ACCOUNT_FAILURES = 3  # wrong passwords for one email; the third locks that account
ACCOUNT_LOCK_S = 15 * 60
# N ≤ a handful of origins × 8 timestamps, and 8 demo emails.
# Origin → times in the last minute. Email → (failures, lock expiry); expiry 0 means not locked.
_login_attempts: dict[str, list[float]] = {}
_account_failures: dict[str, tuple[int, float]] = {}


def reset_login_attempts() -> None:
    _login_attempts.clear()
    _account_failures.clear()


def allow_login(origin: str) -> bool:
    """True when this origin still has an attempt left in the current minute."""
    now = monotonic()
    recent = [stamp for stamp in _login_attempts.get(origin, ()) if now - stamp < LOGIN_WINDOW_S]
    if len(recent) >= LOGIN_LIMIT:
        _login_attempts[origin] = recent
        return False
    recent.append(now)
    _login_attempts[origin] = recent
    return True


def account_locked(email: str) -> bool:
    """True when this demo email is inside its lock window."""
    _, locked_until = _account_failures.get(email.strip().lower(), (0, 0.0))
    return locked_until > monotonic()


def register_failure(email: str) -> bool:
    """Count a wrong password for a demo account. True when this attempt locks it.

    An email that is not one of the eight is ignored, so unknown addresses cannot fill the dict.
    """
    key = email.strip().lower()
    if key not in _LOGINS:
        return False
    failures, locked_until = _account_failures.get(key, (0, 0.0))
    now = monotonic()
    if locked_until > now:
        return True
    if locked_until:
        failures = 0  # the previous lock already expired
    failures += 1
    if failures >= ACCOUNT_FAILURES:
        _account_failures[key] = (failures, now + ACCOUNT_LOCK_S)
        return True
    _account_failures[key] = (failures, 0.0)
    return False


def clear_failures(email: str) -> None:
    _account_failures.pop(email.strip().lower(), None)


def customer_from_login(email: str, password: str) -> str | None:
    """The demo customer that email and password prove, or None when either is wrong.

    An unknown email still runs scrypt, so the answer does not arrive faster than a wrong password.
    """
    record = _LOGINS.get(email.strip().lower())
    salt = email.strip().lower().encode() if record else _DUMMY_SALT
    digest = _digest(password, salt)
    expected = record[1] if record else _DUMMY_DIGEST
    if record is None or not compare_digest(digest, expected):
        return None
    return record[0]


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
