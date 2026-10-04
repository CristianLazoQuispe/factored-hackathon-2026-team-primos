"""The customer's own finances: what "Mis finanzas" shows.

Reuses the spending summary and adds what a screen needs on top: the product and country, the
duplicate charges and the largest purchase. The customer always comes from the session.

It is all or nothing. If any lookup fails the screen is not built: a missing duplicate check would
read as "no duplicate charges", and an unknown is never reported as a zero.
"""

import asyncio
import logging
from typing import Any, Protocol

from app.application.spending import SpendingStore, spending_summary
from app.domain.evidence import DUPLICATE_WINDOW_SECONDS
from app.domain.finances import UnknownCustomer, main_block
from app.domain.finances import own_finances as shape

log = logging.getLogger(__name__)


class FinancesUnavailable(Exception):
    """A lookup the screen depends on failed."""


class FinancesStore(Protocol):
    """Reviewed, read-only lookups, scoped to `customer_id` inside the query. `days` counts back
    from the dataset's last transaction, like the spending summary."""

    async def facts(self, customer_id: str) -> dict | None: ...

    async def duplicates(self, customer_id: str, days: int, window_seconds: int) -> list[dict]: ...

    async def largest_purchase(self, customer_id: str, days: int, currency: str) -> dict | None: ...


def _unwrap(name: str, result: Any) -> Any:
    if isinstance(result, BaseException):
        log.warning("own_finances.%s failed: %s", name, result)
        raise FinancesUnavailable(name)
    return result


async def own_finances(
    spending: SpendingStore, store: FinancesStore, customer_id: str, days: int
) -> dict[str, Any]:
    summary, facts, duplicates = await asyncio.gather(
        spending_summary(spending, customer_id, days),
        store.facts(customer_id),
        store.duplicates(customer_id, days, DUPLICATE_WINDOW_SECONDS),
        return_exceptions=True,
    )
    summary = _unwrap("spending_summary", summary)
    facts = _unwrap("facts", facts)
    duplicates = _unwrap("duplicates", duplicates)
    if summary["unavailable"]:
        raise FinancesUnavailable(", ".join(summary["unavailable"]))
    if facts is None:
        raise UnknownCustomer(customer_id)
    blocks = summary["currencies"]
    currency = main_block(blocks)["currency"]  # raises NoSpending when there is nothing
    try:
        largest = await store.largest_purchase(customer_id, days, currency)
    except Exception as error:  # the same rule: no figure is better than a wrong one
        log.warning("own_finances.largest_purchase failed: %s", error)
        raise FinancesUnavailable("largest_purchase") from None
    return shape(customer_id, days, blocks, facts, duplicates, largest)
