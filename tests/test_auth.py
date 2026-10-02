"""Bearer-token authentication: the token, the endpoints that use it, and what must be refused."""

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

    async def fake_reply(message, thread_key, customer_id):
        calls.append({"thread": thread_key, "customer": customer_id})
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


# ---- POST /api/auth/token: the test identity service ----


def test_only_listed_demo_customers_can_start_a_session_in_the_cloud(cloud):
    with TestClient(http.app) as client:
        ok = client.post("/api/auth/token", json={"customer_id": "CLI-A"})
        assert ok.status_code == 200 and ok.json()["token_type"] == "bearer"
        assert customer_from_token(ok.json()["access_token"]) == "CLI-A"
        refused = client.post("/api/auth/token", json={"customer_id": "CLI-SOMEONE-ELSE"})
        assert refused.status_code == 403


def test_locally_any_customer_can_start_a_session(monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "local")
    with TestClient(http.app) as client:
        assert client.post("/api/auth/token", json={"customer_id": "DEMO-MX-FX"}).status_code == 200


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
