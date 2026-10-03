"""Spending summary: what the customer spent in a period, against the one before.

Runs the reviewed lookups concurrently. A lookup that fails is listed in `unavailable` and its
figures are left out: an unknown is never reported as zero, and one failing lookup never sinks
the rest. The customer always comes from the session, never from the model.
"""

import asyncio
import logging
from typing import Any, Protocol

from app.domain.spending import summarize

log = logging.getLogger(__name__)

EVIDENCE_LOOKUP = "get_spending_summary"
LOOKUPS = ("totals", "by_category", "top_merchants", "monthly", "foreign")


class SpendingStore(Protocol):
    """Reviewed, read-only lookups over Approved purchases, scoped to `customer_id` in the query.
    `days` counts back from the customer's latest transaction."""

    async def totals(self, customer_id: str, days: int) -> list[dict]: ...

    async def by_category(self, customer_id: str, days: int) -> list[dict]: ...

    async def top_merchants(self, customer_id: str, days: int) -> list[dict]: ...

    async def monthly(self, customer_id: str, days: int) -> list[dict]: ...

    async def foreign(self, customer_id: str, days: int) -> list[dict]: ...


async def spending_summary(store: SpendingStore, customer_id: str, days: int) -> dict[str, Any]:
    results = await asyncio.gather(
        *(getattr(store, name)(customer_id, days) for name in LOOKUPS), return_exceptions=True
    )
    parts, unavailable = {}, []
    for name, result in zip(LOOKUPS, results, strict=True):
        if isinstance(result, BaseException):
            log.warning("spending_summary.%s failed: %s", name, result)
            unavailable.append(name)
        else:
            parts[name] = result
    return {
        "days": days,
        "currencies": summarize(days, parts),
        "unavailable": unavailable,
        "evidence_lookup": EVIDENCE_LOOKUP,
    }
