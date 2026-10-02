"""Investigate the bank: what the bank's own records say about one charge.

Runs the reviewed lookups (duplicate, pending, FX) concurrently. A lookup that fails is listed in
`unavailable` and its key is left out: an unknown is never reported as "no", and one failing
lookup never sinks the rest. The customer always comes from the session, never from the model.
"""

import asyncio
import logging
from datetime import date, datetime
from typing import Any, Protocol

from app.domain.evidence import (
    DUPLICATE_WINDOW_SECONDS,
    duplicate_facts,
    fx_facts,
    pending_facts,
)

log = logging.getLogger(__name__)

EVIDENCE_LOOKUP = "investigate_charge"
MAX_MATCHES = 3


class Warehouse(Protocol):
    """Reviewed, read-only lookups. Every one is scoped to `customer_id` inside the query."""

    async def transaction(self, customer_id: str, transaction_id: str) -> dict | None: ...

    async def duplicate_of(
        self, customer_id: str, transaction_id: str, window_seconds: int
    ) -> dict | None: ...

    async def search(
        self,
        customer_id: str,
        days: int,
        merchant: str | None,
        min_amount: float | None,
        max_amount: float | None,
    ) -> list[dict]: ...

    async def home_country(self, customer_id: str) -> str | None: ...

    async def fx_rate_to_usd(self, currency: str, on: date) -> dict | None: ...


async def _fx(warehouse: Warehouse, customer_id: str, transaction: dict) -> dict[str, Any]:
    when: datetime = transaction["transaction_date"]
    home, rate = await asyncio.gather(
        warehouse.home_country(customer_id),
        warehouse.fx_rate_to_usd(transaction["currency"], when.date()),
    )
    return fx_facts(transaction, home, rate)


async def investigate_charge(
    warehouse: Warehouse, customer_id: str, transaction_id: str
) -> dict[str, Any]:
    transaction = await warehouse.transaction(customer_id, transaction_id)
    if transaction is None:  # same answer for "does not exist" and "belongs to someone else"
        return {"error": "No such charge in this customer's account."}

    lookups = {
        "duplicate": warehouse.duplicate_of(customer_id, transaction_id, DUPLICATE_WINDOW_SECONDS),
        "fx": _fx(warehouse, customer_id, transaction),
    }
    results = await asyncio.gather(*lookups.values(), return_exceptions=True)

    report: dict[str, Any] = {
        "transaction": {
            key: transaction[key]
            for key in ("transaction_id", "merchant_name", "amount", "currency", "channel")
        }
        | {"transaction_date": transaction["transaction_date"].isoformat()},
        "pending": pending_facts(transaction),
    }
    unavailable = []
    for name, result in zip(lookups, results, strict=True):
        if isinstance(result, BaseException):
            log.warning("investigate_charge.%s failed: %s", name, result)
            unavailable.append(name)
        elif name == "duplicate":
            report[name] = duplicate_facts(result)
        else:
            report[name] = result
    return report | {"unavailable": unavailable, "evidence_lookup": EVIDENCE_LOOKUP}


async def investigate_matching(
    warehouse: Warehouse,
    customer_id: str,
    days: int,
    merchant: str | None,
    min_amount: float | None,
    max_amount: float | None,
) -> dict[str, Any]:
    """Find the customer's charges that fit the description (newest first, at most 3) and
    investigate each, so the model never has to chain calls to reach the evidence. Charges are
    named #1, #2, #3: internal ids are not shown to the customer, and a twin charge is reported
    by its position in this list."""
    found = (await warehouse.search(customer_id, days, merchant, min_amount, max_amount))[
        :MAX_MATCHES
    ]
    results = await asyncio.gather(
        *(investigate_charge(warehouse, customer_id, row["transaction_id"]) for row in found),
        return_exceptions=True,
    )
    ref = {row["transaction_id"]: f"#{n}" for n, row in enumerate(found, 1)}
    charges, failed = [], 0
    for n, report in enumerate(results, 1):
        if isinstance(report, BaseException) or "error" in report:
            failed += 1
            continue
        transaction = {k: v for k, v in report["transaction"].items() if k != "transaction_id"}
        charge = report | {"transaction": transaction | {"ref": f"#{n}"}}
        duplicate = report.get("duplicate")
        if duplicate and duplicate.get("found"):
            twin = ref.get(duplicate["duplicate_of"], "another charge outside this list")
            charge["duplicate"] = duplicate | {"duplicate_of": twin}
        charges.append(charge)
    return {
        "count": len(charges),
        "not_checked": failed,
        "findings": _findings(charges),
        "charges": charges,
        "evidence_lookup": "investigate_charges",
    }


def _findings(charges: list[dict]) -> list[dict]:
    """The verified facts, each listed once. A duplicate pair is ONE finding, so the model has
    nothing to count twice; the times come from the charges themselves."""
    when = {c["transaction"]["ref"]: c["transaction"]["transaction_date"] for c in charges}
    findings, seen_pairs = [], set()
    for charge in charges:
        ref = charge["transaction"]["ref"]
        duplicate = charge.get("duplicate") or {}
        if duplicate.get("found"):
            twin = duplicate["duplicate_of"]
            pair = frozenset({ref, twin})
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                in_list = sorted(r for r in pair if r in when)
                findings.append(
                    {
                        "kind": "duplicate",
                        "charges": in_list,
                        "at": [when[r] for r in in_list],
                        "merchant_name": duplicate["merchant_name"],
                        "amount": duplicate["amount"],
                        "currency": duplicate["currency"],
                        "seconds_apart": duplicate["seconds_apart"],
                    }
                )
        if charge["pending"]["is_pending"]:
            findings.append({"kind": "pending", "charges": [ref]})
        if charge["pending"]["is_reversed"]:
            findings.append({"kind": "reversed", "charges": [ref]})
        fx = charge.get("fx") or {}
        if fx.get("is_foreign"):
            findings.append(
                {"kind": "foreign_purchase", "charges": [ref], "country": fx["transaction_country"]}
                | {k: fx[k] for k in ("reference_rate_to_usd",) if k in fx}
            )
    return findings
