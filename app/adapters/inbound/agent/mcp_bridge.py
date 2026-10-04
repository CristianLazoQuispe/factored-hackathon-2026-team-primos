"""Expose a skill's MCP tools to LangChain, injecting the session customer via MCP `meta`.

langchain-mcp-adapters does not support mcp 2.x, and the bridge is this small. Each MCP tool
becomes a StructuredTool, so LangChain callbacks (Langfuse) trace every call.
"""

import json

from fastmcp import Client, FastMCP
from langchain_core.tools import StructuredTool

from app.adapters.inbound.mcp.accounts import mcp as accounts
from app.adapters.inbound.mcp.actions import mcp as actions
from app.adapters.inbound.mcp.dwh import mcp as dwh
from app.adapters.inbound.mcp.investigation import mcp as investigation

SERVERS: dict[str, FastMCP] = {
    "accounts": accounts,
    "actions": actions,
    "investigation": investigation,
    "dwh": dwh,
}


def client_for(server: str) -> Client:
    return Client(SERVERS[server])


async def load_tools(
    client: Client, customer_id: str, session: dict[str, str] | None = None
) -> list[StructuredTool]:
    """`session` is more of what the code knows about this conversation (see `session_meta`)."""

    def make(name: str):
        async def call(**arguments) -> str:
            result = await client.call_tool(
                name,
                arguments,
                meta={**(session or {}), "customer_id": customer_id},
                raise_on_error=False,
            )
            if result.is_error:
                return f"Tool error: {result.content[0].text}"
            return json.dumps(result.structured_content or result.data, ensure_ascii=False)

        return call

    return [
        StructuredTool(
            name=tool.name,
            description=tool.description or "",
            args_schema=tool.input_schema,
            coroutine=make(tool.name),
        )
        for tool in await client.list_tools()
    ]
