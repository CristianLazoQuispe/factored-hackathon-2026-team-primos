"""MCP server for the `charge_investigation` skill.

python -m app.adapters.inbound.mcp.investigation   # stdio, e.g. for MCP Inspector
"""

from typing import Annotated

from fastmcp import Context, FastMCP
from pydantic import Field

from app.adapters.inbound.mcp import session_customer
from app.adapters.outbound.postgres.audit import record_decision
from app.adapters.outbound.postgres.investigation import PostgresWarehouse
from app.application.investigate import investigate_charge as investigate
from app.application.investigate import investigate_matching

mcp = FastMCP("investigation")
warehouse = PostgresWarehouse()


@mcp.tool
async def search_transactions(
    ctx: Context,
    days: Annotated[int, Field(ge=1, le=90)] = 30,
    merchant: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
) -> list[dict]:
    """Find the authenticated customer's own charges, newest first (at most 20).

    days counts back from the customer's latest transaction. merchant is a case-insensitive
    substring ("uber"). min_amount / max_amount bound the charge amount in its own currency.
    """
    return await warehouse.search(session_customer(ctx), days, merchant, min_amount, max_amount)


@mcp.tool
async def investigate_charges(
    ctx: Context,
    days: Annotated[int, Field(ge=1, le=90)] = 30,
    merchant: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
) -> dict:
    """Start here when the customer does not recognize a charge. Finds their own charges that fit
    what they said (at most 3, newest first, called #1, #2, #3) and checks the bank's records for
    each: twin (duplicate) charge, pending or reversed status, foreign purchase. Read-only.

    Set merchant whenever the customer names a store or service (merchant="uber"). days counts
    back from the customer's latest transaction. `findings` lists each verified fact once.
    A charge whose check could not run is counted in `not_checked` or listed in its `unavailable`:
    that is unknown, never "no".
    """
    customer_id = session_customer(ctx)
    report = await investigate_matching(
        warehouse, customer_id, days, merchant, min_amount, max_amount
    )
    await record_decision(
        "investigate_charges",
        {"customer_id": customer_id, "merchant": merchant, "days": days},
        "allowed",
        f"charges={report['count']} not_checked={report['not_checked']}",
        executed=True,
    )
    return report


@mcp.tool
async def investigate_charge(ctx: Context, transaction_id: str) -> dict:
    """Check the bank's own records for one charge: twin (duplicate) charge, pending or reversed
    status, and foreign-purchase / FX reference. Read-only.

    Anything listed in `unavailable` could not be checked: treat it as unknown, never as "no".
    """
    customer_id = session_customer(ctx)
    report = await investigate(warehouse, customer_id, transaction_id)
    found = "error" not in report
    await record_decision(
        "investigate_charge",
        {"customer_id": customer_id, "transaction_id": transaction_id},
        "allowed" if found else "blocked",
        report.get("error") or f"unavailable={report['unavailable']}",
        executed=found,
    )
    return report


if __name__ == "__main__":
    mcp.run()
