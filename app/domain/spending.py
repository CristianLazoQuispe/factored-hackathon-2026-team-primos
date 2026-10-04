"""Spending and complaint figures, shaped from warehouse rows. Pure functions, no I/O.

Spending is Approved purchases. Everything is kept per currency: amounts of different currencies
are never added. A part whose lookup did not run is simply not in `parts`, so it is left out of
the result instead of showing as zero.
"""

from typing import Any

OPEN_STATUSES = ("Open", "In Process", "Escalated")
# The source never closes most cases: two thirds of the "open" ones are over a year old. An open
# case older than this (at the dataset's last day) is reported as stale, not as being handled.
STALE_AFTER_DAYS = 90
LATEST_COMPLAINTS = 10
_LISTS = ("by_category", "top_merchants", "monthly")


def change_pct(current: float | None, previous: float | None) -> float | None:
    """Change against the previous period. Unknown when there was no previous spending."""
    if current is None or not previous:
        return None
    return round((current - previous) / previous * 100, 1)


def tx_per_week(transactions: int, days: int) -> float:
    return round(transactions * 7 / days, 1)


def _money(row: dict[str, Any]) -> dict[str, Any]:
    """The row without its currency (the block already says it) and without its unknowns."""
    return {
        key: round(value, 2) if isinstance(value, float) else value
        for key, value in row.items()
        if key != "currency" and value is not None
    }


def summarize(days: int, parts: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """One block per currency from the lookups that ran (`parts`: lookup name -> its rows)."""
    blocks: dict[str, dict[str, Any]] = {}
    for row in parts.get("totals", []):
        block = blocks.setdefault(row["currency"], {"currency": row["currency"]}) | _money(row)
        change = change_pct(row.get("spend"), row.get("previous_spend"))
        if change is not None:
            block["change_pct"] = change
        block["tx_per_week"] = tx_per_week(row["transactions"], days)
        blocks[row["currency"]] = block
    for name in _LISTS:
        for row in parts.get(name, []):
            block = blocks.setdefault(row["currency"], {"currency": row["currency"]})
            block.setdefault(name, []).append(_money(row))
    for row in parts.get("foreign", []):
        block = blocks.setdefault(row["currency"], {"currency": row["currency"]})
        block["foreign"] = _money(row)
    return [blocks[currency] for currency in sorted(blocks)]


def complaints_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """`rows`: the customer's complaints, newest first, each with `stale` (still open and older
    than STALE_AFTER_DAYS)."""
    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
    stale = sum(1 for row in rows if row["status"] in OPEN_STATUSES and row.get("stale"))
    return {
        "count": len(rows),
        "open": sum(by_status.get(status, 0) for status in OPEN_STATUSES) - stale,
        "stale_open": stale,
        "by_status": [{"status": s, "count": by_status[s]} for s in sorted(by_status)],
        "latest": rows[:LATEST_COMPLAINTS],
    }
