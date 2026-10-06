"""The action gateway: propose, confirm, execute, verify. No model and no framework in here.

The model can only call `propose`. Everything that decides or changes something happens here, in
this order: the typed parameters are checked, the facts are read from the bank's data, the policy
(`app.domain.actions.decide`) says allow, confirm, refuse or escalate, and the proposal is stored.
Only the customer's confirmation, which arrives through its own endpoint and never through the
model, lets the batch run. Each action is then executed with bounded retries and verified by
reading its effect back; the customer is told only what was verified.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal, Protocol

from app.domain.action_text import build_email, render_batch
from app.domain.actions import (
    AWAITING,
    CONFIRMATION_TTL,
    CONFIRMED,
    ESCALATED,
    EXECUTING,
    FAILED,
    MAX_ACTIONS_PER_BATCH,
    REFUSED,
    SKIPPED,
    VERIFIED,
    ActionRecord,
    CardFacts,
    Decision,
    Facts,
    TxFacts,
    Verdict,
    case_priority,
    decide,
    parse_params,
    payment_status,
    risk_signals,
    sla_due,
    utcnow,
)
from app.domain.email_content import (
    EmailContent,
    balances_content,
    case_receipt_content,
    content_text,
)

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


class TransientError(Exception):
    """Trying again may work: a timeout, a busy database, a mail server that said later."""


class PermanentError(Exception):
    """Trying again will not help. `reason` is a code from app.domain.action_text.REASONS."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class VerificationFailed(Exception):
    """The action ran but reading its effect back did not show it."""


class NotFound(Exception):
    """No such batch for this customer. A batch of someone else looks the same."""


@dataclass(frozen=True)
class EmailDraft:
    customer_id: str
    action_id: str
    template: str
    language: str
    subject: str
    body: str  # the plain text: what the outbox keeps, and the text part of the message
    to_masked: str
    content: EmailContent | None = None  # when there is one, the mailer also makes the HTML part


@dataclass(frozen=True)
class SendReceipt:
    message_id: str
    status: Literal["accepted", "failed"]
    mode: str
    delivered_to: str | None


@dataclass(frozen=True)
class CaseDraft:
    case_id: str  # the action's id: running it twice cannot make two cases
    customer_id: str
    kind: Literal["payment_inquiry", "callback"]
    priority: str
    reason_codes: list[str]
    sla_due_at: datetime
    case_file: dict[str, Any]
    transaction_id: str | None = None


class FactsPort(Protocol):
    async def card(self, customer_id: str, product_id: str) -> CardFacts | None: ...
    async def transaction(self, customer_id: str, transaction_id: str) -> TxFacts | None: ...
    async def email_masked(self, customer_id: str) -> str | None: ...
    async def products(self, customer_id: str) -> list[dict[str, Any]]: ...
    async def billing(self, customer_id: str) -> list[dict[str, Any]]: ...
    async def as_of(self) -> date: ...


class EffectsPort(Protocol):
    def inboxes(self) -> list[str]: ...
    async def card_control(
        self,
        customer_id: str,
        product_id: str,
        control: Literal["freeze", "cancel"],
        action_id: str,
    ) -> None: ...
    async def card_status(self, customer_id: str, product_id: str) -> str | None: ...
    async def confirm_card(self, action_id: str) -> None: ...
    async def open_case(self, draft: CaseDraft) -> str: ...
    async def read_case(self, customer_id: str, case_id: str) -> dict[str, Any] | None: ...
    async def set_preference(self, customer_id: str, key: str, value: bool) -> None: ...
    async def get_preference(self, customer_id: str, key: str) -> bool | None: ...
    async def send_email(self, draft: EmailDraft, inbox: str | None) -> SendReceipt: ...
    async def message_status(self, customer_id: str, message_id: str) -> str | None: ...


class StorePort(Protocol):
    async def insert(self, records: list[ActionRecord]) -> None: ...
    async def batch(self, batch_id: str, customer_id: str) -> list[ActionRecord]: ...
    async def claim(self, batch_id: str, customer_id: str, now: datetime) -> int: ...
    async def expire(self, batch_id: str, customer_id: str, now: datetime) -> int: ...
    async def cancel(self, batch_id: str, customer_id: str) -> int: ...
    async def supersede(
        self, customer_id: str, conversation_id: str, keep_batch_id: str
    ) -> int: ...
    async def mark(
        self,
        action_id: str,
        status: str,
        *,
        reason: str | None = None,
        attempts: int | None = None,
        result: dict[str, Any] | None = None,
        finished_at: datetime | None = None,
    ) -> None: ...


@dataclass
class Run:
    """What one execution of a batch shares between its actions."""

    inbox: str | None
    results: dict[str, dict[str, Any]]
    views: dict[str, dict[str, Any]]  # each action's view, by action name


Audit = Callable[..., Awaitable[None]]


async def _no_audit(**_: Any) -> None:
    return None


def _card_view(card: CardFacts) -> dict[str, Any]:
    return {"card_kind": card.product_type, "last4": card.last4, "currency": card.currency}


class ActionGateway:
    def __init__(
        self,
        *,
        store: StorePort,
        facts: FactsPort,
        effects: EffectsPort,
        audit: Audit = _no_audit,
        now: Callable[[], datetime] = utcnow,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        new_id: Callable[[], str] = lambda: str(uuid.uuid4()),
    ):
        self.store, self.facts, self.effects, self.audit = store, facts, effects, audit
        self.now, self.sleep, self.new_id = now, sleep, new_id

    # ------------------------------------------------------------------ propose

    async def _facts_for(
        self, customer_id: str, action: str, params: Any, opens_case: bool
    ) -> tuple[Facts, dict[str, Any]]:
        """The facts the policy needs for one action, and the view the customer will see."""
        if action in ("block_card", "cancel_card"):
            card = await self.facts.card(customer_id, params.product_id)
            return Facts(card=card), (_card_view(card) if card else {})
        if action == "open_payment_inquiry":
            tx = await self.facts.transaction(customer_id, params.transaction_id)
            if tx is None:
                return Facts(), {}
            priority, hours = case_priority(risk_signals(tx))
            view = {
                "merchant": tx.merchant,
                "amount": tx.amount,
                "currency": tx.currency,
                "date": tx.occurred_at.date().isoformat(),
                "priority": priority,
                "sla_hours": hours,
                "signals": risk_signals(tx),
            }
            return Facts(tx=tx), view
        if action == "send_summary_email":
            masked = await self.facts.email_masked(customer_id)
            return Facts(email_masked=masked, batch_opens_case=opens_case), {"to": masked}
        return Facts(), {}

    async def propose(
        self,
        customer_id: str,
        requests: list[dict[str, Any]],
        *,
        language: str,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        """Store what the model proposed with the policy's verdict on each item. Nothing runs yet,
        unless every item is allowed without confirmation."""
        batch_id, now = self.new_id(), self.now()
        records: list[ActionRecord] = []
        opens_case = False
        for position, raw in enumerate(requests):
            action = str(raw.get("action") or "").strip().lower()
            params_raw = raw.get("params") if isinstance(raw.get("params"), dict) else {}
            params, view, decision = None, {}, Decision(Verdict.ESCALATE, "unknown_action")
            if position >= MAX_ACTIONS_PER_BATCH:
                decision = Decision(Verdict.DENY, "too_many_actions")
            else:
                params, bad = parse_params(action, params_raw)
                if bad:
                    decision = Decision(Verdict.DENY, bad)
                else:
                    try:
                        facts, view = await self._facts_for(customer_id, action, params, opens_case)
                    except Exception:
                        log.exception("facts for %s failed", action)
                        decision = Decision(Verdict.ESCALATE, "temporary_error")
                    else:
                        decision = decide(action, params, facts)
            if decision.verdict is Verdict.CONFIRM and action == "open_payment_inquiry":
                opens_case = True
            view = {**view, "strong": decision.strong}
            records.append(
                ActionRecord(
                    action_id=self.new_id(),
                    batch_id=batch_id,
                    position=position,
                    customer_id=customer_id,
                    conversation_id=conversation_id,
                    action=action or "unknown",
                    params=params.model_dump() if params is not None else dict(params_raw),
                    view=view,
                    decision=decision.verdict.value,
                    reason=decision.reason,
                    status="pending",
                    language=language,
                    idempotency_key=f"{batch_id}:{position}",
                    created_at=now,
                    expires_at=now + CONFIRMATION_TTL,
                )
            )
        needs_confirmation = any(r.decision == Verdict.CONFIRM.value for r in records)
        for record in records:
            record.status = self._initial_status(record, needs_confirmation)
        await self.store.insert(records)
        if conversation_id and needs_confirmation:  # only the latest proposal keeps its button
            await self.store.supersede(customer_id, conversation_id, batch_id)
        for record in records:
            await self.audit(
                tool=record.action, proposed=record.params, verdict=record.decision,
                reason=record.reason, executed=False, verified=False,
                conversation_id=conversation_id,
            )  # fmt: skip
        if not needs_confirmation and any(r.status == CONFIRMED for r in records):
            await self._execute(await self.store.batch(batch_id, customer_id), inbox=None)
        return await self.view(customer_id, batch_id)

    @staticmethod
    def _initial_status(record: ActionRecord, needs_confirmation: bool) -> str:
        if record.decision == Verdict.CONFIRM.value:
            return AWAITING
        if record.decision == Verdict.ALLOW.value:
            return AWAITING if needs_confirmation else CONFIRMED  # rides with the batch
        return REFUSED if record.decision == Verdict.DENY.value else ESCALATED

    # ------------------------------------------------------------------ confirm / cancel / view

    async def view(self, customer_id: str, batch_id: str) -> dict[str, Any]:
        records = await self.store.batch(batch_id, customer_id)
        if not records:
            raise NotFound(batch_id)
        return render_batch(records, records[0].language, self.effects.inboxes())

    async def cancel(self, customer_id: str, batch_id: str) -> dict[str, Any]:
        await self.store.cancel(batch_id, customer_id)
        return await self.view(customer_id, batch_id)

    async def confirm(
        self, customer_id: str, batch_id: str, *, inbox: str | None = None
    ) -> dict[str, Any]:
        """Run a batch the customer confirmed. Asking twice runs it once."""
        records = await self.store.batch(batch_id, customer_id)
        if not records:
            raise NotFound(batch_id)
        waiting = [r for r in records if r.status == AWAITING]
        if not waiting:
            return await self.view(customer_id, batch_id)
        now = self.now()
        if now >= waiting[0].expires_at:
            await self.store.expire(batch_id, customer_id, now)
            return await self.view(customer_id, batch_id)
        if await self.store.claim(batch_id, customer_id, now) == 0:
            return await self.view(customer_id, batch_id)  # another request got there first
        await self._execute(await self.store.batch(batch_id, customer_id), inbox=inbox)
        return await self.view(customer_id, batch_id)

    # ------------------------------------------------------------------ execute

    async def _execute(self, records: list[ActionRecord], *, inbox: str | None) -> None:
        run = Run(inbox, {}, {r.action: r.view for r in records})
        for record in sorted(records, key=lambda r: r.position):
            if record.status != CONFIRMED:
                continue
            params, _ = parse_params(record.action, record.params)
            opens_case = "open_payment_inquiry" in run.results
            needs_case = (
                record.action == "send_summary_email"
                and record.params.get("topic") == "case_receipt"
            )
            if needs_case and not opens_case:
                await self._finish(record, SKIPPED, "dependency_failed", None)
                continue
            try:
                facts, view = await self._facts_for(
                    record.customer_id, record.action, params, opens_case
                )
            except Exception:
                log.exception("re-check of %s failed", record.action)
                await self._finish(record, FAILED, "temporary_error", None)
                continue
            decision = decide(record.action, params, facts)
            if decision.verdict in (Verdict.DENY, Verdict.ESCALATE):
                status = REFUSED if decision.verdict is Verdict.DENY else ESCALATED
                await self._finish(record, status, decision.reason, None)  # it changed meanwhile
                continue
            record.view = {**record.view, **view}
            await self._run_with_retries(record, params, facts, run)

    async def _run_with_retries(
        self, record: ActionRecord, params: Any, facts: Facts, run: Run
    ) -> None:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            await self.store.mark(record.action_id, EXECUTING, attempts=attempt)
            try:
                result = await self._do(record, params, facts, run)
            except TransientError:
                if attempt < MAX_ATTEMPTS:
                    await self.sleep(0.2 * attempt)
                    continue
                await self._finish(record, FAILED, "temporary_error", None, attempts=attempt)
            except PermanentError as error:
                await self._finish(record, FAILED, error.reason, None, attempts=attempt)
            except VerificationFailed:
                await self._finish(record, FAILED, "verification_failed", None, attempts=attempt)
            except Exception:
                log.exception("action %s crashed", record.action)
                await self._finish(record, FAILED, "error", None, attempts=attempt)
            else:
                run.results[record.action] = result
                await self._finish(record, VERIFIED, None, result, attempts=attempt)
            return

    async def _finish(
        self, record: ActionRecord, status: str, reason: str | None, result: dict | None,
        attempts: int | None = None,
    ) -> None:  # fmt: skip
        record.status, record.reason, record.result = status, reason, result
        if attempts is not None:
            record.attempts = attempts
        record.finished_at = self.now()
        await self.store.mark(
            record.action_id, status, reason=reason, attempts=attempts, result=result,
            finished_at=record.finished_at,
        )  # fmt: skip
        await self.audit(
            tool=record.action, proposed=record.params, verdict=record.decision, reason=reason,
            executed=status in (VERIFIED, FAILED), verified=status == VERIFIED,
            conversation_id=record.conversation_id,
        )  # fmt: skip

    async def _do(
        self, record: ActionRecord, params: Any, facts: Facts, run: Run
    ) -> dict[str, Any]:
        """Run one action and read its effect back. Anything but a verified effect raises."""
        customer, effects = record.customer_id, self.effects
        if record.action in ("block_card", "cancel_card"):
            control, expected = (
                ("freeze", "Blocked") if record.action == "block_card" else ("cancel", "Cancelled")
            )
            await effects.card_control(customer, params.product_id, control, record.action_id)
            status = await effects.card_status(customer, params.product_id)
            if status != expected:
                raise VerificationFailed
            await effects.confirm_card(record.action_id)
            return {"product_id": params.product_id, "status": status}
        if record.action in ("open_payment_inquiry", "request_callback"):
            return await self._open_case(record, params, facts)
        if record.action == "set_alert":
            key = f"alert.{params.kind}"
            await effects.set_preference(customer, key, params.enabled)
            if await effects.get_preference(customer, key) is not params.enabled:
                raise VerificationFailed
            return {"kind": params.kind, "enabled": params.enabled}
        if record.action == "send_summary_email":
            return await self._send_email(record, params, run)
        raise PermanentError("unknown_action")

    async def _open_case(self, record: ActionRecord, params: Any, facts: Facts) -> dict[str, Any]:
        now = self.now()
        if record.action == "open_payment_inquiry":
            tx = facts.tx
            signals = risk_signals(tx)
            priority, hours = case_priority(signals)
            case_file = {
                "request": "payment_inquiry",
                "transaction": {
                    "transaction_id": tx.transaction_id, "merchant": tx.merchant,
                    "amount": tx.amount, "currency": tx.currency,
                    "date": tx.occurred_at.isoformat(), "status": tx.status, "country": tx.country,
                },
                "verified_facts": {"signals": signals, "duplicates_found": tx.duplicates},
                "customer_note": params.note,
                "unresolved": [UNRESOLVED[s] for s in signals if s in UNRESOLVED]
                or ["¿El cliente reconoce el cargo?"],
            }  # fmt: skip
            draft = CaseDraft(
                record.action_id, record.customer_id, "payment_inquiry", priority, signals,
                sla_due(now, priority), case_file, tx.transaction_id,
            )  # fmt: skip
        else:
            priority, hours = "Low", 24
            draft = CaseDraft(
                record.action_id, record.customer_id, "callback", priority, ["callback_requested"],
                sla_due(now, priority),
                {"request": "callback", "window": params.window, "unresolved": []},
            )  # fmt: skip
        case_id = await self.effects.open_case(draft)
        stored = await self.effects.read_case(record.customer_id, case_id)
        if stored is None or stored.get("status") != "open":
            raise VerificationFailed
        return {
            "case_id": case_id,
            "case_ref": "Q-" + case_id.replace("-", "")[:8].upper(),
            "priority": priority,
            "sla_hours": hours,
            "sla_due_at": draft.sla_due_at.isoformat(),
            "reason_codes": draft.reason_codes,
        }

    async def send_receipt(self, customer_id: str, key: str, content: EmailContent) -> bool:
        """Email the receipt of something that already happened, such as a transfer the customer
        confirmed. It is not an action: nothing is proposed, confirmed or verified, and it changes
        nothing. `key` (the id of the transfer) makes it go out once: a message already accepted
        for it is never sent again. A mail that fails is a log line and a False, not an error in
        the operation it reports."""
        to_masked = await self.facts.email_masked(customer_id)
        if not to_masked:
            return False  # no address on file
        draft = EmailDraft(
            customer_id, key, content.kind, content.language, content.subject,
            content_text(content), to_masked, content,
        )  # fmt: skip
        try:
            receipt = await self.effects.send_email(draft, None)
        except (TransientError, PermanentError) as error:
            log.warning("the receipt %s was not sent: %s", key, error)
            return False
        return receipt.status == "accepted"

    async def _send_email(self, record: ActionRecord, params: Any, run: Run) -> dict[str, Any]:
        customer, topic = record.customer_id, params.topic
        content: EmailContent | None = None
        if topic == "balances":
            content = balances_content(record.language, await self.facts.products(customer))
            data: dict[str, Any] = {}
        elif topic == "payment_status":
            as_of = await self.facts.as_of()
            data = {
                "items": [
                    {**row, **payment_status(row, as_of)}
                    for row in await self.facts.billing(customer)
                ]
            }
        else:  # case_receipt: the case this batch just opened, and the charge it is about
            charge = run.views["open_payment_inquiry"]
            data = {
                "case": run.results["open_payment_inquiry"],
                "tx": {k: charge.get(k) for k in ("merchant", "amount", "currency", "date")},
            }
            content = case_receipt_content(record.language, data["case"], data["tx"])
        if content is not None:
            subject, body = content.subject, content_text(content)
        else:
            subject, body = build_email(topic, record.language, data)
        draft = EmailDraft(
            customer, record.action_id, topic, record.language, subject, body,
            str(record.view.get("to") or ""), content,
        )  # fmt: skip
        receipt = await self.effects.send_email(draft, run.inbox)
        if receipt.status != "accepted":
            raise PermanentError("send_failed")
        if await self.effects.message_status(customer, receipt.message_id) != "accepted":
            raise VerificationFailed
        return {
            "message_id": receipt.message_id, "to": draft.to_masked,
            "delivered_to": receipt.delivered_to, "mode": receipt.mode,
        }  # fmt: skip


UNRESOLVED = {
    "possible_fraud": "¿El cliente autorizó este cargo? Hay señales de posible fraude.",
    "duplicate_charge": "¿Se pidió el reverso del cargo repetido al comercio?",
    "foreign_transaction": "¿El cliente estaba en el país donde se hizo el cargo?",
    "pending_charge": "¿El cargo sigue pendiente?",
}
