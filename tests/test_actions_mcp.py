"""The MCP server the model talks to: it can look and propose, and nothing else."""

import pytest
from fastmcp import Client

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
