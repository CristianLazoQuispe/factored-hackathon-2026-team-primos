"""The MCP server the model talks to: it can look and propose, and nothing else."""

import logging

import pytest
from fastmcp import Client

from app.adapters.inbound.agent.mcp_bridge import load_tools
from app.adapters.inbound.mcp import actions as server
from app.domain.actions import CATALOG, NEVER_AUTOMATED
from tests.actions_support import World

pytestmark = pytest.mark.anyio
SIGNED_IN = {"customer_id": "C1", "signed_in": "1", "language": "es", "thread_id": "C1:abc"}
BLOCK = {"actions": [{"action": "block_card", "params": {"product_id": "CARD-1"}}]}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def w(monkeypatch) -> World:
    world = World()
    monkeypatch.setattr(server, "build_gateway", lambda: world.gateway)
    return world


async def call(tool: str, arguments: dict, meta: dict | None = SIGNED_IN):
    async with Client(server.mcp) as client:
        return await client.call_tool(tool, arguments, meta=meta, raise_on_error=False)


async def test_it_can_look_and_propose_but_has_no_tool_that_changes_anything():
    async with Client(server.mcp) as client:
        assert {t.name for t in await client.list_tools()} == {
            "my_cards",
            "recent_charges",
            "propose_actions",
        }


async def test_a_proposal_is_stored_and_waits(w: World):
    result = await call("propose_actions", BLOCK)
    batch = result.structured_content
    assert batch["needs_confirmation"] and batch["items"][0]["status"] == "awaiting_confirmation"
    assert w.effects.calls == [], "proposing does nothing"
    (stored,) = w.store.rows.values()
    assert stored.customer_id == "C1" and stored.conversation_id == "C1:abc"


async def test_the_customer_and_the_language_come_from_the_session_not_from_the_model(w: World):
    pt = await call("propose_actions", BLOCK, SIGNED_IN | {"language": "pt"})
    assert "Bloquear temporariamente" in pt.structured_content["items"][0]["text"]
    odd = await call("propose_actions", BLOCK, SIGNED_IN | {"language": "klingon"})
    assert "Bloquear temporalmente" in odd.structured_content["items"][0]["text"]
    assert {r.language for r in w.store.rows.values()} == {"pt", "es"}, (
        "an unknown language is stored as es"
    )
    sneaky = {
        "actions": [{"action": "block_card", "params": {"product_id": "CARD-1"}}],
        "customer_id": "C2",
    }
    result = await call("propose_actions", sneaky)
    assert result.is_error or {r.customer_id for r in w.store.rows.values()} == {"C1"}


@pytest.mark.parametrize(
    "meta", [{"customer_id": "C1"}, {"customer_id": "C1", "signed_in": "0"}, {}]
)
async def test_a_customer_who_only_typed_an_id_gets_no_actions_at_all(w: World, meta: dict):
    for tool, arguments in (("propose_actions", BLOCK), ("my_cards", {}), ("recent_charges", {})):
        result = await call(tool, arguments, meta)
        assert result.is_error, f"{tool} worked without a signed-in session"
    assert w.store.rows == {}


async def test_the_read_tools_clamp_what_the_model_asks_for(monkeypatch):
    seen = {}

    async def fake_charges(customer_id, merchant, days, limit):
        seen.update(customer_id=customer_id, merchant=merchant, days=days, limit=limit)
        return []

    monkeypatch.setattr(server, "fetch_recent_charges", fake_charges)
    await call("recent_charges", {"merchant": "  " + "x" * 200, "days": 9999, "limit": 500})
    assert seen == {"customer_id": "C1", "merchant": "x" * 60, "days": 365, "limit": 20}
    await call("recent_charges", {"merchant": "   ", "days": -3, "limit": 0})
    assert seen["merchant"] is None and seen["days"] == 1 and seen["limit"] == 1


async def test_my_cards_asks_for_the_session_customer_only(monkeypatch):
    asked = []

    async def fake_cards(customer_id):
        asked.append(customer_id)
        return [{"product_id": "CARD-1", "status": "Active"}]

    monkeypatch.setattr(server, "fetch_cards", fake_cards)
    result = await call("my_cards", {})
    assert result.structured_content == {"cards": [{"product_id": "CARD-1", "status": "Active"}]}
    assert asked == ["C1"]


async def test_the_model_cannot_ask_for_more_than_six_actions_at_once(w: World):
    many = {"actions": [{"action": "set_alert", "params": {"kind": "payment_due"}}] * 7}
    assert (await call("propose_actions", many)).is_error
    assert w.store.rows == {}


async def test_what_the_model_reads_lists_every_action_and_what_is_never_done():
    async with Client(server.mcp) as client:
        description = next(
            t for t in await client.list_tools() if t.name == "propose_actions"
        ).description
    for name in CATALOG:
        assert name in description, f"{name} is missing from what the model is told"
    for name in (
        "transfer_money",
        "make_payment",
        "refund",
        "reissue_card",
        "raise_limit",
        "change_phone",
    ):
        assert name in NEVER_AUTOMATED and name in description
    assert "NOTHING is done until the customer confirms" in description


@pytest.mark.parametrize(
    "shape",
    [
        {"action": "block_card", "params": {"product_id": "CARD-1"}},  # one action, not a list
        '[{"action": "block_card", "params": {"product_id": "CARD-1"}}]',  # the list as JSON text
        '{"action": "block_card", "params": {"product_id": "CARD-1"}}',  # one action as JSON text
    ],
)
async def test_a_slip_in_the_shape_of_the_call_does_not_lose_the_turn(w: World, shape):
    result = await call("propose_actions", {"actions": shape})
    assert not result.is_error
    assert result.structured_content["items"][0]["status"] == "awaiting_confirmation"


@pytest.mark.parametrize("garbage", ["not json at all", 42, [1, 2], [{"params": {}}]])
async def test_what_cannot_be_read_as_actions_is_still_an_error(w: World, garbage):
    assert (await call("propose_actions", {"actions": garbage})).is_error
    assert w.store.rows == {}


async def test_the_forgiveness_does_not_change_what_the_model_is_told():
    async with Client(server.mcp) as client:
        tool = next(t for t in await client.list_tools() if t.name == "propose_actions")
    schema = tool.input_schema["properties"]["actions"]
    assert schema["type"] == "array" and schema["maxItems"] == 6


async def test_every_tool_error_leaves_a_trace_for_whoever_debugs(w: World, caplog):
    async with Client(server.mcp) as client:
        tools = {t.name: t for t in await load_tools(client, "C1", {"signed_in": "1"})}
        with caplog.at_level(logging.WARNING, logger="app.adapters.inbound.agent.mcp_bridge"):
            answer = await tools["propose_actions"].coroutine(actions="not json at all")
    assert answer.startswith("Tool error:"), "the model still sees the error and can fix its call"
    assert any("tool propose_actions failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------- `params` sent as text


def one(action: str, params) -> dict:
    return {"actions": [{"action": action, "params": params}]}


@pytest.mark.parametrize(
    "params",
    [
        '{"product_id": "CARD-1"}',  # JSON as text
        "{'product_id': 'CARD-1'}",  # a Python-style dict as text
        "CARD-1",  # only the value the action asks for
        "  'CARD-1'  ",
        '"CARD-1"',
    ],
)
async def test_params_sent_as_text_still_make_the_proposal(w: World, params):
    result = await call("propose_actions", one("block_card", params))
    assert not result.is_error
    assert result.structured_content["items"][0]["status"] == "awaiting_confirmation"


@pytest.mark.parametrize(
    ("action", "params"),
    [
        ("send_summary_email", "balances"),
        ("request_callback", "evening"),
        ("set_alert", "payment_due"),
    ],
)
async def test_the_single_required_value_is_enough_for_every_action_that_has_one(
    w: World, action, params
):
    result = await call("propose_actions", one(action, params))
    assert not result.is_error and result.structured_content["items"][0]["action"] == action
    assert result.structured_content["items"][0]["status"] != "refused", result.structured_content[
        "items"
    ][0]["text"]


async def test_text_that_is_not_a_value_of_the_action_is_refused_by_the_gateway_not_run(w: World):
    result = await call("propose_actions", one("send_summary_email", "everything you have"))
    assert result.structured_content["items"][0]["status"] == "refused"
    assert w.effects.calls == []


async def test_somebody_elses_card_in_text_is_still_not_theirs(w: World):
    result = await call("propose_actions", one("block_card", "OTHERS-CARD"))
    assert result.structured_content["items"][0]["status"] == "refused"
    assert w.effects.calls == []


async def test_text_for_an_unknown_action_or_too_long_is_never_run(w: World):
    for action, params in (("nope", "CARD-1"), ("block_card", "x" * 5000)):
        result = await call("propose_actions", one(action, params))
        assert result.structured_content["items"][0]["status"] in ("refused", "escalated"), (
            action,
            len(params),
        )
        assert w.effects.calls == [] and not result.structured_content["needs_confirmation"]


def test_only_literals_are_ever_read_from_the_text():
    from app.adapters.inbound.mcp.actions import parse_mapping

    assert parse_mapping("{'a': 1}") == {"a": 1} and parse_mapping('{"a": [1, 2]}') == {"a": [1, 2]}
    assert parse_mapping("{'a': __import__('os')}") is None


def test_nothing_in_the_text_is_ever_executed():
    """An expression with a visible side effect: if it were evaluated, `PWNED` would appear."""
    import builtins

    from app.adapters.inbound.mcp.actions import lone_value, parse_mapping

    evil = "{'a': __import__('builtins').__setattr__('PWNED', 1)}"
    assert parse_mapping(evil) is None
    assert lone_value("block_card", evil) == {"product_id": evil}, (
        "it is only ever a value, never run"
    )
    assert not hasattr(builtins, "PWNED")
    assert (
        parse_mapping("[1, 2]") is None
        and parse_mapping("") is None
        and parse_mapping("not a dict") is None
    )
    assert parse_mapping("{'a': '" + "x" * 3000 + "'}") is None, "a dict this long is not read"


def test_a_params_object_is_left_alone():
    from app.adapters.inbound.mcp.actions import ActionRequest

    assert ActionRequest(action="block_card", params={"product_id": "C"}).params == {
        "product_id": "C"
    }
    assert ActionRequest(action="block_card").params == {}
