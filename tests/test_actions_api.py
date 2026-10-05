"""The routes that confirm what the agent proposed. Only these run an action, and only for the
customer the token proves."""

import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound import http
from app.adapters.inbound.auth import issue_token
from app.adapters.inbound.conversations import Conversation, conversations
from tests.actions_support import World

BLOCK = {"action": "block_card", "params": {"product_id": "CARD-1"}}


def bearer(customer_id: str) -> dict:
    token, _ = issue_token(customer_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def w(monkeypatch) -> World:
    world = World()
    monkeypatch.setattr(http, "gateway", lambda: world.gateway)
    yield world
    conversations.clear()


@pytest.fixture
def client():
    with TestClient(http.app) as c:
        yield c


def propose(w: World, *actions: dict) -> str:
    import asyncio

    view = asyncio.run(
        w.gateway.propose("C1", list(actions), language="es", conversation_id="C1:t1")
    )
    return view["batch_id"]


# ---------------------------------------------------------------- off by default


def test_with_actions_off_the_routes_do_not_exist(client: TestClient):
    for method, path in (
        ("post", "/api/actions/00000000-0000-4000-8000-000000000001/confirm"),
        ("post", "/api/actions/00000000-0000-4000-8000-000000000001/cancel"),
        ("get", "/api/me/outbox"),
    ):
        response = getattr(client, method)(
            path, headers=bearer("C1"), **({"json": {}} if method == "post" else {})
        )
        assert (response.status_code, response.json()["detail"]) == (404, "actions_disabled")


# ---------------------------------------------------------------- confirming


def test_the_customer_confirms_and_it_runs_once(client: TestClient, w: World):
    batch = propose(w, BLOCK)
    assert w.effects.calls == []
    first = client.post(f"/api/actions/{batch}/confirm", json={}, headers=bearer("C1"))
    second = client.post(f"/api/actions/{batch}/confirm", json={}, headers=bearer("C1"))
    assert first.status_code == 200 and first.json() == second.json()
    assert first.json()["items"][0]["status"] == "verified"
    assert [c[0] for c in w.effects.calls] == ["card_control", "confirm_card"]


def test_somebody_elses_batch_is_unknown_and_nothing_runs(client: TestClient, w: World):
    batch = propose(w, BLOCK)
    for action in ("confirm", "cancel"):
        response = client.post(f"/api/actions/{batch}/{action}", json={}, headers=bearer("C2"))
        assert (response.status_code, response.json()["detail"]) == (404, "unknown_batch")
    assert w.effects.calls == []


def test_a_batch_that_does_not_exist_is_unknown(client: TestClient, w: World):
    for batch in ("00000000-0000-4000-8000-0000000000ff", "not-a-uuid"):
        assert (
            client.post(f"/api/actions/{batch}/confirm", json={}, headers=bearer("C1")).status_code
            == 404
        )


def test_the_token_decides_who_confirms_not_the_body(client: TestClient, w: World):
    batch = propose(w, BLOCK)
    response = client.post(
        f"/api/actions/{batch}/confirm", json={"customer_id": "C1"}, headers=bearer("C2")
    )
    assert response.status_code == 403, "a body that names someone else than the token is refused"
    assert w.effects.calls == []


def test_a_customer_can_change_their_mind(client: TestClient, w: World):
    batch = propose(w, BLOCK)
    cancelled = client.post(f"/api/actions/{batch}/cancel", json={}, headers=bearer("C1")).json()
    assert cancelled["items"][0]["status"] == "cancelled"
    again = client.post(f"/api/actions/{batch}/confirm", json={}, headers=bearer("C1")).json()
    assert again["items"][0]["status"] == "cancelled" and w.effects.calls == []


def test_the_demo_inbox_the_customer_picked_reaches_the_mailer(client: TestClient, w: World):
    inquiry = {"action": "open_payment_inquiry", "params": {"transaction_id": "T1"}}
    receipt = {"action": "send_summary_email", "params": {"topic": "case_receipt"}}
    batch = propose(w, inquiry, receipt)
    client.post(
        f"/api/actions/{batch}/confirm", json={"inbox": "b@demo.test"}, headers=bearer("C1")
    )
    assert w.effects.inboxes_used == ["b@demo.test"]


# ---------------------------------------------------------------- what the operator sees


def watched(key: str = "C1:t1") -> Conversation:
    conversations[key] = Conversation(key, "C1")
    return conversations[key]


def test_the_outcome_is_mirrored_once_in_the_chat_the_operator_sees(client: TestClient, w: World):
    chat = watched()
    batch = propose(w, BLOCK)
    for _ in range(2):
        client.post(f"/api/actions/{batch}/confirm", json={"thread_id": "t1"}, headers=bearer("C1"))
    texts = [m["text"] for m in chat.messages]
    assert len(texts) == 1 and "quedó bloqueada" in texts[0]
    assert chat.status == "bot", "a good outcome does not call a person"


def test_an_action_that_could_not_be_verified_goes_to_a_person_with_the_case(
    client: TestClient, w: World
):
    chat = watched()
    w.effects.silent_card = True
    batch = propose(w, BLOCK)
    client.post(f"/api/actions/{batch}/confirm", json={"thread_id": "t1"}, headers=bearer("C1"))
    assert chat.status == "waiting"
    assert chat.case_file["unresolved"] == [
        {"action": "block_card", "reason": "verification_failed"}
    ]
    assert (
        chat.case_file["actions"][0]["status"] == "failed" and chat.case_file["customer_id"] == "C1"
    )


def test_a_chat_that_a_person_already_has_is_left_alone(client: TestClient, w: World):
    chat = watched()
    chat.status = "human"
    w.effects.silent_card = True
    client.post(
        f"/api/actions/{propose(w, BLOCK)}/confirm", json={"thread_id": "t1"}, headers=bearer("C1")
    )
    assert chat.status == "human"


# ---------------------------------------------------------------- the chat and the outbox


def test_the_chat_answer_carries_what_was_proposed(client: TestClient, monkeypatch):
    async def reply(message, thread_id, customer_id=None, image=None):
        return {
            "reply": "Revisa abajo.", "customer_id": customer_id, "skill": "account_actions",
            "tools_used": ["propose_actions"], "handoff": None,
            "actions": {"batch_id": "b1", "items": []},
        }  # fmt: skip

    monkeypatch.setattr(http, "reply", reply)
    body = client.post(
        "/api/chat", json={"message": "bloquea mi tarjeta"}, headers=bearer("C1")
    ).json()
    assert body["actions"] == {"batch_id": "b1", "items": []}
    conversations.clear()


def test_the_outbox_shows_only_the_token_customers_messages(
    client: TestClient, w: World, monkeypatch
):
    asked = []

    async def recent(customer_id, limit):
        asked.append((customer_id, limit))
        return [{"subject": "Hola", "body": "…", "status": "accepted"}]

    monkeypatch.setattr(http, "recent_messages", recent)
    rows = client.get("/api/me/outbox?limit=5", headers=bearer("C1")).json()
    assert rows == [{"subject": "Hola", "body": "…", "status": "accepted"}] and asked == [("C1", 5)]
    assert client.get("/api/me/outbox?customer_id=C2", headers=bearer("C1")).status_code == 403
    assert client.get("/api/me/outbox?limit=500", headers=bearer("C1")).status_code == 422
