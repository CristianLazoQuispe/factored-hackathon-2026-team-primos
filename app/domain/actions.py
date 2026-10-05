"""What the agent may do for a customer, and the policy that decides it. Pure functions, no I/O.

The model only *proposes* an action by name with typed parameters. Whether the action is allowed,
needs the customer's confirmation, is refused or goes to a person is decided here, from facts the
code read from the bank's data. Anything that is not in the catalog goes to a person.

Moving money is not an action of this policy: it refuses it. Transfers and payments are
khipear's (app/domain/transfers.py), with its own rules and its own confirmation.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_ACTIONS_PER_BATCH = 3
CONFIRMATION_TTL = timedelta(minutes=10)
CARD_TYPES = frozenset({"Tarjeta Crédito", "Tarjeta Débito", "Credit Card", "Debit Card"})
CREDIT_CARD_TYPES = frozenset({"Tarjeta Crédito", "Credit Card"})
FRAUD_SCORE_HIGH = 70.0  # flagged transactions average 55.7 in the sample, the rest 14.8
PENDING_GRACE_DAYS = 3  # a charge still pending after this long is worth a case
DEBT_TOLERANCE = 0.01
DUE_SOON_DAYS = 5
SLA_HOURS = {"High": 4, "Medium": 24, "Low": 72}

# Statuses of one action. The first two wait for the customer or for the executor.
AWAITING = "awaiting_confirmation"
CONFIRMED = "confirmed"
EXECUTING = "executing"
VERIFIED = "verified"
FAILED = "failed"
CANCELLED = "cancelled"
EXPIRED = "expired"
REFUSED = "refused"
ESCALATED = "escalated"
SKIPPED = "skipped"
TERMINAL = frozenset({VERIFIED, FAILED, CANCELLED, EXPIRED, REFUSED, ESCALATED, SKIPPED})


class Verdict(StrEnum):
    """Same words as ops.decision_log.policy_decision."""

    ALLOW = "allowed"
    CONFIRM = "needs_confirmation"
    DENY = "blocked"
    ESCALATE = "escalated"


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    reason: str | None = None
    strong: bool = False  # the confirmation spells out what cannot be undone


# ---------------------------------------------------------------- what the model may ask for


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CardParams(_Params):
    product_id: str = Field(min_length=1, max_length=64)


class InquiryParams(_Params):
    transaction_id: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=300)  # the customer's words, for the person


class EmailParams(_Params):
    topic: Literal["balances", "payment_status", "case_receipt"]


class AlertParams(_Params):
    kind: Literal["duplicate_charge", "payment_due"]
    enabled: bool = True


class CallbackParams(_Params):
    window: Literal["morning", "afternoon", "evening"]


@dataclass(frozen=True)
class ActionSpec:
    params: type[BaseModel]
    risk: Literal["low", "medium", "high"]


CATALOG: dict[str, ActionSpec] = {
    "send_summary_email": ActionSpec(EmailParams, "low"),
    "set_alert": ActionSpec(AlertParams, "low"),
    "request_callback": ActionSpec(CallbackParams, "low"),
    "open_payment_inquiry": ActionSpec(InquiryParams, "medium"),
    "block_card": ActionSpec(CardParams, "medium"),
    "cancel_card": ActionSpec(CardParams, "high"),
}

# Known requests that are never automated, with what happens to them instead.
NEVER_AUTOMATED: dict[str, tuple[Verdict, str]] = {
    **{
        name: (Verdict.DENY, "money_movement_not_authorized")
        for name in ("transfer_money", "make_payment", "schedule_payment", "pay_card")
    },
    **{
        name: (Verdict.ESCALATE, "needs_human_approval")
        for name in ("refund", "reverse_charge", "compensation", "provisional_credit")
    },
    **{
        name: (Verdict.ESCALATE, "identity_change")
        for name in ("change_phone", "change_email", "change_address", "change_contact")
    },
    "raise_limit": (Verdict.ESCALATE, "credit_policy"),
    "credit_eligibility": (Verdict.ESCALATE, "credit_policy"),
    "reissue_card": (Verdict.ESCALATE, "physical_card"),
    "unblock_card": (Verdict.ESCALATE, "unfreeze_needs_review"),
}


def known_actions() -> list[str]:
    return sorted(CATALOG)


# ---------------------------------------------------------------- facts the code read


@dataclass(frozen=True)
class CardFacts:
    product_id: str
    product_type: str
    last4: str | None
    status: str  # effective: the bank's status with the customer's own freeze or cancel on top
    frozen_by_customer: bool
    currency: str | None
    balance: float | None
    days_past_due: int | None


@dataclass(frozen=True)
class TxFacts:
    transaction_id: str
    product_id: str | None
    status: str
    kind: str
    amount: float
    currency: str
    merchant: str | None
    country: str | None
    occurred_at: datetime
    is_fraud: bool
    fraud_score: float | None
    duplicates: int  # other approved or pending purchases: same merchant, amount, within 10 min
    customer_country: str | None
    as_of: date  # the dataset's last day: "today" for ages


@dataclass(frozen=True)
class Facts:
    card: CardFacts | None = None
    tx: TxFacts | None = None
    email_masked: str | None = None
    batch_opens_case: bool = False  # an inquiry earlier in the same batch can be receipted
    extras: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------- the policy


def _deny(reason: str) -> Decision:
    return Decision(Verdict.DENY, reason)


def _escalate(reason: str) -> Decision:
    return Decision(Verdict.ESCALATE, reason)


def _card_precheck(card: CardFacts | None) -> Decision | None:
    if card is None:
        return _deny("not_found")  # not theirs and not found look the same
    if card.product_type not in CARD_TYPES:
        return _deny("not_a_card")
    if card.status in ("Closed", "Cancelled"):
        return _deny("card_closed")
    if card.status == "Suspended":
        return _escalate("card_suspended")
    return None


def _block_card(_: BaseModel, facts: Facts) -> Decision:
    if (refused := _card_precheck(facts.card)) is not None:
        return refused
    card = facts.card
    if card.status == "Blocked":
        return _deny("already_blocked")
    if card.status != "Active":
        return _escalate("unknown_card_status")
    return Decision(Verdict.CONFIRM)


def _cancel_card(_: BaseModel, facts: Facts) -> Decision:
    if (refused := _card_precheck(facts.card)) is not None:
        return refused
    card = facts.card
    if card.status == "Blocked" and not card.frozen_by_customer:
        return _escalate("blocked_by_bank")  # someone else's block: a person looks at why
    if card.status not in ("Active", "Blocked"):
        return _escalate("unknown_card_status")
    if (card.days_past_due or 0) > 0:
        return _escalate("past_due")
    if card.product_type in CREDIT_CARD_TYPES and (card.balance or 0) > DEBT_TOLERANCE:
        return _escalate("outstanding_balance")
    return Decision(Verdict.CONFIRM, strong=True)


def _payment_inquiry(_: BaseModel, facts: Facts) -> Decision:
    tx = facts.tx
    if tx is None:
        return _deny("not_found")
    if tx.status == "Reversed":
        return _deny("already_reversed")
    if tx.status == "Declined":
        return _deny("was_declined")
    if tx.status == "Pending" and (tx.as_of - tx.occurred_at.date()).days < PENDING_GRACE_DAYS:
        return _deny("still_pending")
    return Decision(Verdict.CONFIRM)


def _email(params: BaseModel, facts: Facts) -> Decision:
    if not facts.email_masked:
        return _deny("no_contact_on_file")
    if params.topic == "case_receipt" and not facts.batch_opens_case:
        return _deny("no_case_to_confirm")
    return Decision(Verdict.ALLOW)


def _always_confirm(_: BaseModel, __: Facts) -> Decision:
    return Decision(Verdict.CONFIRM)


_RULES = {
    "block_card": _block_card,
    "cancel_card": _cancel_card,
    "open_payment_inquiry": _payment_inquiry,
    "send_summary_email": _email,
    "set_alert": _always_confirm,
    "request_callback": _always_confirm,
}


def decide(action: str, params: BaseModel | None, facts: Facts) -> Decision:
    """The one place that says what happens to a proposed action."""
    if action in NEVER_AUTOMATED:
        verdict, reason = NEVER_AUTOMATED[action]
        return Decision(verdict, reason)
    if action not in CATALOG or params is None:
        return _escalate("unknown_action")
    return _RULES[action](params, facts)


def parse_params(action: str, raw: dict[str, Any] | None) -> tuple[BaseModel | None, str | None]:
    """The typed parameters, or why they are not valid. Extra fields are an error."""
    spec = CATALOG.get(action)
    if spec is None:
        return None, None
    try:
        return spec.params.model_validate(raw or {}), None
    except ValueError:
        return None, "invalid_params"


# ---------------------------------------------------------------- signals, priority, payments


def risk_signals(tx: TxFacts) -> list[str]:
    signals = []
    if tx.is_fraud or (tx.fraud_score or 0) >= FRAUD_SCORE_HIGH:
        signals.append("possible_fraud")
    if tx.duplicates > 0:
        signals.append("duplicate_charge")
    if tx.country and tx.customer_country and tx.country != tx.customer_country:
        signals.append("foreign_transaction")
    if tx.status == "Pending":
        signals.append("pending_charge")
    return signals


def case_priority(signals: list[str]) -> tuple[str, int]:
    """Priority and the hours a person has to answer."""
    if "possible_fraud" in signals:
        priority = "High"
    elif {"duplicate_charge", "foreign_transaction"} & set(signals):
        priority = "Medium"
    else:
        priority = "Low"
    return priority, SLA_HOURS[priority]


def sla_due(now: datetime, priority: str) -> datetime:
    return now + timedelta(hours=SLA_HOURS[priority])


def payment_status(row: dict[str, Any], as_of: date) -> dict[str, Any]:
    """Where a card or loan stands with its payment, computed and never estimated."""
    due: date = row["due_date"]
    past_due = float(row.get("past_due_amount") or 0)
    days_to_due = (due - as_of).days
    if past_due > DEBT_TOLERANCE or days_to_due < 0:
        state = "overdue"
    elif days_to_due <= DUE_SOON_DAYS:
        state = "due_soon"
    else:
        state = "current"
    return {
        "state": state,
        "due_date": due.isoformat(),
        "days_to_due": days_to_due,
        "minimum_payment": float(row["minimum_payment"]),
        "past_due_amount": past_due,
    }


@dataclass
class ActionRecord:
    """One proposed action as it is stored."""

    action_id: str
    batch_id: str
    position: int
    customer_id: str
    conversation_id: str | None
    action: str
    params: dict[str, Any]
    view: dict[str, Any]
    decision: str
    reason: str | None
    status: str
    language: str
    idempotency_key: str
    created_at: datetime
    expires_at: datetime
    attempts: int = 0
    result: dict[str, Any] | None = None
    confirmed_at: datetime | None = None
    finished_at: datetime | None = None


def utcnow() -> datetime:
    return datetime.now(UTC)
