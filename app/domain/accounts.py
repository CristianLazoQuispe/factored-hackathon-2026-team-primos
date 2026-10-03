"""Facts about a customer's products, debts and profile, mapped from warehouse rows. Pure.

Same rules as `evidence.py`: a value the warehouse did not return stays absent (never 0), and
amounts of different currencies are never added together.
"""

from datetime import date
from typing import Any

CREDIT_CARD = "Tarjeta Crédito"
DEBT_TYPES = (CREDIT_CARD, "Préstamo Personal", "Préstamo Hipotecario")
# Debit cards are left out of the totals: the data does not say which account they draw on.
GROUPS = {
    "Cuenta Ahorro": "deposits",
    "Cuenta Corriente": "deposits",
    "Inversión": "investments",
    **dict.fromkeys(DEBT_TYPES, "debt"),
}


def present(row: dict[str, Any]) -> dict[str, Any]:
    """The row without its unknowns, dates as ISO text."""
    return {
        key: value.isoformat() if isinstance(value, date) else value
        for key, value in row.items()
        if value is not None
    }


def credit_available(product: dict[str, Any]) -> float | None:
    """What is left of a credit card's limit. Unknown when the limit or the balance is."""
    limit, balance = product.get("credit_limit"), product.get("current_balance")
    if product.get("product_type") != CREDIT_CARD or limit is None or balance is None:
        return None
    return round(max(limit - balance, 0), 2)


def balance_totals(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Active products added up per group (deposits, investments, debt) and currency."""
    totals: dict[tuple[str, str], dict[str, Any]] = {}
    for product in products:
        group, balance = GROUPS.get(product.get("product_type")), product.get("current_balance")
        if group is None or balance is None or product.get("product_status") != "Active":
            continue
        key = (group, product.get("currency"))
        total = totals.setdefault(
            key, {"group": group, "currency": key[1], "total": 0.0, "products": 0}
        )
        total["total"] = round(total["total"] + balance, 2)
        total["products"] += 1
    return [totals[key] for key in sorted(totals, key=str)]


def tenure_years(since: date | None, as_of: date | None) -> int | None:
    """Whole years as a customer. Unknown when a date is missing or the dates contradict."""
    if since is None or as_of is None or since > as_of:
        return None
    return as_of.year - since.year - ((as_of.month, as_of.day) < (since.month, since.day))
