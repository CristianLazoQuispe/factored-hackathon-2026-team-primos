"""The operator console: who may read the chats, what it sees, and when the agent stays out."""

import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound import http
from app.adapters.inbound.auth import issue_token
from app.adapters.inbound.conversations import conversations
from app.config import get_settings

OPERATOR_KEY = "o" * 40
OPERATOR = {"Authorization": f"Bearer {OPERATOR_KEY}"}


@pytest.fixture(autouse=True)
def cloud(monkeypatch):
    """The deployed configuration, with an empty console."""
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "cloud")
    monkeypatch.setattr(settings, "jwt_secret", "s" * 40)
    monkeypatch.setattr(settings, "operator_key", OPERATOR_KEY)
    conversations.clear()


@pytest.fixture
def agent(monkeypatch):
    """Replace the agent: records the turns it gets and hands off when asked for a person."""
    turns = []

    async def fake_reply(message, thread_key, customer_id, image=None):
        turns.append(message)
        handoff = {"customer_id": customer_id, "request": message} if "persona" in message else None
        return {
            "reply": f"bot: {message}",
            "customer_id": customer_id,
            "skill": None,
            "tools_used": [],
            "handoff": handoff,
        }

    monkeypatch.setattr(http, "reply", fake_reply)
    return turns


def as_customer(customer: str) -> dict:
    return {"Authorization": f"Bearer {issue_token(customer)[0]}"}


def say(client: TestClient, text: str, customer: str = "CLI-A", thread: str = "t1") -> dict:
    response = client.post(
        "/api/chat", json={"message": text, "thread_id": thread}, headers=as_customer(customer)
    )
    assert response.status_code == 200
    return response.json()


def console(client: TestClient) -> list[dict]:
    return client.get("/api/crm/conversations", headers=OPERATOR).json()


def operator_says(client: TestClient, text: str, thread_key: str = "CLI-A:t1") -> None:
    body = {"thread_key": thread_key, "text": text}
    assert client.post("/api/crm/reply", json=body, headers=OPERATOR).status_code == 200


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer wrong-key"}, {"Authorization": "Bearer clavé".encode()}],
    ids=["no-key", "wrong-key", "non-ascii-key"],
)
def test_the_console_needs_the_operator_key(agent, headers):
    body = {"thread_key": "CLI-A:t1", "text": "hola"}
    with TestClient(http.app) as client:
        say(client, "hola")
        responses = [
            client.get("/api/crm/conversations", headers=headers),
            client.post("/api/crm/reply", json=body, headers=headers),
            client.post("/api/crm/release", json=body, headers=headers),
        ]
    assert [r.status_code for r in responses] == [401, 401, 401]


def test_a_customer_token_does_not_open_the_console(agent):
    with TestClient(http.app) as client:
        response = client.get("/api/crm/conversations", headers=as_customer("CLI-A"))
    assert response.status_code == 401


def test_a_chat_turn_shows_up_in_the_console(agent):
    with TestClient(http.app) as client:
        say(client, "hola")
        [chat] = console(client)
    assert (chat["thread_key"], chat["customer_id"], chat["status"]) == ("CLI-A:t1", "CLI-A", "bot")
    assert [(m["role"], m["text"]) for m in chat["messages"]] == [
        ("customer", "hola"),
        ("assistant", "bot: hola"),
    ]


def test_a_handoff_leaves_the_chat_waiting_with_its_case_file_and_listed_first(agent):
    with TestClient(http.app) as client:
        say(client, "quiero una persona", thread="t1")
        say(client, "hola", thread="t2")
        first, second = console(client)
    assert (first["thread_key"], first["status"]) == ("CLI-A:t1", "waiting")
    assert first["case_file"] == {"customer_id": "CLI-A", "request": "quiero una persona"}
    assert second["status"] == "bot"


def test_while_a_chat_waits_for_a_person_the_agent_stays_out(agent):
    with TestClient(http.app) as client:
        say(client, "quiero una persona")
        answer = say(client, "¿sigues ahí?")
        [chat] = console(client)
    assert answer["reply"] is None and agent == ["quiero una persona"]
    assert chat["messages"][-1]["text"] == "¿sigues ahí?"  # the operator still sees it


def test_after_the_operator_replies_the_agent_stays_out(agent):
    with TestClient(http.app) as client:
        say(client, "hola")
        operator_says(client, "Soy Ana, te ayudo.")
        answer = say(client, "gracias")
        [chat] = console(client)
    assert answer["reply"] is None and agent == ["hola"]
    assert chat["status"] == "human"
    roles = [m["role"] for m in chat["messages"]]
    assert roles == ["customer", "assistant", "operator", "customer"]


def test_the_customer_reads_the_operator_reply_once_and_nobody_else_does(agent):
    with TestClient(http.app) as client:
        say(client, "hola", customer="CLI-A")
        say(client, "hola", customer="CLI-B")  # same thread id, another customer
        operator_says(client, "Soy Ana, te ayudo.", thread_key="CLI-A:t1")
        mine = client.get("/api/chat/t1/operator", headers=as_customer("CLI-A")).json()
        again = client.get(
            "/api/chat/t1/operator", params={"after": mine["next"]}, headers=as_customer("CLI-A")
        ).json()
        theirs = client.get("/api/chat/t1/operator", headers=as_customer("CLI-B")).json()
        anonymous = client.get("/api/chat/t1/operator")
    assert [m["text"] for m in mine["messages"]] == ["Soy Ana, te ayudo."] and mine["next"] == 3
    assert again["messages"] == [] and theirs["messages"] == []
    assert anonymous.status_code == 401


def test_a_released_chat_goes_back_to_the_agent(agent):
    with TestClient(http.app) as client:
        say(client, "quiero una persona")
        operator_says(client, "Listo, resuelto.")
        client.post("/api/crm/release", json={"thread_key": "CLI-A:t1"}, headers=OPERATOR)
        answer = say(client, "otra consulta")
        [chat] = console(client)
    assert answer["reply"] == "bot: otra consulta" and chat["status"] == "bot"


def test_a_chat_the_instance_no_longer_has_is_a_404(agent):
    body = {"thread_key": "CLI-A:gone", "text": "hola"}
    with TestClient(http.app) as client:
        reply = client.post("/api/crm/reply", json=body, headers=OPERATOR)
        release = client.post("/api/crm/release", json=body, headers=OPERATOR)
        polled = client.get("/api/chat/gone/operator", headers=as_customer("CLI-A"))
    assert (reply.status_code, release.status_code) == (404, 404)
    assert polled.json() == {"next": 0, "messages": []}  # the customer's page just keeps polling
