"""Postgres side of the action gateway: where actions are kept, the bank facts the policy reads,
and the effects the gateway applies and then reads back.

The bank's own tables (`core`) are never written: a card the customer blocks or cancels is a row
in `ops.card_actions`, laid over the bank's status when it is read. Every statement filters by
customer inside the query, so an id that belongs to someone else finds nothing.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime
from functools import cache
from typing import Any, Literal

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.adapters.outbound.mailer import Mailer, get_mailer
from app.adapters.outbound.postgres import query
from app.adapters.outbound.postgres.audit import record_decision
from app.adapters.outbound.postgres.investigation import DUPLICATE
from app.application.actions import (
    ActionGateway,
    CaseDraft,
    EmailDraft,
    PermanentError,
    SendReceipt,
    TransientError,
)
from app.config import get_settings
from app.domain.action_text import mask_email
from app.domain.actions import ActionRecord, CardFacts, TxFacts
from app.domain.evidence import DUPLICATE_WINDOW_SECONDS

log = logging.getLogger(__name__)
AS_OF_TTL_SECONDS = 600

# What the customer's own control does to the bank's status: freeze, cancel or unfreeze.
CONTROL_STATUS = {"freeze": "Blocked", "cancel": "Cancelled", "unfreeze": "Active"}
LATEST_CONTROL = """
    LEFT JOIN LATERAL (
        SELECT c.action FROM ops.card_actions c
        WHERE c.product_id = p.product_id
        ORDER BY c.requested_at DESC, c.action_id DESC LIMIT 1
    ) ca ON true
"""
CARD = f"""
    SELECT p.product_id, p.product_type, p.product_number_last4 AS last4, p.currency,
           p.current_balance AS balance, p.days_past_due, p.product_status AS bank_status,
           ca.action AS control
    FROM core.products p {LATEST_CONTROL}
    WHERE p.product_id = %(product_id)s AND p.customer_id = %(customer_id)s
"""
TRANSACTION = """
    SELECT t.transaction_id, t.product_id, t.transaction_status AS status,
           t.transaction_type AS kind, t.amount, t.currency, t.merchant_name AS merchant,
           t.transaction_country AS country, t.transaction_date AS occurred_at,
           coalesce(t.is_fraud, false) AS is_fraud, t.fraud_score, c.country AS customer_country
    FROM core.transactions t JOIN core.customers c ON c.customer_id = t.customer_id
    WHERE t.customer_id = %(customer_id)s AND t.transaction_id = %(transaction_id)s
"""
EMAIL = "SELECT email FROM core.customers WHERE customer_id = %(customer_id)s"
PRODUCTS = f"""
    SELECT p.product_type, p.product_number_last4 AS last4, p.current_balance AS balance,
           p.currency, p.credit_limit AS "limit"
    FROM core.products p {LATEST_CONTROL}
    WHERE p.customer_id = %(customer_id)s AND p.product_status IN ('Active', 'Blocked')
      AND coalesce(ca.action, '') <> 'cancel'
    ORDER BY p.product_type, p.product_number_last4
"""
BILLING = f"""
    SELECT p.product_type, p.product_number_last4 AS last4, p.currency, b.due_date,
           b.minimum_payment, b.past_due_amount
    FROM core.billing b JOIN core.products p ON p.product_id = b.product_id {LATEST_CONTROL}
    WHERE b.customer_id = %(customer_id)s AND p.product_status IN ('Active', 'Blocked')
      AND coalesce(ca.action, '') <> 'cancel'
    ORDER BY b.due_date, p.product_type
"""
AS_OF = "SELECT max(transaction_date)::date AS as_of FROM core.transactions"

COLUMNS = (
    "action_id, batch_id, position, customer_id, conversation_id, action, params, view, decision, "
    "reason, status, language, idempotency_key, attempts, result, created_at, expires_at, "
    "confirmed_at, finished_at"
)
INSERT = f"""
    INSERT INTO ops.actions ({COLUMNS})
    VALUES (%(action_id)s, %(batch_id)s, %(position)s, %(customer_id)s, %(conversation_id)s,
            %(action)s, %(params)s, %(view)s, %(decision)s, %(reason)s, %(status)s, %(language)s,
            %(idempotency_key)s, %(attempts)s, %(result)s, %(created_at)s, %(expires_at)s,
            %(confirmed_at)s, %(finished_at)s)
"""
OWN_AWAITING = """
    WHERE batch_id = %(batch_id)s AND customer_id = %(customer_id)s
      AND status = 'awaiting_confirmation'
"""
OUTBOX_UPSERT = """
    INSERT INTO ops.outbox (customer_id, action_id, channel, destination, delivered_to, template,
                            language, subject, body, mode, status, attempts)
    VALUES (%(customer_id)s, %(action_id)s, 'email', %(destination)s, %(delivered_to)s,
            %(template)s, %(language)s, %(subject)s, %(body)s, %(mode)s, 'queued', 1)
    ON CONFLICT (action_id) WHERE action_id IS NOT NULL
    DO UPDATE SET attempts = ops.outbox.attempts + 1, delivered_to = EXCLUDED.delivered_to
    RETURNING message_id, status, mode, delivered_to
"""

_as_of_cache: tuple[float, date] | None = None


@asynccontextmanager
async def _conn() -> AsyncIterator[psycopg.AsyncConnection]:
    """A connection; a database that is down or busy is worth retrying, so it says so."""
    try:
        async with await psycopg.AsyncConnection.connect(
            get_settings().database_url, row_factory=dict_row
        ) as conn:
            yield conn
    except psycopg.OperationalError as error:
        raise TransientError(type(error).__name__) from error


def _uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _record(row: dict[str, Any]) -> ActionRecord:
    return ActionRecord(
        **{**row, "action_id": str(row["action_id"]), "batch_id": str(row["batch_id"])}
    )


class PostgresStore:
    async def insert(self, records: list[ActionRecord]) -> None:
        async with _conn() as conn, conn.transaction():
            for r in records:
                await conn.execute(
                    INSERT,
                    {
                        **r.__dict__,
                        "params": Jsonb(r.params),
                        "view": Jsonb(r.view),
                        "result": Jsonb(r.result) if r.result is not None else None,
                    },
                )

    async def batch(self, batch_id: str, customer_id: str) -> list[ActionRecord]:
        if _uuid(batch_id) is None:
            return []
        async with _conn() as conn:
            cursor = await conn.execute(
                f"SELECT {COLUMNS} FROM ops.actions "
                "WHERE batch_id = %s AND customer_id = %s ORDER BY position",
                (batch_id, customer_id),
            )
            return [_record(row) for row in await cursor.fetchall()]

    async def _update(self, sql: str, params: dict[str, Any]) -> int:
        async with _conn() as conn:
            return (await conn.execute(sql, params)).rowcount

    async def claim(self, batch_id: str, customer_id: str, now: datetime) -> int:
        """Awaiting to confirmed in one statement, so two requests cannot both win."""
        return await self._update(
            "UPDATE ops.actions SET status = 'confirmed', confirmed_at = %(now)s "
            + OWN_AWAITING
            + " AND expires_at > %(now)s",
            {"batch_id": batch_id, "customer_id": customer_id, "now": now},
        )

    async def expire(self, batch_id: str, customer_id: str, now: datetime) -> int:
        return await self._update(
            "UPDATE ops.actions SET status = 'expired', finished_at = %(now)s " + OWN_AWAITING,
            {"batch_id": batch_id, "customer_id": customer_id, "now": now},
        )

    async def cancel(self, batch_id: str, customer_id: str) -> int:
        return await self._update(
            "UPDATE ops.actions SET status = 'cancelled', finished_at = now() " + OWN_AWAITING,
            {"batch_id": batch_id, "customer_id": customer_id},
        )

    async def mark(
        self,
        action_id: str,
        status: str,
        *,
        reason: str | None = None,
        attempts: int | None = None,
        result: dict[str, Any] | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        sets, params = ["status = %(status)s"], {"action_id": action_id, "status": status}
        if reason is not None or status == "verified":
            sets.append("reason = %(reason)s")
            params["reason"] = reason
        if attempts is not None:
            sets.append("attempts = %(attempts)s")
            params["attempts"] = attempts
        if result is not None:
            sets.append("result = %(result)s")
            params["result"] = Jsonb(result)
        if finished_at is not None:
            sets.append("finished_at = %(finished_at)s")
            params["finished_at"] = finished_at
        await self._update(
            f"UPDATE ops.actions SET {', '.join(sets)} WHERE action_id = %(action_id)s", params
        )


class PostgresFacts:
    async def card(self, customer_id: str, product_id: str) -> CardFacts | None:
        rows = await query(CARD, {"customer_id": customer_id, "product_id": product_id})
        if not rows:
            return None
        row = rows[0]
        status = CONTROL_STATUS.get(row["control"], row["bank_status"])
        return CardFacts(
            product_id=row["product_id"],
            product_type=row["product_type"],
            last4=row["last4"],
            status=status,
            frozen_by_customer=row["control"] == "freeze",
            currency=row["currency"],
            balance=row["balance"],
            days_past_due=row["days_past_due"],
        )

    async def transaction(self, customer_id: str, transaction_id: str) -> TxFacts | None:
        params = {"customer_id": customer_id, "transaction_id": transaction_id}
        rows = await query(TRANSACTION, params)
        if not rows:
            return None
        row = rows[0]
        twin = await query(DUPLICATE, {**params, "window": DUPLICATE_WINDOW_SECONDS})
        return TxFacts(
            transaction_id=row["transaction_id"],
            product_id=row["product_id"],
            status=row["status"],
            kind=row["kind"],
            amount=row["amount"],
            currency=row["currency"],
            merchant=row["merchant"],
            country=row["country"],
            occurred_at=row["occurred_at"],
            is_fraud=bool(row["is_fraud"]),
            fraud_score=row["fraud_score"],
            duplicates=len(twin),
            customer_country=row["customer_country"],
            as_of=await self.as_of(),
        )

    async def email_masked(self, customer_id: str) -> str | None:
        rows = await query(EMAIL, {"customer_id": customer_id})
        return mask_email(rows[0]["email"]) if rows else None

    async def products(self, customer_id: str) -> list[dict[str, Any]]:
        return await query(PRODUCTS, {"customer_id": customer_id})

    async def billing(self, customer_id: str) -> list[dict[str, Any]]:
        return await query(BILLING, {"customer_id": customer_id})

    async def as_of(self) -> date:
        """The dataset's last day. It only changes when the data is reloaded, so it is cached."""
        global _as_of_cache
        if _as_of_cache and time.monotonic() - _as_of_cache[0] < AS_OF_TTL_SECONDS:
            return _as_of_cache[1]
        found: date = (await query(AS_OF, {}))[0]["as_of"]
        _as_of_cache = (time.monotonic(), found)
        return found


class PostgresEffects:
    def __init__(self, mailer: Mailer):
        self.mailer = mailer
        self._facts = PostgresFacts()

    def inboxes(self) -> list[str]:
        return self.mailer.choices()

    async def card_control(
        self,
        customer_id: str,
        product_id: str,
        control: Literal["freeze", "cancel"],
        action_id: str,
    ) -> None:
        async with _conn() as conn:
            await conn.execute(  # the join to core.products is the ownership check
                "INSERT INTO ops.card_actions (action_id, product_id, customer_id, action) "
                "SELECT %(action_id)s, p.product_id, p.customer_id, %(control)s "
                "FROM core.products p "
                "WHERE p.product_id = %(product_id)s AND p.customer_id = %(customer_id)s "
                "ON CONFLICT (action_id) DO NOTHING",
                {
                    "action_id": action_id, "control": control,
                    "product_id": product_id, "customer_id": customer_id,
                },
            )  # fmt: skip

    async def card_status(self, customer_id: str, product_id: str) -> str | None:
        card = await self._facts.card(customer_id, product_id)
        return card.status if card else None

    async def confirm_card(self, action_id: str) -> None:
        async with _conn() as conn:
            await conn.execute(
                "UPDATE ops.card_actions SET verified_at = now() "
                "WHERE action_id = %s AND verified_at IS NULL",
                (action_id,),
            )

    async def open_case(self, draft: CaseDraft) -> str:
        """A dispute (for a charge) and the case a person picks up. Running it twice is harmless."""
        ref = "Q-" + draft.case_id.replace("-", "")[:8].upper()
        case_file = {
            **draft.case_file,
            "case_ref": ref,
            "priority": draft.priority,
            "sla_due_at": draft.sla_due_at.isoformat(),
        }
        async with _conn() as conn, conn.transaction():
            dispute = None
            if draft.kind == "payment_inquiry":
                dispute = draft.case_id
                await conn.execute(
                    "INSERT INTO ops.disputes (dispute_id, customer_id, transaction_id, "
                    "investigation_result, status, sla_due_at, tracking_token) "
                    "VALUES (%s, %s, %s, %s, 'open', %s, %s) ON CONFLICT (dispute_id) DO NOTHING",
                    (dispute, draft.customer_id, draft.transaction_id, Jsonb(case_file),
                     draft.sla_due_at, ref),
                )  # fmt: skip
            await conn.execute(
                "INSERT INTO ops.handoff_cases (case_id, customer_id, dispute_id, priority, "
                "reason_codes, case_file, status) VALUES (%s, %s, %s, %s, %s, %s, 'open') "
                "ON CONFLICT (case_id) DO NOTHING",
                (draft.case_id, draft.customer_id, dispute, draft.priority, draft.reason_codes,
                 Jsonb(case_file)),
            )  # fmt: skip
        return draft.case_id

    async def read_case(self, customer_id: str, case_id: str) -> dict[str, Any] | None:
        async with _conn() as conn:
            cursor = await conn.execute(
                "SELECT status, priority, reason_codes FROM ops.handoff_cases "
                "WHERE case_id = %s AND customer_id = %s",
                (case_id, customer_id),
            )
            return await cursor.fetchone()

    async def set_preference(self, customer_id: str, key: str, value: bool) -> None:
        async with _conn() as conn:
            await conn.execute(
                "INSERT INTO ops.preferences (customer_id, key, value) VALUES (%s, %s, %s) "
                "ON CONFLICT (customer_id, key) DO UPDATE SET value = EXCLUDED.value, "
                "updated_at = now()",
                (customer_id, key, Jsonb(value)),
            )

    async def get_preference(self, customer_id: str, key: str) -> bool | None:
        async with _conn() as conn:
            cursor = await conn.execute(
                "SELECT value FROM ops.preferences WHERE customer_id = %s AND key = %s",
                (customer_id, key),
            )
            row = await cursor.fetchone()
        return row["value"] if row else None

    async def send_email(self, draft: EmailDraft, inbox: str | None) -> SendReceipt:
        """Store the message, hand it to the mailer, and record what the mailer answered. A message
        already accepted for this action is never sent again."""
        to = self.mailer.resolve(inbox)
        delivered = mask_email(to) if to else None
        async with _conn() as conn:
            cursor = await conn.execute(
                OUTBOX_UPSERT,
                {
                    "customer_id": draft.customer_id, "action_id": draft.action_id,
                    "destination": draft.to_masked, "delivered_to": delivered,
                    "template": draft.template, "language": draft.language,
                    "subject": draft.subject, "body": draft.body, "mode": self.mailer.mode,
                },
            )  # fmt: skip
            row = await cursor.fetchone()
        message_id = str(row["message_id"])
        if row["status"] == "accepted":
            return SendReceipt(message_id, "accepted", row["mode"], row["delivered_to"])
        try:
            reply = await asyncio.to_thread(self.mailer.send, draft, to)
        except TransientError as error:
            await self._settle(message_id, "queued", str(error))
            raise
        except PermanentError as error:
            await self._settle(message_id, "failed", error.reason)
            raise
        await self._settle(message_id, "accepted", reply)
        return SendReceipt(message_id, "accepted", self.mailer.mode, delivered)

    async def _settle(self, message_id: str, status: str, reply: str) -> None:
        async with _conn() as conn:
            await conn.execute(
                "UPDATE ops.outbox SET status = %s, provider_reply = %s, "
                "sent_at = CASE WHEN %s = 'accepted' THEN now() ELSE sent_at END "
                "WHERE message_id = %s",
                (status, reply, status, int(message_id)),
            )

    async def message_status(self, customer_id: str, message_id: str) -> str | None:
        async with _conn() as conn:
            cursor = await conn.execute(
                "SELECT status FROM ops.outbox WHERE message_id = %s AND customer_id = %s",
                (int(message_id), customer_id),
            )
            row = await cursor.fetchone()
        return row["status"] if row else None


async def recent_messages(customer_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """What the system sent this customer, newest first: the simulated phone in the demo."""
    return await query(
        "SELECT message_id, channel, destination, delivered_to, subject, body, language, mode, "
        "status, created_at FROM ops.outbox WHERE customer_id = %(customer_id)s "
        "ORDER BY created_at DESC, message_id DESC LIMIT %(limit)s",
        {"customer_id": customer_id, "limit": limit},
    )


async def audit_action(
    *,
    tool: str,
    proposed: dict[str, Any],
    verdict: str,
    reason: str | None,
    executed: bool,
    verified: bool,
    conversation_id: str | None = None,
) -> None:
    await record_decision(
        tool,
        proposed,
        verdict,
        reason,
        executed,
        verified=verified,
        conversation_id=conversation_id,
    )


@cache
def build_gateway() -> ActionGateway:
    return ActionGateway(
        store=PostgresStore(),
        facts=PostgresFacts(),
        effects=PostgresEffects(get_mailer()),
        audit=audit_action,
    )
