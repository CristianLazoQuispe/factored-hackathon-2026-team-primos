"""Bearer-token authentication for the HTTP API.

Every protected request carries `Authorization: Bearer <jwt>`. The customer is the token's `sub`:
it never comes from the request body or from the model. Tokens are short-lived (a session that
expires is one of the failure cases the challenge asks to test).

`POST /api/auth/token` checks a demo login and its password, then signs that JWT. A login is the ID
of a customer in DEMO_CUSTOMER_IDS (the password is that same ID) or one of eight demo emails.
A `*` in DEMO_CUSTOMER_IDS lets the ID of any customer in the database sign in the same way.
In production the bank's identity provider replaces the check; `customer_from_token` is what stays.
"""

import hashlib
import re
from datetime import UTC, datetime, timedelta
from functools import lru_cache
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

# Demo login: the password is the login itself, an email or a customer ID. The emails are hashed at
# import; the check compares digests. Salt is the login. The eight addresses are listed in the
# README. Not a column in the database.
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
ANY_CUSTOMER = "*"  # in DEMO_CUSTOMER_IDS: the ID of every customer in the database can sign in
_CUSTOMER_ID = re.compile(r"(?:cli|demo)-[a-z0-9-]+")


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
# N ≤ a handful of origins × 8 timestamps, and one entry per demo login (the 8 emails and the
# IDs in DEMO_CUSTOMER_IDS).
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


def _demo_ids() -> dict[str, str]:
    """The IDs that can sign in (DEMO_CUSTOMER_IDS): lower-cased ID -> the ID as it is listed."""
    ids = get_settings().demo_customer_ids.split(",")
    return {i.strip().lower(): i.strip() for i in ids if i.strip() not in ("", ANY_CUSTOMER)}


@lru_cache(maxsize=256)
def _id_digest(customer_id: str) -> bytes:
    """What the password of an ID must hash to: the ID itself, in capitals, salted with the ID."""
    return _digest(customer_id.upper(), customer_id.lower().encode())


def account_locked(login: str) -> bool:
    """True when this demo login is inside its lock window."""
    _, locked_until = _account_failures.get(login.strip().lower(), (0, 0.0))
    return locked_until > monotonic()


def register_failure(login: str) -> bool:
    """Count a wrong password for a demo account. True when this attempt locks it.

    A login that is not one of the eight emails or a listed ID is ignored, so unknown names
    cannot fill the dict.
    """
    key = login.strip().lower()
    if key not in _LOGINS and key not in _demo_ids():
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


def clear_failures(login: str) -> None:
    _account_failures.pop(login.strip().lower(), None)


def customer_from_login(login: str, password: str) -> str | None:
    """The demo customer that this login and password prove, or None when either is wrong.

    A login is a demo email (the password is that email) or an ID listed in DEMO_CUSTOMER_IDS (the
    password is that ID, in any case). An unknown login still runs scrypt, so the answer does not
    arrive faster than a wrong password.
    """
    key = login.strip().lower()
    ids = _demo_ids()
    if key in _LOGINS:
        customer, expected = _LOGINS[key]
        given = _digest(password, key.encode())
    elif key in ids:
        customer = ids[key]
        expected, given = _id_digest(customer), _digest(password.strip().upper(), key.encode())
    else:
        customer, expected, given = None, _DUMMY_DIGEST, _digest(password, _DUMMY_SALT)
    if customer is None or not compare_digest(given, expected):
        return None
    return customer


def claimed_customer(login: str, password: str) -> str | None:
    """With `*` in DEMO_CUSTOMER_IDS: the customer ID this login names, when the password is that
    same ID. It proves nothing about the database: the caller checks that the customer exists."""
    key = login.strip().lower()
    listed = (i.strip() for i in get_settings().demo_customer_ids.split(","))
    if ANY_CUSTOMER not in listed or not _CUSTOMER_ID.fullmatch(key):
        return None
    given = _digest(password.strip().upper(), key.encode())
    return key.upper() if compare_digest(given, _id_digest(key)) else None


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
