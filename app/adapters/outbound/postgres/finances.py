"""Reviewed SQL for the customer's own finances screen. No LLM writes any of it.

Every statement filters by `customer_id` inside the query. Like the spending summary, "the last N
days" is counted back from the dataset's last transaction, the same day for every customer.
"""

from app.adapters.outbound.postgres import query

_ANCHOR = "WITH anchor AS (SELECT max(transaction_date) AS at FROM core.transactions)"
# The country of the customer and the product they buy with most often (a count, not a sum: the
# amounts of different currencies are never added).
FACTS = """
    SELECT c.country,
           (SELECT p.product_type
              FROM core.transactions t JOIN core.products p ON p.product_id = t.product_id
             WHERE t.customer_id = c.customer_id
               AND t.transaction_type = 'Purchase' AND t.transaction_status = 'Approved'
             GROUP BY p.product_type ORDER BY count(*) DESC, p.product_type LIMIT 1
           ) AS product_type
    FROM core.customers c WHERE c.customer_id = %(customer_id)s
"""
# Two purchases of the same merchant and amount within the window, each pair once. The same rule
# the agent uses when it investigates a charge (investigate_charge): Approved or Pending.
DUPLICATES = (
    _ANCHOR
    + """
    SELECT a.merchant_name, a.amount, a.currency,
           least(a.transaction_date, b.transaction_date) AS at,
           abs(extract(epoch FROM (b.transaction_date - a.transaction_date)))::int AS seconds_apart
    FROM core.transactions a
    JOIN core.transactions b
      ON b.customer_id = a.customer_id AND b.transaction_id > a.transaction_id
     AND b.merchant_name = a.merchant_name AND b.amount = a.amount AND b.currency = a.currency
     AND b.transaction_type = 'Purchase' AND b.transaction_status IN ('Approved', 'Pending')
     AND abs(extract(epoch FROM (b.transaction_date - a.transaction_date))) <= %(window)s,
    anchor
    WHERE a.customer_id = %(customer_id)s
      AND a.transaction_type = 'Purchase' AND a.transaction_status IN ('Approved', 'Pending')
      AND least(a.transaction_date, b.transaction_date)
          > anchor.at - make_interval(days => %(days)s)
    ORDER BY at DESC, a.transaction_id
"""
)
LARGEST = (
    _ANCHOR
    + """
    SELECT t.merchant_name, t.amount
    FROM core.transactions t, anchor
    WHERE t.customer_id = %(customer_id)s AND t.currency = %(currency)s
      AND t.transaction_type = 'Purchase' AND t.transaction_status = 'Approved'
      AND t.transaction_date > anchor.at - make_interval(days => %(days)s)
    ORDER BY t.amount DESC, t.transaction_date DESC, t.transaction_id
    LIMIT 1
"""
)


class PostgresFinances:
    async def facts(self, customer_id: str) -> dict | None:
        rows = await query(FACTS, {"customer_id": customer_id})
        return rows[0] if rows else None

    async def duplicates(self, customer_id: str, days: int, window_seconds: int) -> list[dict]:
        params = {"customer_id": customer_id, "days": days, "window": window_seconds}
        return await query(DUPLICATES, params)

    async def largest_purchase(self, customer_id: str, days: int, currency: str) -> dict | None:
        rows = await query(
            LARGEST, {"customer_id": customer_id, "days": days, "currency": currency}
        )
        return rows[0] if rows else None
