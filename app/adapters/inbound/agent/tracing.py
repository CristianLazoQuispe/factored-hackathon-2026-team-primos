"""Langfuse tracing for the graph: every node, LLM call, skill choice and MCP tool call.

Enabled when LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are set; otherwise no callbacks.
"""

import os

from langchain_core.callbacks import BaseCallbackHandler


def callbacks() -> list[BaseCallbackHandler]:
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        return []
    from langfuse.langchain import CallbackHandler

    return [CallbackHandler()]
