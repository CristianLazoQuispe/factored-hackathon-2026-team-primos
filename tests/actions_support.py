"""In-memory stand-ins for the action gateway's ports, with failure injection and a clock.

The store keeps the guarantees the Postgres one must keep (compare-and-set claim, ownership by
customer), so the state machine is tested without a database.
"""

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.application.actions import (
    ActionGateway,
    CaseDraft,
    EmailDraft,
    PermanentError,
    SendReceipt,
    TransientError,
)
from app.domain.actions import (
    AWAITING,
    CANCELLED,
    CONFIRMED,
    EXPIRED,
    ActionRecord,
    CardFacts,
    TxFacts,
)

AS_OF = date(2026, 6, 18)
T0 = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.value = T0

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **delta: int) -> None:
        self.value += timedelta(**delta)


def card(
    product_id: str = "CARD-1",
    *,
    product_type: str = "Tarjeta Crédito",
    status: str = "Active",
    balance: float = 0.0,
    days_past_due: int = 0,
    frozen_by_customer: bool = False,
) -> CardFacts:
    return CardFacts(
        product_id, product_type, "2951", status, frozen_by_customer, "MXN", balance, days_past_due
    )


def tx(
    transaction_id: str = "T1",
    *,
    status: str = "Approved",
    amount: float = 312.4,
    merchant: str = "Uber Trip",
    country: str = "México",
    is_fraud: bool = False,
    fraud_score: float = 5.0,
    duplicates: int = 1,
    age_days: int = 7,
) -> TxFacts:
    occurred = datetime.combine(AS_OF - timedelta(days=age_days), datetime.min.time())
    return TxFacts(
        transaction_id, "CARD-1", status, "Purchase", amount, "MXN", merchant, country, occurred,
        is_fraud, fraud_score, duplicates, "México", AS_OF,
    )  # fmt: skip


class MemoryStore:
    def __init__(self) -> None:
        self.rows: dict[str, ActionRecord] = {}

    async def insert(self, records: list[ActionRecord]) -> None:
        for record in records:
            self.rows[record.action_id] = deepcopy(record)

    async def batch(self, batch_id: str, customer_id: str) -> list[ActionRecord]:
        rows = [
            deepcopy(r)
            for r in self.rows.values()
            if r.batch_id == batch_id and r.customer_id == customer_id
        ]
        return sorted(rows, key=lambda r: r.position)

    def _move(
        self, batch_id: str, customer_id: str, to: str, *, now: datetime | None = None
    ) -> int:
        moved = 0
        for r in self.rows.values():
            if r.batch_id == batch_id and r.customer_id == customer_id and r.status == AWAITING:
                if to == CONFIRMED and now is not None and now >= r.expires_at:
                    continue
                self.rows[r.action_id] = replace(r, status=to)
                moved += 1
        return moved

    async def claim(self, batch_id: str, customer_id: str, now: datetime) -> int:
        return self._move(batch_id, customer_id, CONFIRMED, now=now)

    async def expire(self, batch_id: str, customer_id: str, now: datetime) -> int:
        return self._move(batch_id, customer_id, EXPIRED)

    async def cancel(self, batch_id: str, customer_id: str) -> int:
        return self._move(batch_id, customer_id, CANCELLED)

    async def supersede(self, customer_id: str, conversation_id: str, keep_batch_id: str) -> int:
        moved = 0
        for r in list(self.rows.values()):
            same = r.customer_id == customer_id and r.conversation_id == conversation_id
            if same and r.batch_id != keep_batch_id and r.status == AWAITING:
                self.rows[r.action_id] = replace(r, status=CANCELLED, reason="superseded")
                moved += 1
        return moved

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
        row = self.rows[action_id]
        row.status = status
        if reason is not None or status in ("verified",):
            row.reason = reason
        if attempts is not None:
            row.attempts = attempts
        if result is not None:
            row.result = result
        if finished_at is not None:
            row.finished_at = finished_at


class FakeFacts:
    def __init__(self) -> None:
        self.cards: dict[tuple[str, str], CardFacts] = {}
        self.txs: dict[tuple[str, str], TxFacts] = {}
        self.emails: dict[str, str | None] = {}
        self.product_rows: dict[str, list[dict[str, Any]]] = {}
        self.billing_rows: dict[str, list[dict[str, Any]]] = {}
        self.broken = False

    def _check(self) -> None:
        if self.broken:
            raise ConnectionError("database down")

    async def card(self, customer_id: str, product_id: str) -> CardFacts | None:
        self._check()
        return self.cards.get((customer_id, product_id))

    async def transaction(self, customer_id: str, transaction_id: str) -> TxFacts | None:
        self._check()
        return self.txs.get((customer_id, transaction_id))

    async def email_masked(self, customer_id: str) -> str | None:
        self._check()
        return self.emails.get(customer_id)

    async def products(self, customer_id: str) -> list[dict[str, Any]]:
        return self.product_rows.get(customer_id, [])

    async def billing(self, customer_id: str) -> list[dict[str, Any]]:
        return self.billing_rows.get(customer_id, [])

    async def as_of(self) -> date:
        return AS_OF


class FakeEffects:
    """Does what the real effects do, can be told to fail, and can lie about what it did."""

    def __init__(self, facts: FakeFacts) -> None:
        self.facts = facts
        self.calls: list[tuple[str, ...]] = []
        self.cases: dict[str, dict[str, Any]] = {}
        self.prefs: dict[tuple[str, str], bool] = {}
        self.sent: list[EmailDraft] = []
        self.inboxes_used: list[str | None] = []
        self.send_transient_failures = 0  # how many sends raise TransientError before one works
        self.send_permanent_failure = False
        self.silent_card = False  # card_control returns but changes nothing
        self.silent_case = False
        self.forget_messages = False  # the mail is accepted but cannot be found afterwards

    def inboxes(self) -> list[str]:
        return ["a@demo.test", "b@demo.test"]

    async def card_control(self, customer_id: str, product_id: str, control: str, action_id: str):
        self.calls.append(("card_control", customer_id, product_id, control))
        if self.silent_card:
            return
        current = self.facts.cards[(customer_id, product_id)]
        status = {"freeze": "Blocked", "cancel": "Cancelled"}[control]
        self.facts.cards[(customer_id, product_id)] = replace(
            current, status=status, frozen_by_customer=control == "freeze"
        )

    async def card_status(self, customer_id: str, product_id: str) -> str | None:
        found = self.facts.cards.get((customer_id, product_id))
        return found.status if found else None

    async def confirm_card(self, action_id: str) -> None:
        self.calls.append(("confirm_card", action_id))

    async def open_case(self, draft: CaseDraft) -> str:
        self.calls.append(("open_case", draft.customer_id, draft.kind))
        if not self.silent_case:
            self.cases[draft.case_id] = {
                "status": "open",
                "customer_id": draft.customer_id,
                "draft": draft,
            }
        return draft.case_id

    async def read_case(self, customer_id: str, case_id: str) -> dict[str, Any] | None:
        found = self.cases.get(case_id)
        return found if found and found["customer_id"] == customer_id else None

    async def set_preference(self, customer_id: str, key: str, value: bool) -> None:
        self.calls.append(("set_preference", customer_id, key))
        self.prefs[(customer_id, key)] = value

    async def get_preference(self, customer_id: str, key: str) -> bool | None:
        return self.prefs.get((customer_id, key))

    async def send_email(self, draft: EmailDraft, inbox: str | None) -> SendReceipt:
        self.calls.append(("send_email", draft.customer_id, draft.template))
        self.inboxes_used.append(inbox)
        if self.send_permanent_failure:
            raise PermanentError("send_failed")
        if self.send_transient_failures > 0:
            self.send_transient_failures -= 1
            raise TransientError("mail server busy")
        self.sent.append(draft)
        return SendReceipt(str(len(self.sent)), "accepted", "simulated", inbox)

    async def message_status(self, customer_id: str, message_id: str) -> str | None:
        if self.forget_messages:
            return None
        return "accepted" if int(message_id) <= len(self.sent) else None


class Audit:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def __call__(self, **row: Any) -> None:
        self.rows.append(row)


class World:
    """A gateway with everything faked, a clock and a record of the sleeps it asked for."""

    def __init__(self) -> None:
        self.clock = Clock()
        self.store = MemoryStore()
        self.facts = FakeFacts()
        self.effects = FakeEffects(self.facts)
        self.audit = Audit()
        self.sleeps: list[float] = []
        self.counter = 0

        async def sleep(seconds: float) -> None:
            self.sleeps.append(seconds)

        def new_id() -> str:
            self.counter += 1
            return f"00000000-0000-4000-8000-{self.counter:012d}"

        self.gateway = ActionGateway(
            store=self.store, facts=self.facts, effects=self.effects, audit=self.audit,
            now=self.clock, sleep=sleep, new_id=new_id,
        )  # fmt: skip
        self.facts.cards[("C1", "CARD-1")] = card()
        self.facts.txs[("C1", "T1")] = tx()
        self.facts.emails["C1"] = "c***@demo.bank"
