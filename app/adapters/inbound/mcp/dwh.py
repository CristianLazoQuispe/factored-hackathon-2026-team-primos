"""MCP server for the `data_lookup` skill. The usual questions (movements, spending, complaints,
exchange rate) have a tool with reviewed SQL; for the rest the agent writes SQL and code decides
what it can see.

python -m app.adapters.inbound.mcp.dwh   # stdio, e.g. for MCP Inspector
"""

from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from fastmcp import Context, FastMCP
from pydantic import Field

from app.adapters.inbound.mcp import session_customer
from app.adapters.outbound.postgres.audit import record_decision
from app.adapters.outbound.postgres.readonly import ReadOnlyPostgres
from app.adapters.outbound.postgres.spending import PostgresSpending
from app.application.run_sql import run_scoped_sql
from app.application.spending import spending_summary
from app.domain.accounts import present
from app.domain.spending import complaints_summary

mcp = FastMCP("dwh")
db = ReadOnlyPostgres()
store = PostgresSpending()
CATALOG = (Path(__file__).parent / "dwh_catalog.md").read_text()
Days = Annotated[int, Field(ge=1, le=365)]
Currency = Literal["USD", "MXN", "COP", "ARS"]
ProductType = Literal[
    "Cuenta Ahorro",
    "Cuenta Corriente",
    "Tarjeta Crédito",
    "Tarjeta Débito",
    "Préstamo Personal",
    "Préstamo Hipotecario",
    "Inversión",
    "Seguro",
]


@mcp.tool
async def get_movements(
    ctx: Context,
    days: Days = 30,
    product_type: ProductType | None = None,
    last4: str | None = None,
    transaction_type: Literal[
        "Purchase", "Payment", "Transfer", "Deposit", "Withdrawal", "Adjustment"
    ]
    | None = None,
    status: Literal["Approved", "Declined", "Pending", "Reversed"] | None = None,
    merchant: str | None = None,
    category: Literal["Food", "Transport", "Services", "Entertainment", "Health", "Other"]
    | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    order: Literal["newest", "largest"] = "newest",
    limit: Annotated[int, Field(ge=1, le=50)] = 20,
) -> dict:
    """The authenticated customer's movements (purchases, payments, transfers, deposits,
    withdrawals) on their accounts and cards. Use it for "my last movements", "my purchases at
    X", "my biggest purchases", "movements of my credit card".

    days counts back from the customer's latest transaction. product_type or last4 (the last 4
    digits) narrow to one account or card. merchant is a case-insensitive substring ("uber").
    order="largest" sorts by amount. `truncated` true means there are more than `limit`.
    Amounts are in each movement's own currency: never add different currencies.
    """
    customer_id = session_customer(ctx)
    filters = {
        "days": days,
        "product_type": product_type,
        "last4": last4,
        "transaction_type": transaction_type,
        "status": status,
        "merchant": merchant,
        "category": category,
        "min_amount": min_amount,
        "max_amount": max_amount,
    }
    rows = await store.movements(customer_id, limit + 1, largest=order == "largest", **filters)
    await record_decision(
        "get_movements",
        {"customer_id": customer_id} | present(filters),
        "allowed",
        f"count={len(rows[:limit])}",
        executed=True,
    )
    return {
        "count": len(rows[:limit]),
        "truncated": len(rows) > limit,
        "movements": [present(row) for row in rows[:limit]],
        "evidence_lookup": "get_movements",
    }


@mcp.tool
async def get_spending_summary(ctx: Context, days: Days = 30) -> dict:
    """How much the authenticated customer spent (Approved purchases) in the last `days`, counted
    back from their latest transaction. One block per currency in `currencies`: `spend`,
    `previous_spend` (the same number of days before) and `change_pct`, `transactions`,
    `tx_per_week`, `avg_ticket`, `max_ticket`, `by_category`, `top_merchants` (5), `monthly` and
    `foreign` (purchases outside the customer's country). Use it for "how much did I spend",
    "what do I spend the most on", "where do I spend the most", "compared with before".

    A figure that is absent, or listed in `unavailable`, is unknown: never read it as zero.
    """
    customer_id = session_customer(ctx)
    summary = await spending_summary(store, customer_id, days)
    await record_decision(
        "get_spending_summary",
        {"customer_id": customer_id, "days": days},
        "allowed",
        f"unavailable={summary['unavailable']}",
        executed=True,
    )
    return summary


@mcp.tool
async def get_complaints(ctx: Context) -> dict:
    """The complaints, claims, requests and suggestions the authenticated customer filed: `count`,
    how many are still `open`, `by_status`, and the `latest` ones (newest first) with type,
    category, status, priority and dates."""
    customer_id = session_customer(ctx)
    rows = await store.complaints(customer_id)
    summary = complaints_summary([present(row) for row in rows])
    await record_decision(
        "get_complaints", {"customer_id": customer_id}, "allowed", f"count={len(rows)}", True
    )
    return summary | {"evidence_lookup": "get_complaints"}


@mcp.tool
async def get_exchange_rate(
    ctx: Context, source: Currency, target: Currency, on: date | None = None
) -> dict:
    """The bank's reference exchange rate: 1 `source` = `exchange_rate` `target`, with the buy and
    sell rates. `on` (YYYY-MM-DD) gives the rate of that day or the closest earlier one; omit it
    for the latest. `found` false means there is no rate for that pair and date."""
    customer_id = session_customer(ctx)
    rate = await store.exchange_rate(source, target, on)
    await record_decision(
        "get_exchange_rate",
        {"customer_id": customer_id, "source": source, "target": target},
        "allowed",
        None,
        executed=True,
    )
    return (
        {"found": rate is not None} | present(rate or {}) | {"evidence_lookup": "get_exchange_rate"}
    )


@mcp.tool
def describe_schema() -> str:
    """The tables and columns you may query, with the data quirks to know. Call it once first."""
    return CATALOG


@mcp.tool
async def run_sql(ctx: Context, sql: str) -> dict:
    """Run ONE read-only PostgreSQL SELECT over the tables from describe_schema.

    The result only contains the authenticated customer's rows. At most 100 rows come back
    (`truncated` tells you). If `error` is set the query did not run: fix it, or say you could not
    find out. An error is an unknown, never a zero.
    """
    customer_id = session_customer(ctx)
    result = await run_scoped_sql(db, customer_id, sql)
    await record_decision(
        "run_sql",
        {"customer_id": customer_id, "sql": sql},
        "blocked" if result.get("blocked") else "allowed",
        result.get("error"),
        executed="error" not in result,
    )
    return result


if __name__ == "__main__":
    mcp.run()
