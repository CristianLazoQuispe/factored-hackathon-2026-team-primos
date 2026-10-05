# ruff: noqa: E501, F811  (long made-up prompts; and the fixtures of the actions tests are reused by name)
"""What the agent is shown of a customer's earlier conversations: where, for how long, and to whom.
A scripted model, the real graph, no database."""

import asyncio
import uuid

import pytest
from langchain_core.messages import AIMessage

from app.adapters.inbound.agent import graph
from app.domain import chat_memory as rules
from tests.test_actions_agent import (  # noqa: F401  (fixtures)
    PROPOSE_BLOCK,
    ROUTE,
    actions_on,
    call,
    say,
    w,
)

pytestmark = pytest.mark.anyio

SUMMARY = rules.summary_for_agent(
    [
        rules.Past(
            when=rules.datetime(2026, 10, 4),
            title="¿Cuál es mi saldo?",
            last_customer="",
            skill="balance_inquiry",
            outcome="answered",
            turns=1,
        )
    ]
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def system_of(messages) -> str:
    return next(m.content for m in messages if m.type == "system")


async def test_the_router_is_given_the_summary_after_its_prompt(actions_on, w, monkeypatch):
    model = say(AIMessage("Hola, ¿en qué te ayudo?"), monkeypatch=monkeypatch)
    await graph.reply("hola", uuid.uuid4().hex, "C1", memory=SUMMARY)
    prompt = system_of(model.seen[0])
    assert "## Earlier conversations" in prompt and SUMMARY in prompt
    assert prompt.index("## Skills") < prompt.index("## Earlier conversations"), (
        "after the rules, never before them"
    )


async def test_without_a_summary_the_prompt_is_exactly_what_it_was(actions_on, w, monkeypatch):
    model = say(AIMessage("Hola"), AIMessage("Hola"), monkeypatch=monkeypatch)
    await graph.reply("hola", uuid.uuid4().hex, "C1")
    await graph.reply("hola", uuid.uuid4().hex, "C1", memory="")
    assert system_of(model.seen[0]) == system_of(model.seen[1])
    assert "Earlier conversations" not in system_of(model.seen[0])


async def test_the_skill_that_answers_is_given_it_too(actions_on, w, monkeypatch):
    model = say(
        ROUTE,
        AIMessage("", tool_calls=[call("my_cards")]),
        AIMessage("", tool_calls=[PROPOSE_BLOCK]),
        AIMessage("Revisa lo que propongo y confírmalo abajo."),
        monkeypatch=monkeypatch,
    )
    await graph.reply("bloquea mi tarjeta", uuid.uuid4().hex, "C1", memory=SUMMARY)
    skill_prompts = [system_of(seen) for seen in model.seen[1:]]
    assert skill_prompts and all("## Active skill" in p and SUMMARY in p for p in skill_prompts)
    assert all(
        p.index("## Active skill") < p.index("## Earlier conversations") for p in skill_prompts
    )


async def test_it_is_not_kept_with_the_thread_and_does_not_reach_the_next_turn(
    actions_on, w, monkeypatch
):
    model = say(AIMessage("uno"), AIMessage("dos"), monkeypatch=monkeypatch)
    thread = uuid.uuid4().hex
    await graph.reply("primero", thread, "C1", memory=SUMMARY)
    saved = await graph.agent.aget_state({"configurable": {"thread_id": thread}})
    everything = repr(saved.values) + repr(saved.metadata) + repr(saved.config)
    assert "Earlier conversations" not in everything and "¿Cuál es mi saldo?" not in everything
    await graph.reply("segundo", thread, "C1")  # this turn is given none
    assert "Earlier conversations" not in system_of(model.seen[1])
    assert all(
        "Earlier conversations" not in repr(m.content) for m in model.seen[1] if m.type != "system"
    )


async def test_it_is_forgotten_when_the_turn_ends_even_if_the_turn_fails(
    actions_on, w, monkeypatch
):
    async def broken(*args, **kwargs):
        raise RuntimeError("the model is down")

    monkeypatch.setattr(graph.agent, "ainvoke", broken)
    result = await graph.reply("hola", uuid.uuid4().hex, "C1", memory=SUMMARY)
    assert result["handoff"]["reason"] == "assistant_error"
    assert graph.earlier_conversations.get() == ""


async def test_two_customers_answered_at_once_each_see_only_their_own(actions_on, w, monkeypatch):
    seen_by_thread: dict[str, str] = {}

    class Slow:
        def __init__(self, tag: str):
            self.tag = tag

    async def fake_invoke(turn, config):
        await asyncio.sleep(0.05)  # both are in flight together
        seen_by_thread[config["configurable"]["thread_id"]] = graph.with_memory("PROMPT")
        return {"messages": [AIMessage("ok")], "customer_id": "C1"}

    monkeypatch.setattr(graph.agent, "ainvoke", fake_invoke)
    await asyncio.gather(
        graph.reply("a", "t-ana", "C1", memory="MEMORIA DE ANA"),
        graph.reply("b", "t-luis", "C2", memory="MEMORIA DE LUIS"),
        graph.reply("c", "t-sin", "C3"),
    )
    assert (
        seen_by_thread["t-ana"].endswith("MEMORIA DE ANA") and "LUIS" not in seen_by_thread["t-ana"]
    )
    assert (
        seen_by_thread["t-luis"].endswith("MEMORIA DE LUIS")
        and "ANA" not in seen_by_thread["t-luis"]
    )
    assert seen_by_thread["t-sin"] == "PROMPT"


def test_the_prompt_helper_adds_a_section_only_when_there_is_something_to_add():
    assert graph.with_memory("P") == "P"
    token = graph.earlier_conversations.set("lo de antes")
    try:
        expected = f"P\n\n## Earlier conversations\n{graph.MEMORY_RULES}\n\nlo de antes"
        assert graph.with_memory("P") == expected
    finally:
        graph.earlier_conversations.reset(token)
    assert graph.with_memory("P") == "P"


# ---------------------------------------------- the agent is told it may use what it remembers


async def test_the_history_comes_with_permission_to_use_it_and_what_to_say_when_it_is_not_there(
    actions_on, w, monkeypatch
):
    """A model that reads 'you can only help with your skills' answers 'I have no memory'. It must be told."""
    model = say(AIMessage("Preguntaste por tu saldo."), monkeypatch=monkeypatch)
    await graph.reply("¿qué te pregunté antes?", uuid.uuid4().hex, "C1", memory=SUMMARY)
    prompt = system_of(model.seen[0])
    section = prompt[prompt.index("## Earlier conversations") :]
    for must_say in (
        "You do remember this customer",
        "whatever the scope above says",
        "do not see it in their earlier conversations",
        "Never say that you have no memory",
    ):
        assert must_say in section, must_say
    assert section.index("You do remember") < section.index(SUMMARY), (
        "the permission comes before the history"
    )
    assert prompt.index("Scope") < prompt.index("## Earlier conversations"), (
        "and after the scope it overrides"
    )


async def test_the_permission_is_there_for_the_skill_too_and_never_without_a_history(
    actions_on, w, monkeypatch
):
    model = say(
        ROUTE,
        AIMessage("", tool_calls=[call("my_cards")]),
        AIMessage("", tool_calls=[PROPOSE_BLOCK]),
        AIMessage("Revisa lo que propongo y confírmalo abajo."),
        AIMessage("hola"),
        monkeypatch=monkeypatch,
    )
    await graph.reply("bloquea mi tarjeta", uuid.uuid4().hex, "C1", memory=SUMMARY)
    assert all("Never say that you have no memory" in system_of(seen) for seen in model.seen[1:4])
    await graph.reply("hola", uuid.uuid4().hex, "C1")
    assert "You do remember" not in system_of(model.seen[-1]), (
        "a customer with no history is not told they have one"
    )
