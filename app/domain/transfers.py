"""Rules for moving the customer's money (khipear). Pure.

The model proposes, this code decides, the customer confirms with a button. Nothing here trusts a
value the model wrote: accounts are picked from the customer's own products, and `check` runs
twice, when the operation is proposed and again when it is confirmed.
"""

import re
from dataclasses import dataclass
from typing import Any, Literal

from app.domain.accounts import DEBT_TYPES

Kind = Literal["own_accounts", "pay_debt", "third_party"]
ACCOUNT_TYPES = ("Cuenta Ahorro", "Cuenta Corriente")


# How a customer names each product type, in Spanish and Portuguese.
_SAID_AS = {
    "Cuenta Ahorro": r"ahorro|poupan",
    "Cuenta Corriente": r"corriente|corrente",
    "Tarjeta Crédito": r"tarjeta|cart[aã]o|cr[eé]dito",
    "Préstamo Personal": r"pr[eé]stamo|empr[eé]stimo",
    "Préstamo Hipotecario": r"hipoteca",
}


def said(text: str, last4: str | None = None, product_type: str | None = None) -> bool:
    """True when the customer's own words name that product: its last 4 digits, or its type.
    The model must pass only what the customer said; a value it made up fails this."""
    if last4:
        return last4 in re.findall(r"\d+", text)
    return bool(re.search(_SAID_AS.get(product_type, r"(?!)"), text, re.IGNORECASE))


@dataclass(frozen=True)
class Limits:
    """Team assumption, in USD: the organizer's data has no transfer limits."""

    per_operation_usd: float
    per_day_usd: float


@dataclass(frozen=True)
class Block:
    """Why an operation is refused: `reason` for code, `code` as a card network would answer,
    `detail` for the model to explain it."""

    reason: str
    code: str
    detail: str


def can_send(product: dict[str, Any]) -> bool:
    return can_receive(product) and product.get("current_balance") is not None


def can_receive(product: dict[str, Any]) -> bool:
    return (
        product.get("product_type") in ACCOUNT_TYPES and product.get("product_status") == "Active"
    )


def can_be_paid(product: dict[str, Any]) -> bool:
    """A credit card or loan with something owed. A blocked or past-due one can still be paid."""
    return (
        product.get("product_type") in DEBT_TYPES
        and product.get("product_status") != "Closed"
        and (product.get("current_balance") or 0) > 0
    )


def option(product: dict[str, Any]) -> dict[str, Any]:
    """What the customer is shown of one of their own products when they have to pick."""
    amount = "debt" if product["product_type"] in DEBT_TYPES else "balance"
    return {
        "product_type": product["product_type"],
        "last4": product["product_number_last4"],
        "currency": product["currency"],
        amount: product["current_balance"],
    }


def choose(candidates: list[dict[str, Any]], last4: str | None) -> dict[str, Any] | None:
    """The one product meant, or None when the customer has to say which. A lone candidate needs
    no question; `last4` settles it only when exactly one candidate ends in those digits."""
    if last4:
        matches = [c for c in candidates if c["product_number_last4"] == last4]
        return matches[0] if len(matches) == 1 else None
    return candidates[0] if len(candidates) == 1 else None


def recipient_name(first_name: str | None, last_name: str | None) -> str:
    """First name and last initial: enough to recognise the person, nothing more."""
    initial = f" {last_name.strip()[0]}." if last_name and last_name.strip() else ""
    return f"{(first_name or '').strip()}{initial}".strip() or "Cliente"


def check(
    kind: Kind,
    origin: dict[str, Any],
    destination: dict[str, Any],
    amount: float,
    amount_usd: float | None,
    sent_today_usd: float,
    limits: Limits,
) -> Block | None:
    """None when the operation may go ahead."""
    currency = origin.get("currency")
    if not amount > 0 or round(amount, 2) != amount:
        return Block(
            "invalid_amount", "13", "The amount must be positive, with at most 2 decimals."
        )
    if not can_send(origin) or origin.get("customer_status", "Active") != "Active":
        return Block("origin_unavailable", "57", "That account cannot send money right now.")
    if origin["product_id"] == destination["product_id"]:
        return Block("same_account", "14", "Origin and destination are the same account.")
    own = destination["customer_id"] == origin["customer_id"]
    if kind == "third_party" and own:
        return Block("own_account", "14", "That account is the customer's own: use own_accounts.")
    if kind != "third_party" and not own:
        return Block("destination_unavailable", "14", "That product is not the customer's.")
    if kind == "pay_debt":
        if not can_be_paid(destination):
            return Block("nothing_to_pay", "14", "That card or loan has nothing owed.")
    elif not can_receive(destination) or (
        kind == "third_party" and destination.get("customer_status") != "Active"
    ):
        return Block("destination_unavailable", "14", "That account cannot receive money.")
    if destination.get("currency") != currency:
        return Block(
            "currency_mismatch",
            "57",
            f"The origin is in {currency} and the destination in {destination.get('currency')}: "
            "both must be in the same currency.",
        )
    if amount > origin["current_balance"]:
        return Block(
            "insufficient_funds",
            "51",
            f"The account has {origin['current_balance']:.2f} {currency}.",
        )
    if kind == "pay_debt" and amount > destination["current_balance"]:
        return Block(
            "over_debt", "13", f"The debt is {destination['current_balance']:.2f} {currency}."
        )
    if kind == "third_party":
        if amount_usd is None:
            return Block(
                "limit_unknown", "96", f"No exchange rate for {currency} to check the limit."
            )
        if amount_usd > limits.per_operation_usd:
            return Block(
                "over_operation_limit",
                "61",
                f"The limit per operation is USD {limits.per_operation_usd:.2f} or its equivalent.",
            )
        if sent_today_usd + amount_usd > limits.per_day_usd:
            return Block(
                "over_daily_limit",
                "61",
                f"The daily limit is USD {limits.per_day_usd:.2f} or its equivalent.",
            )
    return None
