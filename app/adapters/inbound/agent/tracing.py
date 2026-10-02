"""Langfuse tracing for the graph: every node, LLM call, skill choice and MCP tool call.

Enabled when LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are set; otherwise no callbacks.
Traces are masked in this process before they are sent: private customer fields, emails and
long numbers (cards, accounts, documents, phones) never reach Langfuse.
"""

import json
import os
import re
from functools import cache
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

PRIVATE_FIELDS = (  # the personal columns of core.customers
    "first_name",
    "last_name",
    "email",
    "mobile_phone",
    "document_number",
    "date_of_birth",
)
REDACTED = "<redacted>"
EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# 8+ digits, plain or split by spaces or dashes: cards, accounts, documents, phones.
# Timestamps, decimal amounts and IDs such as CLI-01OSDSMM4FX2 are left alone.
LONG_NUMBER = re.compile(r"(?<![\w.-])(?!\d{4}-\d\d-\d\d)\d(?:[ -]?\d){7,}(?![\w-]|[.,]\d)")
# a private field inside JSON text, as in a tool result: "first_name": "Ana"
FIELD_IN_TEXT = re.compile(rf'("(?:{"|".join(PRIVATE_FIELDS)})"\s*:\s*")(?:[^"\\]|\\.)*')


def _mask_text(text: str) -> str:
    text = FIELD_IN_TEXT.sub(rf"\g<1>{REDACTED}", text)
    text = EMAIL.sub("<email>", text)
    return LONG_NUMBER.sub(lambda m: "****" + re.sub(r"\D", "", m.group())[-4:], text)


def _mask_value(value: Any) -> Any:
    if isinstance(value, str):
        return _mask_text(value)
    if isinstance(value, list):
        return [_mask_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: REDACTED if key in PRIVATE_FIELDS and item is not None else _mask_value(item)
            for key, item in value.items()
        }
    return value


def mask(*, data: Any, **_: Any) -> Any:
    """Langfuse mask hook: runs on the input, output and metadata of every span before export."""
    from langfuse._utils.serializer import EventSerializer

    # LangChain messages and other objects become plain JSON first, so nothing is skipped
    return _mask_value(json.loads(json.dumps(data, cls=EventSerializer)))


@cache
def _start_masked_client() -> None:
    from langfuse import Langfuse

    Langfuse(mask=mask)  # CallbackHandler() takes this client, and its mask, with get_client()


def callbacks() -> list[BaseCallbackHandler]:
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        return []
    from langfuse.langchain import CallbackHandler

    _start_masked_client()
    return [CallbackHandler()]
