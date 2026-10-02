"""MCP server for the `data_lookup` skill: the agent writes SQL, code decides what it can see.

python -m app.adapters.inbound.mcp.dwh   # stdio, e.g. for MCP Inspector
"""

from pathlib import Path

from fastmcp import Context, FastMCP

from app.adapters.inbound.mcp import session_customer
from app.adapters.outbound.postgres.audit import record_decision
from app.adapters.outbound.postgres.readonly import ReadOnlyPostgres
from app.application.run_sql import run_scoped_sql

mcp = FastMCP("dwh")
db = ReadOnlyPostgres()
CATALOG = (Path(__file__).parent / "dwh_catalog.md").read_text()


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
