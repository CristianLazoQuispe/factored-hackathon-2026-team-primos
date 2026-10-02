"""Facts about a charge, mapped from warehouse rows. Pure functions, no I/O.

Rules carried over from the reviewed-SQL packs this was modelled on:
- A value the warehouse did not return stays absent. Never 0, never False by default.
- "The lookup ran and found nothing" (`found: False`) is a real answer. "The lookup failed" is
  not: the application reports it under `unavailable`, and it is never read as a "no".
"""

import unicodedata
from typing import Any

DUPLICATE_WINDOW_SECONDS = 600  # same merchant + amount within 10 minutes


def _same_country(a: str, b: str) -> bool:
    def fold(name: str) -> str:
        return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().casefold()

    return fold(a.strip()) == fold(b.strip())


def duplicate_facts(row: dict[str, Any] | None) -> dict[str, Any]:
    """`row` is the closest twin charge, or None when the lookup ran and found none."""
    if row is None:
        return {"found": False}
    return {
        "found": True,
        "duplicate_of": row["transaction_id"],
        "seconds_apart": row["seconds_apart"],
        "merchant_name": row["merchant_name"],
        "amount": row["amount"],
        "currency": row["currency"],
    }


def pending_facts(transaction: dict[str, Any]) -> dict[str, Any]:
    status = transaction["transaction_status"]
    return {
        "status": status,
        "is_pending": status == "Pending",
        "is_reversed": status == "Reversed",
    }


def fx_facts(
    transaction: dict[str, Any], home_country: str | None, rate: dict[str, Any] | None
) -> dict[str, Any]:
    """Foreign-purchase flag; for foreign purchases also the reference USD rate of that date."""
    facts: dict[str, Any] = {}
    place = transaction.get("transaction_country")
    if place and home_country:
        facts["is_foreign"] = not _same_country(place, home_country)
        facts["transaction_country"] = place
        facts["home_country"] = home_country
    if facts.get("is_foreign") and rate is not None and transaction["currency"] != "USD":
        facts["reference_rate_to_usd"] = rate["exchange_rate"]
        facts["reference_rate_date"] = rate["date"].isoformat()
        facts["amount_usd_at_reference_rate"] = round(
            transaction["amount"] * rate["exchange_rate"], 2
        )
    return facts
