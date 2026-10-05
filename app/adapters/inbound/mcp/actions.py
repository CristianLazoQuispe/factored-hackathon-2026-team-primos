"""MCP server for the `account_actions` skill: what the agent may PROPOSE, never do.

python -m app.adapters.inbound.mcp.actions   # stdio, e.g. for MCP Inspector

There is no tool here that changes anything. `propose_actions` hands the request to the action
gateway, which checks it against the bank's data and the policy and stores it; it only runs after
the customer confirms it in the app, which the model cannot do. The customer comes from the session
and so do the language and the conversation, so the model cannot choose any of them.
"""

import ast
import json
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, BeforeValidator, Field, model_validator

from app.adapters.inbound.mcp import session_customer, session_meta
from app.adapters.outbound.postgres.actions import (
    build_gateway,
    fetch_cards,
    fetch_recent_charges,
)
from app.domain.action_text import LANGUAGES
from app.domain.actions import CATALOG

mcp = FastMCP("actions")
MAX_REQUESTED = 6


class ActionRequest(BaseModel):
    action: str = Field(
        description="The name of the action, from the list in the tool description."
    )
    params: dict[str, Any] = Field(default_factory=dict, description="Its parameters.")

    @model_validator(mode="before")
    @classmethod
    def params_as_an_object(cls, data: Any) -> Any:
        """Gemini often sends `params` as text: JSON, a Python-style dict, or just the one value the
        action asks for. The schema says object; this only forgives the slip, so the turn is not
        lost to it. What comes out still goes through the gateway's checks on the customer's data.
        """
        if not isinstance(data, dict) or not isinstance(data.get("params"), str):
            return data
        text = data["params"].strip()
        found = parse_mapping(text)
        if found is None:
            found = lone_value(data.get("action"), text)
        return {**data, "params": found or {}}


MAX_PARAMS_TEXT = 2000


def parse_mapping(text: str) -> dict[str, Any] | None:
    """A dict written as JSON or as a Python literal, or None. Only literals: nothing runs."""
    if not text or len(text) > MAX_PARAMS_TEXT:
        return None
    for read in (json.loads, ast.literal_eval):
        try:
            value = read(text)
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            continue
        if isinstance(value, dict):
            return value
    return None


def lone_value(action: Any, text: str) -> dict[str, Any] | None:
    """`"CARD-1"` for block_card: when the action has exactly one required parameter and the text is
    not a dict, the text is that parameter. The gateway still checks it belongs to the customer."""
    spec = CATALOG.get(action) if isinstance(action, str) else None
    required = (
        [name for name, f in spec.params.model_fields.items() if f.is_required()] if spec else []
    )
    if len(required) != 1 or not text or len(text) > MAX_PARAMS_TEXT:
        return None
    return {required[0]: text.strip().strip("'\"")}


def as_list(value: Any) -> Any:
    """Models sometimes send one action instead of a list of one, or the list as JSON text. The
    schema they read says array; this only forgives the slip, so a turn is not lost to it."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return value
    return [value] if isinstance(value, dict) else value


Requested = Annotated[
    list[ActionRequest], BeforeValidator(as_list), Field(max_length=MAX_REQUESTED)
]


def require_sign_in(ctx: Context) -> str:
    """Actions need a customer the token proved, not one who typed an ID in the chat."""
    customer_id = session_customer(ctx)
    if session_meta(ctx, "signed_in") != "1":
        raise ToolError("Actions need a signed-in session.")
    return customer_id


@mcp.tool
async def my_cards(ctx: Context) -> dict:
    """The customer's cards: `product_id` (what an action needs), type, last 4 digits, currency,
    balance and `status` as it is now (Active, Blocked, Cancelled, Closed or Suspended). Card
    numbers come masked. Call it before proposing anything about a card."""
    customer_id = require_sign_in(ctx)
    return {"cards": await fetch_cards(customer_id)}


@mcp.tool
async def recent_charges(
    ctx: Context, merchant: str | None = None, days: int = 30, limit: int = 8
) -> dict:
    """The customer's recent purchases, newest first: `transaction_id` (what an inquiry needs),
    date, merchant, amount, currency and status. `merchant` filters by part of the name. Call it
    to find the id of a charge the customer talks about. If several look alike, ask which one."""
    customer_id = require_sign_in(ctx)
    days, limit = max(1, min(days, 365)), max(1, min(limit, 20))
    found = await fetch_recent_charges(
        customer_id, (merchant or "").strip()[:60] or None, days, limit
    )
    return {"charges": found, "count": len(found)}


@mcp.tool
async def propose_actions(ctx: Context, actions: Requested) -> dict:
    """Propose what the customer asked for. Nothing happens yet: the code checks each action and
    the customer confirms it with a button. Call this ONCE with everything they asked (at most 3).
    `actions` is always a LIST of objects, even for a single action.

    Actions and their params:
    - block_card {product_id}: block a card temporarily.
    - cancel_card {product_id}: cancel a card for good.
    - open_payment_inquiry {transaction_id, note?}: open an inquiry about a charge; `note` is the
      customer's own words, short.
    - request_callback {window: morning|afternoon|evening}: a person calls the customer.
    - set_alert {kind: duplicate_charge|payment_due, enabled: true|false}.
    - send_summary_email {topic: balances|payment_status|case_receipt}: `case_receipt` only
      together with open_payment_inquiry in the same call.
    For anything else the customer asks to do (a transfer, a payment, a refund, a new card, a
    limit, changing phone or email), propose it under its plain name (transfer_money,
    make_payment, refund, reissue_card, raise_limit, change_phone, change_email): the code answers
    it, it is never done by you.

    Returns each item with its `status`: awaiting_confirmation, refused or escalated, and the text
    to tell the customer. NOTHING is done until the customer confirms: never say it was.
    """
    customer_id = require_sign_in(ctx)
    language = session_meta(ctx, "language", "es")
    return await build_gateway().propose(
        customer_id,
        [a.model_dump() for a in actions],
        language=language if language in LANGUAGES else "es",
        conversation_id=session_meta(ctx, "thread_id"),
    )


if __name__ == "__main__":
    mcp.run()
