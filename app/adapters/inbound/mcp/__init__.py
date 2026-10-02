"""MCP servers, one per skill. Tools never take customer_id as an argument.

The agent passes the authenticated customer in the MCP request `meta`; tools read it with
`session_customer(ctx)`, so the LLM can neither see nor change whose data is accessed.
"""

from fastmcp import Context
from fastmcp.exceptions import ToolError


def session_customer(ctx: Context) -> str:
    customer_id = (ctx.request_context.meta or {}).get("customer_id")
    if not customer_id:
        raise ToolError("No authenticated customer in this session.")
    return customer_id
