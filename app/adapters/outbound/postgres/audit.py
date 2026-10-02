"""Append one row to `ops.decision_log` for each tool decision. Best effort: an audit failure is
logged and never breaks the customer's turn."""

import logging

import psycopg
from psycopg.types.json import Jsonb

from app.config import get_settings

log = logging.getLogger(__name__)

INSERT = """
    INSERT INTO ops.decision_log (tool, proposed, policy_decision, policy_reason, executed)
    VALUES (%s, %s, %s, %s, %s)
"""


async def record_decision(
    tool: str, proposed: dict, decision: str, reason: str | None, executed: bool
) -> None:
    try:
        async with await psycopg.AsyncConnection.connect(get_settings().database_url) as conn:
            await conn.execute(INSERT, (tool, Jsonb(proposed), decision, reason, executed))
    except Exception:
        log.exception("decision_log write failed for %s", tool)
