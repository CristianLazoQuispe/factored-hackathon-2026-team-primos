"""MCP server for the `balance_inquiry` skill.

python -m app.adapters.inbound.mcp.accounts   # stdio, e.g. for MCP Inspector
"""

from fastmcp import Context, FastMCP

from app.adapters.inbound.mcp import session_customer
from app.adapters.outbound.postgres.accounts import fetch_balances

mcp = FastMCP("accounts")


@mcp.tool
async def get_balances(ctx: Context, product_type: str | None = None) -> list[dict]:
    """Balances of the authenticated customer's products.

    product_type filters to one type: "Cuenta Ahorro", "Cuenta Corriente", "Tarjeta Crédito",
    "Tarjeta Débito", "Préstamo Personal", "Préstamo Hipotecario", "Inversión", "Seguro".
    Omit it to get every product. Card and account numbers come masked (last 4 digits).
    """
    return await fetch_balances(session_customer(ctx), product_type)


if __name__ == "__main__":
    mcp.run()
