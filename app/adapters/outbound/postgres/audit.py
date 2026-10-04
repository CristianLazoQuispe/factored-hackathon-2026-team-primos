"""Append one row to `ops.decision_log` for each tool decision. Best effort: an audit failure is
logged and never breaks the customer's turn."""

import logging
import uuid

import psycopg
from psycopg.types.json import Jsonb

from app.config import get_settings

log = logging.getLogger(__name__)

INSERT = """
    INSERT INTO ops.decision_log
        (tool, proposed, policy_decision, policy_reason, executed, verified, conversation_id)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
"""


def _uuid_or_none(value: str | None) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None  # a thread id that is not a UUID is still worth a row, just not linked


async def record_decision(
    tool: str,
    proposed: dict,
    decision: str,
    reason: str | None,
    executed: bool,
    *,
    verified: bool = False,
    conversation_id: str | None = None,
) -> None:
    try:
        async with await psycopg.AsyncConnection.connect(get_settings().database_url) as conn:
            await conn.execute(
                INSERT,
                (
                    tool,
                    Jsonb(proposed),
                    decision,
                    reason,
                    executed,
                    verified,
                    _uuid_or_none(conversation_id),
                ),
            )
    except Exception:
        log.exception("decision_log write failed for %s", tool)
