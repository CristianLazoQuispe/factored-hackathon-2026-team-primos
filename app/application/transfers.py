"""Khipear: propose a movement of the customer's money, then execute it when they confirm.

`propose` never moves anything. It resolves the accounts from the customer's own products (the
model only passes what the customer said), asks when there is more than one candidate, applies the
rules and stores the proposal. `execute` runs only from the confirmation button: the ledger locks
both products and the same rules run again, because the balance may have changed since.
The customer always comes from the session, never from the model.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol
from uuid import uuid4

from app.domain.accounts import DEBT_TYPES
from app.domain.transfers import (
    Block,
    Kind,
    Limits,
    can_be_paid,
    can_receive,
    can_send,
    check,
    choose,
    option,
    recipient_name,
)

Recheck = Callable[[dict, dict, dict, float], Block | None]


class Ledger(Protocol):
    """The bank's accounts. Reads are reviewed SQL; `execute` is one database transaction."""

    async def products(self, customer_id: str) -> list[dict]: ...

    async def account_by_number(self, account_number: str) -> dict | None: ...

    async def accounts_of(self, customer_id: str) -> list[dict]:
        """Active deposit accounts of another customer, oldest first, with the owner's name."""

    async def usd_rate(self, currency: str) -> float | None: ...

    async def sent_today_usd(self, customer_id: str) -> float: ...

    async def save(self, proposal: dict) -> datetime:
        """Stores the proposal and returns when it expires."""

    async def execute(self, transfer_id: str, customer_id: str, recheck: Recheck) -> dict: ...

    async def cancel(self, transfer_id: str, customer_id: str) -> bool: ...


def _ask(missing: str, candidates: list[dict], question: str) -> dict[str, Any]:
    return {
        "status": "needs_clarification",
        "missing": missing,
        "options": [option(c) for c in candidates],
        "ask": question,
    }


def _blocked(block: Block) -> dict[str, Any]:
    return {
        "status": "blocked",
        "reason": block.reason,
        "response_code": block.code,
        "detail": block.detail,
    }


def _others(products: list[dict], taken: dict | None) -> list[dict]:
    return [p for p in products if taken is None or p["product_id"] != taken["product_id"]]


def _kind(kind: Kind, products: list[dict], to_last4, to_type, other_customer) -> Kind:
    """What the destination is decides the kind, not the label the model chose: a small model
    calls paying a card "own_accounts", and that must not turn into a refusal."""
    if other_customer:
        return "third_party"
    named = [p for p in products if to_last4 and p["product_number_last4"] == to_last4]
    is_debt = to_type in DEBT_TYPES or (
        any(can_be_paid(p) for p in named) and not any(can_receive(p) for p in named)
    )
    return "pay_debt" if is_debt else kind


async def transfer_options(ledger: Ledger, customer_id: str) -> dict[str, Any]:
    products = await ledger.products(customer_id)
    return {
        "accounts": [option(p) for p in products if can_send(p)],
        "debts": [option(p) for p in products if can_be_paid(p)],
    }


async def _third_party(
    ledger: Ledger,
    customer_id: str,
    origin: dict,
    account_number: str | None,
    recipient_id: str | None,
) -> dict | Block:
    """The account that receives. By customer ID the code picks it: the sender never sees or
    chooses among someone else's accounts."""
    if account_number:
        found = await ledger.account_by_number(account_number.strip())
        return found or Block("recipient_not_found", "14", "No account has that number.")
    recipient_id = recipient_id.strip().upper()
    if recipient_id == customer_id:
        return Block("own_account", "14", "That is the customer's own ID: use own_accounts.")
    accounts = await ledger.accounts_of(recipient_id)
    same_currency = [a for a in accounts if a["currency"] == origin["currency"]]
    if not accounts:
        return Block("recipient_not_found", "14", "No customer with that ID can receive money.")
    if not same_currency:
        return Block(
            "currency_mismatch", "57", f"That customer has no account in {origin['currency']}."
        )
    return same_currency[0]


async def propose(
    ledger: Ledger,
    limits: Limits,
    customer_id: str,
    kind: Kind,
    amount: float,
    from_last4: str | None = None,
    to_last4: str | None = None,
    to_account_number: str | None = None,
    to_customer_id: str | None = None,
    from_type: str | None = None,
    to_type: str | None = None,
) -> dict[str, Any]:
    """`from_type` and `to_type` are the product type the customer named ("mi tarjeta", "mi
    cuenta de ahorro"): they narrow the candidates, so there is no question when one fits."""
    products = await ledger.products(customer_id)
    kind = _kind(kind, products, to_last4, to_type, to_account_number or to_customer_id)
    receivers = [p for p in products if to_type in (None, p["product_type"])]
    sources = [p for p in products if can_send(p) and from_type in (None, p["product_type"])]
    if not sources:
        return _blocked(Block("no_source_account", "57", "No active account to send money from."))

    destination: dict | None = None
    if kind == "own_accounts" and to_last4:  # a known destination narrows the possible origins
        destination = choose([p for p in receivers if can_receive(p)], to_last4)
        sources = _others(sources, destination)
    origin = choose(sources, from_last4)
    if origin is None:
        return _ask("origin", sources, "Which account should the money come from?")

    if kind == "own_accounts":
        targets = [p for p in _others(receivers, origin) if can_receive(p)]
        destination = destination or choose(targets, to_last4)
        if not targets:
            return _blocked(Block("no_other_account", "14", "No other account of their own."))
        if destination is None:
            return _ask("destination", targets, "Which of their accounts should receive it?")
    elif kind == "pay_debt":
        debts = [p for p in receivers if can_be_paid(p)]
        destination = choose(debts, to_last4)
        if not debts:
            return _blocked(Block("nothing_to_pay", "14", "No card or loan with a debt to pay."))
        if destination is None:
            return _ask("destination", debts, "Which card or loan do they want to pay?")
    else:
        if bool(to_account_number) == bool(to_customer_id):
            return _ask("destination", [], "The recipient's account number, or their customer ID?")
        found = await _third_party(ledger, customer_id, origin, to_account_number, to_customer_id)
        if isinstance(found, Block):
            return _blocked(found)
        destination = found

    amount = float(amount)
    rate = await ledger.usd_rate(origin["currency"])
    amount_usd = None if rate is None else round(amount * rate, 2)
    sent = await ledger.sent_today_usd(customer_id) if kind == "third_party" else 0.0
    block = check(kind, origin, destination, amount, amount_usd, sent, limits)
    if block:
        return _blocked(block)

    if kind == "third_party":
        shown = {
            "name": recipient_name(destination.get("first_name"), destination.get("last_name"))
        }
        if to_account_number:  # the sender typed the number, so its ending tells them nothing new
            shown["last4"] = destination["product_number_last4"]
    else:
        shown = {k: v for k, v in option(destination).items() if k in ("product_type", "last4")}
    confirmation = {
        "transfer_id": str(uuid4()),
        "kind": kind,
        "origin": {k: v for k, v in option(origin).items() if k in ("product_type", "last4")},
        "destination": shown,
        "amount": amount,
        "currency": origin["currency"],
    }
    expires_at = await ledger.save(
        confirmation
        | {
            "customer_id": customer_id,
            "origin_product_id": origin["product_id"],
            "destination_product_id": destination["product_id"],
            "destination_customer_id": destination["customer_id"],
            "amount_usd": amount_usd,
        }
    )
    return {
        "status": "proposed",
        "confirmation": confirmation | {"expires_at": expires_at.isoformat()},
    }


async def execute(
    ledger: Ledger, limits: Limits, customer_id: str, transfer_id: str
) -> dict[str, Any]:
    """Runs a proposal the customer confirmed. Safe to call twice: the second call gets the same
    receipt and moves nothing."""

    def recheck(transfer: dict, origin: dict, destination: dict, sent_today_usd: float):
        return check(
            transfer["kind"],
            origin,
            destination,
            transfer["amount"],
            transfer["amount_usd"],
            sent_today_usd,
            limits,
        )

    result = await ledger.execute(transfer_id, customer_id, recheck)
    block = result.pop("block", None)
    return result | _blocked(block) if block else result


async def cancel(ledger: Ledger, customer_id: str, transfer_id: str) -> dict[str, Any]:
    cancelled = await ledger.cancel(transfer_id, customer_id)
    return {"status": "cancelled" if cancelled else "not_found"}
