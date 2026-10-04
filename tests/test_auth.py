"""Bearer-token authentication: the token, the endpoints that use it, and what must be refused."""

import base64
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound import http
from app.adapters.inbound.auth import (
    ALGORITHM,
    AUDIENCE,
    ISSUER,
    AuthError,
    customer_from_token,
    issue_token,
    reset_login_attempts,
)
from app.config import get_settings

SECRET = "s" * 40


@pytest.fixture
def cloud(monkeypatch):
    """The deployed configuration: real signing key, demo allowlist, no local shortcuts."""
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "cloud")
    monkeypatch.setattr(settings, "jwt_secret", SECRET)
    monkeypatch.setattr(settings, "demo_customer_ids", "CLI-A, CLI-B")
    return settings


@pytest.fixture
def seen(monkeypatch):
    """Replace the agent: records what the API passes to it."""
    calls = []

    async def fake_reply(message, thread_key, customer_id, image=None):
        calls.append({"thread": thread_key, "customer": customer_id, "image": image})
        return {
            "reply": "ok",
            "customer_id": customer_id,
            "skill": None,
            "tools_used": [],
            "handoff": None,
        }

    monkeypatch.setattr(http, "reply", fake_reply)
    return calls


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def forged(**changes) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": "CLI-A",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    return jwt.encode({**claims, **changes}, SECRET, algorithm=ALGORITHM)


# ---- the token itself ----


def test_a_token_proves_the_customer_it_was_issued_for(cloud):
    token, expires_in = issue_token("CLI-A")
    assert customer_from_token(token) == "CLI-A" and expires_in == 15 * 60


def test_an_expired_token_is_refused_as_expired(cloud, monkeypatch):
    monkeypatch.setattr(cloud, "access_token_ttl_minutes", -1)
    token, _ = issue_token("CLI-A")
    with pytest.raises(AuthError) as error:
        customer_from_token(token)
    assert error.value.reason == "token_expired"


@pytest.mark.parametrize(
    "token",
    [
        jwt.encode({"sub": "CLI-A"}, "another-secret-" + "k" * 30, algorithm=ALGORITHM),
        jwt.encode({"sub": "CLI-A"}, key=None, algorithm="none"),  # unsigned
        "not-a-token",
        "",
    ],
    ids=["wrong-key", "unsigned", "garbage", "empty"],
)
def test_forged_or_malformed_tokens_are_refused(cloud, token):
    with pytest.raises(AuthError) as error:
        customer_from_token(token)
    assert error.value.reason == "invalid_token"


@pytest.mark.parametrize("changes", [{"aud": "someone-else"}, {"iss": "someone-else"}])
def test_a_token_meant_for_another_service_is_refused(cloud, changes):
    with pytest.raises(AuthError):
        customer_from_token(forged(**changes))


def test_a_token_without_expiry_or_subject_is_refused(cloud):
    no_exp = jwt.encode(
        {"sub": "CLI-A", "iss": ISSUER, "aud": AUDIENCE}, SECRET, algorithm=ALGORITHM
    )
    with pytest.raises(AuthError):
        customer_from_token(no_exp)


# ---- POST /api/auth/token: email, password, then the same bearer token ----

LUCIA_EMAIL = "demo-mx-duplicate@demo.bank"
LUCIA = {"email": LUCIA_EMAIL, "password": LUCIA_EMAIL}


@pytest.fixture(autouse=True)
def fresh_login_window():
    reset_login_attempts()


def test_the_right_password_issues_a_token_for_that_customer(cloud):
    with TestClient(http.app) as client:
        ok = client.post("/api/auth/token", json=LUCIA)
    assert ok.status_code == 200 and ok.json()["token_type"] == "bearer"
    assert ok.json()["customer_id"] == "DEMO-MX-DUPLICATE"
    assert customer_from_token(ok.json()["access_token"]) == "DEMO-MX-DUPLICATE"


@pytest.mark.parametrize(
    "body",
    [
        {"email": LUCIA_EMAIL, "password": "no"},
        {"email": "nadie@demo.bank", "password": "nadie@demo.bank"},
    ],
    ids=["wrong-password", "unknown-email"],
)
def test_a_wrong_email_or_password_is_refused_the_same_way(cloud, seen, body):
    with TestClient(http.app) as client:
        refused = client.post("/api/auth/token", json=body)
        chat = client.post("/api/chat", json={"message": "hola"})
    assert refused.status_code == 401
    assert refused.json()["detail"] == "Correo o contraseña incorrectos."
    assert chat.status_code == 401 and seen == []


def test_the_ninth_login_attempt_in_a_minute_is_refused(cloud):
    wrong = {"email": "nadie@demo.bank", "password": "no"}
    with TestClient(http.app) as client:
        for _ in range(8):
            assert client.post("/api/auth/token", json=wrong).status_code == 401
        blocked = client.post("/api/auth/token", json=wrong)
    assert blocked.status_code == 429


def test_three_wrong_passwords_lock_that_account_and_leave_the_others_open(cloud):
    wrong = {"email": LUCIA_EMAIL, "password": "no"}
    other = {"email": "demo-mx-fx@demo.bank", "password": "demo-mx-fx@demo.bank"}
    with TestClient(http.app) as client:
        for _ in range(2):
            assert client.post("/api/auth/token", json=wrong).status_code == 401
        locked = client.post("/api/auth/token", json=wrong)
        still = client.post("/api/auth/token", json=LUCIA)
        sibling = client.post("/api/auth/token", json=other)
    assert locked.status_code == 423 and still.status_code == 423
    assert sibling.status_code == 200


def test_a_successful_login_clears_the_failures_before_the_lock(cloud):
    wrong = {"email": LUCIA_EMAIL, "password": "no"}
    with TestClient(http.app) as client:
        for _ in range(2):
            assert client.post("/api/auth/token", json=wrong).status_code == 401
        assert client.post("/api/auth/token", json=LUCIA).status_code == 200
        # The next miss is the first again. A success that did not
        # clear the count would lock the account here.
        assert client.post("/api/auth/token", json=wrong).status_code == 401


# ---- POST /api/chat ----


def test_the_cloud_refuses_chat_without_a_token(cloud, seen):
    with TestClient(http.app) as client:
        response = client.post("/api/chat", json={"message": "hola", "customer_id": "CLI-A"})
    assert response.status_code == 401 and "Bearer" in response.headers["www-authenticate"]
    assert seen == []  # the agent never ran: a customer number alone proves nothing


def test_the_customer_comes_from_the_token_not_from_the_body(cloud, seen):
    token, _ = issue_token("CLI-A")
    with TestClient(http.app) as client:
        ok = client.post("/api/chat", json={"message": "hola"}, headers=bearer(token))
        clash = client.post(
            "/api/chat", json={"message": "hola", "customer_id": "CLI-B"}, headers=bearer(token)
        )
    assert ok.status_code == 200 and seen[0]["customer"] == "CLI-A"
    assert (
        clash.status_code == 403 and len(seen) == 1
    )  # asking for B with A's token never reaches the agent


def test_expired_and_forged_tokens_get_401_not_a_chat(cloud, seen):
    expired = forged(exp=datetime.now(UTC) - timedelta(minutes=1))
    with TestClient(http.app) as client:
        a = client.post("/api/chat", json={"message": "hola"}, headers=bearer(expired))
        b = client.post("/api/chat", json={"message": "hola"}, headers=bearer("forged.token.here"))
    assert a.status_code == 401 and a.json()["detail"] == "token_expired"
    assert b.status_code == 401 and b.json()["detail"] == "invalid_token"
    assert seen == []


def test_two_customers_never_share_a_conversation_even_with_the_same_thread_id(cloud, seen):
    with TestClient(http.app) as client:
        for customer in ("CLI-A", "CLI-B"):
            token, _ = issue_token(customer)
            response = client.post(
                "/api/chat", json={"message": "hola", "thread_id": "t1"}, headers=bearer(token)
            )
            assert response.json()["thread_id"] == "t1"  # the client still sees its own id
    assert [c["thread"] for c in seen] == ["CLI-A:t1", "CLI-B:t1"]


def test_locally_chat_still_works_without_a_token_using_the_body(monkeypatch, seen):
    monkeypatch.setattr(get_settings(), "app_env", "local")
    with TestClient(http.app) as client:
        response = client.post("/api/chat", json={"message": "hola", "customer_id": "DEMO-MX-FX"})
    assert response.status_code == 200 and seen[0]["customer"] == "DEMO-MX-FX"


@pytest.mark.parametrize(
    ("email", "customer"),
    [
        ("demo-co-ambiguous@demo.bank", "DEMO-CO-AMBIGUOUS"),
        ("demo-mx-own-purchase@demo.bank", "DEMO-MX-OWN-PURCHASE"),
        ("demo-ar-reversed@demo.bank", "DEMO-AR-REVERSED"),
    ],
)
def test_the_other_demo_cases_can_sign_in(cloud, email, customer):
    with TestClient(http.app) as client:
        ok = client.post("/api/auth/token", json={"email": email, "password": email})
    assert ok.status_code == 200 and ok.json()["customer_id"] == customer


def test_a_photo_reaches_the_agent(cloud, seen):
    token, _ = issue_token("CLI-A")
    png = base64.b64encode(b"\x89PNG\r\n").decode()
    with TestClient(http.app) as client:
        ok = client.post(
            "/api/chat",
            json={"message": "no reconozco", "image": png, "image_type": "image/png"},
            headers=bearer(token),
        )
    assert ok.status_code == 200 and seen[0]["image"] == (png, "image/png")


def test_a_photo_of_the_wrong_type_or_over_4mb_is_refused(cloud, seen):
    token, _ = issue_token("CLI-A")
    png = base64.b64encode(b"\x89PNG\r\n").decode()
    huge = base64.b64encode(b"x" * 4_000_001).decode()
    with TestClient(http.app) as client:
        kind = client.post(
            "/api/chat",
            json={"message": "no reconozco", "image": png, "image_type": "image/gif"},
            headers=bearer(token),
        )
        size = client.post(
            "/api/chat",
            json={"message": "no reconozco", "image": huge, "image_type": "image/png"},
            headers=bearer(token),
        )
    assert kind.status_code == 400 and size.status_code == 400
    assert seen == []


# ---- the web is another origin: its browser must be allowed to send the token ----


def test_the_web_origin_may_send_the_authorization_header():
    origin = get_settings().cors_origins.split(",")[0].strip()
    preflight = {
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    }
    with TestClient(http.app) as client:
        response = client.options("/api/chat", headers=preflight)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_another_origin_is_not_allowed():
    preflight = {"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"}
    with TestClient(http.app) as client:
        response = client.options("/api/chat", headers=preflight)
    assert "access-control-allow-origin" not in response.headers
