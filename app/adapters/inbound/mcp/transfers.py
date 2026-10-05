"""MCP server for the `money_movement` skill (khipear): it proposes, it never executes.

There is no tool that moves money. `propose_transfer` and `propose_service_payment` store a
proposal; only the customer's Confirmar button (POST /api/khipu/confirm) executes it.

python -m app.adapters.inbound.mcp.transfers   # stdio, e.g. for MCP Inspector
"""

from typing import Annotated, Literal

from fastmcp import Context, FastMCP
from pydantic import Field

from app.adapters.inbound.mcp import session_customer
from app.adapters.outbound.postgres.audit import record_decision
from app.adapters.outbound.postgres.transfers import PostgresLedger
from app.application.transfers import (
    propose,
    service_bills,
    transfer_options,
)
from app.application.transfers import propose_service_payment as propose_payment
from app.config import get_settings
from app.domain.transfers import Kind, Limits, Service, said

mcp = FastMCP("transfers")
ledger = PostgresLedger()
Last4 = Annotated[str, Field(pattern=r"^\d{4}$")]
AccountType = Literal["Cuenta Ahorro", "Cuenta Corriente"]
OwnType = Literal[
    "Cuenta Ahorro",
    "Cuenta Corriente",
    "Tarjeta Crédito",
    "Préstamo Personal",
    "Préstamo Hipotecario",
]
DECISION = {
    "proposed": "needs_confirmation",
    "blocked": "blocked",
    "needs_clarification": "allowed",  # a question to the customer: nothing is proposed yet
}


def limits() -> Limits:
    settings = get_settings()
    return Limits(settings.khipu_limit_per_operation_usd, settings.khipu_limit_per_day_usd)


@mcp.tool
async def list_transfer_options(ctx: Context) -> dict:
    """The authenticated customer's accounts that can send money (`accounts`, with balance) and
    their credit cards and loans that can be paid (`debts`, with the amount owed). Numbers come
    masked (last 4 digits). Read-only."""
    customer_id = session_customer(ctx)
    options = await transfer_options(ledger, customer_id)
    await record_decision(
        "list_transfer_options",
        {"customer_id": customer_id},
        "allowed",
        f"accounts={len(options['accounts'])} debts={len(options['debts'])}",
        executed=True,
    )
    return options | {"evidence_lookup": "list_transfer_options"}


@mcp.tool
async def propose_transfer(
    ctx: Context,
    kind: Kind,
    amount: Annotated[float, Field(gt=0)],
    from_last4: Last4 | None = None,
    to_last4: Last4 | None = None,
    to_account_number: str | None = None,
    to_customer_id: str | None = None,
    from_type: AccountType | None = None,
    to_type: OwnType | None = None,
) -> dict:
    """Prepare a movement of the authenticated customer's money. It moves NOTHING: the customer
    confirms on their screen.

    kind: "own_accounts" (between their own accounts), "pay_debt" (pay their own credit card or
    loan) or "third_party" (to another customer of the bank).
    amount: in the currency of the origin account. Pass only what the customer said:
    from_last4: last 4 digits of the account the money leaves, if they said which.
    to_last4: last 4 digits of their own account, card or loan that receives it, if they said.
    from_type / to_type: the kind of product they named instead of its digits ("de mi cuenta de
    ahorro" -> from_type "Cuenta Ahorro"; "a mi tarjeta" -> to_type "Tarjeta Crédito").
    to_account_number / to_customer_id: for "third_party", exactly one of them.
    Never guess a value: leave it out and the result tells you what to ask.

    `status` is one of:
    - "needs_clarification": ask the customer the question in `ask`, listing `options`.
    - "blocked": it cannot be done; `detail` says why (`response_code` as a bank would answer).
    - "proposed": the customer now sees a card with `confirmation` and a Confirmar button.
    """
    customer_id = session_customer(ctx)
    # On the customer's first request the agent sends their words along (`said`). A product the
    # model names that they did not is dropped, so the result asks instead of acting on a guess.
    words = (ctx.request_context.meta or {}).get("said")
    if words is not None:
        from_last4 = from_last4 if said(words, last4=from_last4) else None
        to_last4 = to_last4 if said(words, last4=to_last4) else None
        from_type = from_type if said(words, product_type=from_type) else None
        to_type = to_type if said(words, product_type=to_type) else None
    result = await propose(
        ledger,
        limits(),
        customer_id,
        kind,
        amount,
        from_last4,
        to_last4,
        to_account_number,
        to_customer_id,
        from_type,
        to_type,
    )
    status = result["status"]
    await record_decision(
        "propose_transfer",
        {
            "customer_id": customer_id,
            "kind": kind,
            "amount": amount,
            "to_customer_id": to_customer_id,
            "transfer_id": result.get("confirmation", {}).get("transfer_id"),
        },
        DECISION[status],
        result.get("reason") or (f"asked: {result['missing']}" if "missing" in result else None),
        executed=False,
    )
    return result | {"evidence_lookup": "propose_transfer"}


@mcp.tool
async def list_service_bills(ctx: Context) -> dict:
    """The authenticated customer's pending service bills (`bills`: service, biller, reference,
    amount, currency and due date): electricity, water, phone, internet, cable TV. Read-only."""
    customer_id = session_customer(ctx)
    bills = await service_bills(ledger, customer_id)
    await record_decision(
        "list_service_bills",
        {"customer_id": customer_id},
        "allowed",
        f"bills={len(bills['bills'])}",
        executed=True,
    )
    return bills | {"evidence_lookup": "list_service_bills"}


@mcp.tool
async def propose_service_payment(
    ctx: Context,
    service: Service | None = None,
    from_last4: Last4 | None = None,
    from_type: AccountType | None = None,
) -> dict:
    """Prepare the payment of one of the authenticated customer's pending service bills from one
    of their accounts. It pays NOTHING: the customer confirms on their screen. The amount is the
    bill's, never one you pass.

    service: the one the customer named ("la luz" -> "luz", "el agua" -> "agua", "mi celular" ->
    "teléfono", "el wifi" -> "internet", "la tele" -> "cable"). Leave it out if they named none.
    from_last4 / from_type: the account that pays, only if the customer said which.

    `status` is "needs_clarification", "blocked" or "proposed", exactly as in `propose_transfer`.
    """
    customer_id = session_customer(ctx)
    words = (ctx.request_context.meta or {}).get("said")
    if words is not None:  # as in propose_transfer: what the customer did not say is dropped
        service = service if said(words, product_type=service) else None
        from_last4 = from_last4 if said(words, last4=from_last4) else None
        from_type = from_type if said(words, product_type=from_type) else None
    result = await propose_payment(ledger, customer_id, service, from_last4, from_type)
    status = result["status"]
    await record_decision(
        "propose_service_payment",
        {
            "customer_id": customer_id,
            "service": service,
            "transfer_id": result.get("confirmation", {}).get("transfer_id"),
        },
        DECISION[status],
        result.get("reason") or (f"asked: {result['missing']}" if "missing" in result else None),
        executed=False,
    )
    return result | {"evidence_lookup": "propose_service_payment"}


if __name__ == "__main__":
    mcp.run()
