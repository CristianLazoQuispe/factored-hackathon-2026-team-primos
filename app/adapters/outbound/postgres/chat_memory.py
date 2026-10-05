"""The memory of the chat in Postgres: ops.conversations and ops.messages (see 003_chat_memory.sql).

Three rules hold in every function:
  * the customer is always in the WHERE: nobody reads or writes a conversation that is not theirs;
  * the id of a conversation is made from the customer and the thread, so a thread id someone else
    knows opens nothing of theirs;
  * saving is best effort: a failure is logged and the chat goes on, as the audit does.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

import psycopg

from app.adapters.outbound.postgres import query
from app.config import get_settings
from app.domain import chat_memory as rules
from app.domain.chat_memory import Past

log = logging.getLogger(__name__)

NAMESPACE = uuid.UUID("5d1b0a6e-3c52-4f0e-9c1a-71a6a7a96e04")  # fixed: the ids must not change

UPSERT_CONVERSATION = """
    INSERT INTO ops.conversations
        (conversation_id, channel, language, customer_id, title, skill, outcome, last_message_at)
    VALUES (%(id)s, %(channel)s, %(language)s, %(customer)s, %(title)s, %(skill)s,
            %(outcome)s, now())
    ON CONFLICT (conversation_id) DO UPDATE SET
        language = COALESCE(EXCLUDED.language, ops.conversations.language),
        skill = COALESCE(EXCLUDED.skill, ops.conversations.skill),
        outcome = COALESCE(EXCLUDED.outcome, ops.conversations.outcome),
        last_message_at = now()
    WHERE ops.conversations.customer_id = EXCLUDED.customer_id
"""

INSERT_MESSAGE = """
    INSERT INTO ops.messages (conversation_id, role, content, skill)
    SELECT %(id)s, %(role)s, %(content)s, %(skill)s
    WHERE EXISTS (SELECT 1 FROM ops.conversations
                  WHERE conversation_id = %(id)s AND customer_id = %(customer)s)
"""

LIST = """
    SELECT c.conversation_id::text AS conversation_id, c.title, c.skill, c.outcome, c.language,
           c.last_message_at,
           (SELECT count(*) FROM ops.messages m
             WHERE m.conversation_id = c.conversation_id) AS messages
    FROM ops.conversations c
    WHERE c.customer_id = %(customer)s AND c.last_message_at IS NOT NULL
    ORDER BY c.last_message_at DESC
    LIMIT %(limit)s
"""

READ_HEADER = """
    SELECT conversation_id::text AS conversation_id, title, skill, outcome, language,
           last_message_at
    FROM ops.conversations
    WHERE conversation_id = %(id)s AND customer_id = %(customer)s
"""

READ_MESSAGES = """
    SELECT role, content, skill, created_at
    FROM ops.messages
    WHERE conversation_id = %(id)s
    ORDER BY message_id
"""

PAST = """
    SELECT c.title, c.skill, c.outcome, c.last_message_at,
           (SELECT m.content FROM ops.messages m
             WHERE m.conversation_id = c.conversation_id AND m.role = 'customer'
             ORDER BY m.message_id DESC LIMIT 1) AS last_customer,
           (SELECT count(*) FROM ops.messages m
             WHERE m.conversation_id = c.conversation_id AND m.role = 'customer') AS turns
    FROM ops.conversations c
    WHERE c.customer_id = %(customer)s AND c.conversation_id <> %(exclude)s
      AND c.last_message_at IS NOT NULL
    ORDER BY c.last_message_at DESC
    LIMIT %(limit)s
"""


def conversation_id(customer_id: str, thread_id: str) -> uuid.UUID:
    """The same customer and thread always give the same id; another customer never does."""
    return uuid.uuid5(NAMESPACE, f"{customer_id}:{thread_id}")


async def record_turn(
    customer_id: str,
    thread_id: str,
    customer_text: str,
    reply_text: str,
    *,
    skill: str | None = None,
    outcome: str | None = None,
    language: str | None = None,
    channel: str = "web",
) -> bool:
    """Keep one turn: what the customer wrote and what the agent answered. False if it failed."""
    try:
        cid = conversation_id(customer_id, thread_id)
        async with await psycopg.AsyncConnection.connect(get_settings().database_url) as conn:
            await conn.execute(
                UPSERT_CONVERSATION,
                {
                    "id": cid,
                    "channel": channel,
                    "language": language,
                    "customer": customer_id,
                    "title": rules.title_of(customer_text) or None,
                    "skill": skill,
                    "outcome": outcome,
                },
            )
            for role, text in (("customer", customer_text), ("assistant", reply_text)):
                if text and text.strip():
                    params = {"id": cid, "customer": customer_id, "role": role}
                    params |= {
                        "content": rules.stored(text),
                        "skill": skill if role == "assistant" else None,
                    }
                    await conn.execute(INSERT_MESSAGE, params)
        return True
    except Exception:
        log.exception("chat memory: could not save a turn")
        return False


async def set_outcome(customer_id: str, thread_id: str, outcome: str) -> bool:
    """How the conversation ended, once the customer has confirmed or cancelled a card."""
    if outcome not in rules.OUTCOMES:
        return False
    try:
        async with await psycopg.AsyncConnection.connect(get_settings().database_url) as conn:
            await conn.execute(
                "UPDATE ops.conversations SET outcome = %s "
                "WHERE conversation_id = %s AND customer_id = %s",
                (outcome, conversation_id(customer_id, thread_id), customer_id),
            )
        return True
    except Exception:
        log.exception("chat memory: could not set the outcome")
        return False


async def list_conversations(
    customer_id: str, limit: int = rules.MAX_LISTED
) -> list[dict[str, Any]]:
    """The customer's earlier conversations, the most recent first."""
    rows = await query(LIST, {"customer": customer_id, "limit": min(limit, rules.MAX_LISTED)})
    return [
        {**r, "last_message_at": _iso(r["last_message_at"]), "messages": int(r["messages"])}
        for r in rows
    ]


async def read_conversation(customer_id: str, conversation: str) -> dict[str, Any] | None:
    """One conversation with its messages, or None if it does not exist or is not the customer's."""
    try:
        cid = uuid.UUID(str(conversation))
    except ValueError:
        return None
    header = await query(READ_HEADER, {"id": cid, "customer": customer_id})
    if not header:
        return None
    messages = await query(READ_MESSAGES, {"id": cid})
    head = header[0]
    return {
        **head,
        "last_message_at": _iso(head["last_message_at"]),
        "messages": [{**m, "created_at": _iso(m["created_at"])} for m in messages],
    }


async def past_for_agent(
    customer_id: str, thread_id: str, limit: int = rules.MAX_PAST
) -> list[Past]:
    """The last conversations other than this one, for the agent's summary. Never raises."""
    try:
        rows = await query(
            PAST,
            {
                "customer": customer_id,
                "exclude": conversation_id(customer_id, thread_id),
                "limit": min(limit, rules.MAX_PAST),
            },
        )
    except Exception:
        log.exception("chat memory: could not read the earlier conversations")
        return []
    return [
        Past(
            when=r["last_message_at"],
            title=r["title"] or "",
            last_customer=r["last_customer"] or "",
            skill=r["skill"],
            outcome=r["outcome"],
            turns=int(r["turns"]),
        )
        for r in rows
    ]


async def delete_history(customer_id: str) -> int:
    """Forget everything kept of this customer. Returns how many conversations went."""
    async with await psycopg.AsyncConnection.connect(get_settings().database_url) as conn:
        await conn.execute(
            "DELETE FROM ops.messages WHERE conversation_id IN "
            "(SELECT conversation_id FROM ops.conversations WHERE customer_id = %s)",
            (customer_id,),
        )
        done = await conn.execute(
            "DELETE FROM ops.conversations WHERE customer_id = %s", (customer_id,)
        )
        return done.rowcount


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
