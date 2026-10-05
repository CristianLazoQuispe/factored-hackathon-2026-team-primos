# ruff: noqa: E501  (made-up conversations and expected rows stay on one line each)
"""The routes of the chat memory: what is kept, to whom it is shown, and that with it off nothing changes.
A fake store that keeps each customer's rows apart, the real routes, no database and no model."""

import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound import http
from app.adapters.inbound.auth import issue_token
from app.adapters.inbound.conversations import conversations
from app.config import get_settings
from app.domain import chat_memory as rules
from tests.actions_support import World

OPERATOR_KEY = "o" * 40
OPERATOR = {"Authorization": f"Bearer {OPERATOR_KEY}"}
BLOCK = {"action": "block_card", "params": {"product_id": "CARD-1"}}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeStore:
    """The same functions as the Postgres store, in memory, with each customer's rows apart."""

    def __init__(self):
        self.turns: list[dict] = []
        self.added: list[dict] = []
        self.deleted: list[str] = []
        self.asked_for_past: list[tuple[str, str]] = []
        self.past: dict[str, list[rules.Past]] = {}
        self.listed: dict[str, list[dict]] = {}

    async def record_turn(self, customer_id, thread_id, customer_text, reply_text, **kw):
        self.turns.append(
            {
                "customer": customer_id,
                "thread": thread_id,
                "said": customer_text,
                "reply": reply_text,
                **kw,
            }
        )
        return True

    async def past_for_agent(self, customer_id, thread_id, limit=8):
        self.asked_for_past.append((customer_id, thread_id))
        return self.past.get(customer_id, [])

    async def list_conversations(self, customer_id, limit=30):
        return self.listed.get(customer_id, [])

    async def read_conversation(self, customer_id, conversation):
        return next(
            (c for c in self.listed.get(customer_id, []) if c["conversation_id"] == conversation),
            None,
        )

    async def delete_history(self, customer_id):
        self.deleted.append(customer_id)
        return len(self.listed.pop(customer_id, []))

    async def append_message(self, customer_id, thread_id, role, text, *, outcome=None):
        self.added.append(
            {
                "customer": customer_id,
                "thread": thread_id,
                "role": role,
                "text": text,
                "outcome": outcome,
            }
        )
        return True

    @property
    def untouched(self) -> bool:
        return not (self.turns or self.added or self.deleted or self.asked_for_past)


@pytest.fixture(autouse=True)
def cloud(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "cloud")
    monkeypatch.setattr(settings, "jwt_secret", "s" * 40)
    monkeypatch.setattr(settings, "operator_key", OPERATOR_KEY)
    conversations.clear()
    yield settings
    conversations.clear()


@pytest.fixture
def on(cloud, monkeypatch):
    monkeypatch.setattr(cloud, "chat_memory_enabled", True)


@pytest.fixture
def store(monkeypatch) -> FakeStore:
    fake = FakeStore()
    monkeypatch.setattr(http, "memory_store", fake)
    return fake


@pytest.fixture
def agent(monkeypatch):
    """Replace the agent: records the keywords it is called with, answers what the test sets."""
    seen: dict = {"calls": [], "result": {}}

    async def fake_reply(message, thread_key, customer_id, image=None, **extra):
        seen["calls"].append(
            {"message": message, "thread": thread_key, "customer": customer_id, "extra": extra}
        )
        base = {
            "reply": f"bot: {message}",
            "customer_id": customer_id,
            "skill": "balance_inquiry",
            "tools_used": [],
            "handoff": None,
            "actions": None,
            "confirmation": None,
        }
        return base | seen["result"]

    monkeypatch.setattr(http, "reply", fake_reply)
    return seen


@pytest.fixture
def client():
    with TestClient(http.app) as c:
        yield c


def bearer(customer: str) -> dict:
    return {"Authorization": f"Bearer {issue_token(customer)[0]}"}


def say(client, text="hola", customer="C1", thread="t1", **body):
    response = client.post(
        "/api/chat", json={"message": text, "thread_id": thread} | body, headers=bearer(customer)
    )
    assert response.status_code == 200, response.text
    return response.json()


def a_past(title="¿Cuál es mi saldo?", **kw) -> rules.Past:
    base = {
        "when": rules.datetime(2026, 10, 4),
        "title": title,
        "last_customer": title,
        "skill": "balance_inquiry",
        "outcome": "answered",
        "turns": 1,
    }
    return rules.Past(**(base | kw))


# ------------------------------------------------------------------ off: nothing changes


def test_with_the_memory_off_the_chat_is_what_it_was_and_the_store_is_never_touched(
    client, store, agent
):
    reply = say(client, "hola")
    assert reply["reply"] == "bot: hola"
    assert store.untouched
    assert agent["calls"][0]["extra"] == {}, "the agent is called exactly as before: no new keyword"


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/api/me/conversations"),
        ("get", "/api/me/conversations/x"),
        ("delete", "/api/me/conversations"),
    ],
)
def test_with_the_memory_off_its_routes_do_not_exist(client, store, method, path):
    response = getattr(client, method)(path, headers=bearer("C1"))
    assert (response.status_code, response.json()["detail"]) == (404, "chat_memory_disabled")
    assert store.untouched


# ------------------------------------------------------------------ on: keeping turns


def test_each_turn_is_kept_with_what_the_agent_answered_and_how_it_ended(client, on, store, agent):
    say(client, "¿Cuál es mi saldo?", thread="t1")
    assert store.turns == [
        {
            "customer": "C1",
            "thread": "t1",
            "said": "¿Cuál es mi saldo?",
            "reply": "bot: ¿Cuál es mi saldo?",
            "skill": "balance_inquiry",
            "outcome": "answered",
            "language": None,
        }
    ]


@pytest.mark.parametrize(
    "result, expected",
    [
        ({}, "answered"),
        ({"handoff": {"request": "x"}}, "handed_off"),
        ({"actions": {"needs_confirmation": True, "language": "pt", "items": []}}, "proposed"),
        ({"confirmation": {"transfer_id": "T1"}}, "proposed"),
        ({"actions": {"needs_confirmation": False, "items": [{"status": "verified"}]}}, "done"),
        ({"actions": {"needs_confirmation": False, "items": [{"status": "refused"}]}}, "refused"),
    ],
)
def test_the_outcome_of_a_turn_is_what_the_agent_returned(
    client, on, store, agent, result, expected
):
    agent["result"] = result
    say(client)
    assert store.turns[0]["outcome"] == expected


def test_the_language_of_a_proposal_is_kept(client, on, store, agent):
    agent["result"] = {"actions": {"needs_confirmation": True, "language": "pt", "items": []}}
    say(client)
    assert store.turns[0]["language"] == "pt"


def test_a_photo_without_words_is_kept_as_a_note_and_the_photo_is_not(client, on, store, agent):
    import base64

    photo = base64.b64encode(b"\x89PNG" + b"x" * 20).decode()
    say(client, "", image=photo, image_type="image/png")
    assert store.turns[0]["said"] == "[foto]"
    assert photo not in repr(store.turns)


def test_the_memory_is_the_tokens_customer_and_never_the_one_the_body_claims(
    client, on, store, agent
):
    response = client.post(
        "/api/chat",
        json={"message": "hola", "thread_id": "t1", "customer_id": "C2"},
        headers=bearer("C1"),
    )
    assert response.status_code == 403
    assert store.untouched and agent["calls"] == []


def test_without_a_customer_there_is_nothing_to_remember(
    cloud, monkeypatch, client, on, store, agent
):
    monkeypatch.setattr(cloud, "app_env", "local")  # the only place a chat may be anonymous
    response = client.post("/api/chat", json={"message": "hola", "thread_id": "t1"})
    assert response.status_code == 200
    assert store.untouched and agent["calls"][0]["extra"] == {}


def test_when_a_person_has_the_chat_the_customers_message_is_kept_and_the_agent_stays_out(
    client, on, store, agent
):
    say(client, "hola", thread="t1")
    key = next(iter(conversations))
    client.post(
        "/api/crm/reply", json={"thread_key": key, "text": "Hola, soy Marta."}, headers=OPERATOR
    )
    turns_before = len(agent["calls"])
    answer = say(client, "gracias, ¿me ayudas?", thread="t1")
    assert answer["reply"] is None and len(agent["calls"]) == turns_before
    assert store.turns[-1]["said"] == "gracias, ¿me ayudas?" and store.turns[-1]["reply"] == ""


# ------------------------------------------------------------------ on: telling the agent


def test_the_agent_is_given_the_summary_of_the_other_conversations(client, on, store, agent):
    store.past["C1"] = [a_past("bloquea mi tarjeta", outcome="done", skill="account_actions")]
    say(client, "hola", thread="nuevo")
    summary = agent["calls"][0]["extra"]["memory"]
    assert (
        summary.splitlines()[1].startswith('1. 2026-10-04: asked "bloquea mi tarjeta"')
        and "result: done" in summary
    )
    assert store.asked_for_past == [("C1", "nuevo")], "for this customer, apart from this thread"


def test_one_customer_never_gets_the_summary_of_another(client, on, store, agent):
    store.past["C2"] = [a_past("secreto de C2")]
    say(client, "hola", customer="C1")
    assert agent["calls"][0]["extra"] == {} and "C2" not in repr(agent["calls"])


def test_with_nothing_to_remember_the_agent_is_called_as_usual(client, on, store, agent):
    say(client, "hola")
    assert agent["calls"][0]["extra"] == {}


# ------------------------------------------------------------------ the routes the customer uses


def entry(identifier: str, title: str) -> dict:
    return {
        "conversation_id": identifier,
        "title": title,
        "messages": [{"role": "customer", "content": title}],
    }


def test_the_customer_lists_and_opens_only_their_own_conversations(client, on, store):
    store.listed = {"C1": [entry("a", "de Ana")], "C2": [entry("b", "de Luis")]}
    assert [
        c["title"] for c in client.get("/api/me/conversations", headers=bearer("C1")).json()
    ] == ["de Ana"]
    assert client.get("/api/me/conversations/a", headers=bearer("C1")).json()["title"] == "de Ana"
    other = client.get("/api/me/conversations/b", headers=bearer("C1"))
    assert (other.status_code, other.json()["detail"]) == (404, "unknown_conversation")


def test_the_customer_forgets_their_history_and_only_theirs(client, on, store):
    store.listed = {"C1": [entry("a", "x"), entry("c", "y")], "C2": [entry("b", "z")]}
    done = client.delete("/api/me/conversations", headers=bearer("C1"))
    assert done.json() == {"deleted": 2} and store.deleted == ["C1"]
    assert [
        c["title"] for c in client.get("/api/me/conversations", headers=bearer("C2")).json()
    ] == ["z"]


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/api/me/conversations"),
        ("get", "/api/me/conversations/a"),
        ("delete", "/api/me/conversations"),
    ],
)
def test_without_a_token_the_history_is_closed(client, on, store, method, path):
    response = getattr(client, method)(path)
    assert response.status_code == 401 and store.untouched


@pytest.mark.parametrize(
    "method, path", [("get", "/api/me/conversations"), ("delete", "/api/me/conversations")]
)
def test_a_customer_id_in_the_request_cannot_open_somebody_elses(client, on, store, method, path):
    store.listed = {"C2": [entry("b", "de Luis")]}
    response = getattr(client, method)(path + "?customer_id=C2", headers=bearer("C1"))
    assert response.status_code == 403
    assert store.deleted == [] and "de Luis" not in response.text


def test_a_forged_token_opens_nothing(client, on, store):
    response = client.get("/api/me/conversations", headers={"Authorization": "Bearer " + "x" * 80})
    assert response.status_code == 401 and store.untouched


# ------------------------------------------------------------------ what came of a card


@pytest.fixture
def bank(monkeypatch) -> World:
    world = World()
    monkeypatch.setattr(http, "gateway", lambda: world.gateway)
    monkeypatch.setattr(get_settings(), "actions_enabled", True)
    return world


def proposed(bank: World) -> str:
    import asyncio

    view = asyncio.run(bank.gateway.propose("C1", [BLOCK], language="es", conversation_id="C1:t1"))
    return view["batch_id"]


def test_confirming_a_card_keeps_what_came_of_it_and_marks_the_conversation_done(
    client, on, store, bank
):
    batch = proposed(bank)
    client.post(f"/api/actions/{batch}/confirm", json={"thread_id": "t1"}, headers=bearer("C1"))
    [added] = store.added
    assert (added["customer"], added["thread"], added["role"], added["outcome"]) == (
        "C1",
        "t1",
        "assistant",
        "done",
    )
    assert added["text"]


def test_cancelling_a_card_marks_the_conversation_cancelled(client, on, store, bank):
    batch = proposed(bank)
    client.post(f"/api/actions/{batch}/cancel", json={"thread_id": "t1"}, headers=bearer("C1"))
    assert [a["outcome"] for a in store.added] == ["cancelled"]


def test_without_the_thread_there_is_nothing_to_add_to(client, on, store, bank):
    batch = proposed(bank)
    client.post(f"/api/actions/{batch}/confirm", json={}, headers=bearer("C1"))
    assert store.added == []


def test_with_the_memory_off_a_confirmation_keeps_nothing(client, store, bank):
    batch = proposed(bank)
    client.post(f"/api/actions/{batch}/confirm", json={"thread_id": "t1"}, headers=bearer("C1"))
    assert store.untouched


@pytest.mark.anyio
@pytest.mark.parametrize(
    "items, escalate, expected",
    [
        ([{"status": "verified", "text": "Listo."}], [], "done"),
        (
            [
                {"status": "verified", "text": "Listo."},
                {"status": "escalated", "text": "Lo ve una persona."},
            ],
            [{"action": "cancel_card", "reason": "outstanding_balance"}],
            "handed_off",
        ),
        (
            [{"status": "escalated", "text": "Lo ve una persona."}],
            [{"action": "cancel_card", "reason": "past_due"}],
            "handed_off",
        ),
        ([{"status": "cancelled", "text": "Cancelaste."}], [], "cancelled"),
        ([{"status": "refused", "text": "No se pudo."}], [], "refused"),
    ],
)
async def test_a_card_that_ends_with_a_person_is_kept_as_handed_off(
    on, store, items, escalate, expected
):
    await http.remember_decision("C1", "t1", {"items": items, "escalate": escalate})
    assert [a["outcome"] for a in store.added] == [expected]
    assert store.added[0]["text"] == " · ".join(i["text"] for i in items)


# ------------------------------------------------------------------ what a person of the team answers


def test_what_the_operator_answers_is_kept_in_that_customers_history(client, on, store, agent):
    say(client, "necesito ayuda", customer="C1", thread="t9")
    key = next(iter(conversations))
    client.post(
        "/api/crm/reply", json={"thread_key": key, "text": "Hola, soy Marta."}, headers=OPERATOR
    )
    assert store.added == [
        {
            "customer": "C1",
            "thread": "t9",
            "role": "operator",
            "text": "Hola, soy Marta.",
            "outcome": None,
        }
    ]


def test_with_the_memory_off_the_operators_answer_is_not_kept(client, store, agent):
    say(client, "necesito ayuda")
    key = next(iter(conversations))
    response = client.post(
        "/api/crm/reply", json={"thread_key": key, "text": "Hola"}, headers=OPERATOR
    )
    assert response.status_code == 200 and store.untouched


def test_an_operator_answer_in_a_chat_without_a_customer_is_not_kept(client, on, store):
    conversations["anon-thread"] = http.Conversation("anon-thread", None)
    response = client.post(
        "/api/crm/reply", json={"thread_key": "anon-thread", "text": "Hola"}, headers=OPERATOR
    )
    assert response.status_code == 200 and store.added == []
