"""Reviewed SQL for the `data_lookup` skill's fixed questions. No LLM writes any of it.

Every statement filters by `customer_id` inside the query. The dataset is static (it ends in June
2026), so "the last N days" is counted back from the dataset's last transaction, the same day for
every customer, not from today. Spending is Approved purchases, always grouped by currency.
"""

from datetime import date

from app.adapters.outbound.postgres import query

# Approved purchases of the last 2 x days; `in_window` marks the latest `days`, the rest is the
# period before it (only TOTALS reads that one).
_PURCHASES = """
    WITH anchor AS (SELECT max(transaction_date) AS at FROM core.transactions),
    purchases AS (
        SELECT t.*, t.transaction_date > a.at - make_interval(days => %(days)s) AS in_window
        FROM core.transactions t, anchor a
        WHERE t.customer_id = %(customer_id)s
          AND t.transaction_type = 'Purchase' AND t.transaction_status = 'Approved'
          AND t.transaction_date > a.at - make_interval(days => 2 * %(days)s))
"""
TOTALS = (
    _PURCHASES
    + """
    SELECT currency, sum(amount) FILTER (WHERE in_window) AS spend,
           coalesce(sum(amount) FILTER (WHERE NOT in_window), 0) AS previous_spend,
           count(*) FILTER (WHERE in_window) AS transactions,
           avg(amount) FILTER (WHERE in_window) AS avg_ticket,
           max(amount) FILTER (WHERE in_window) AS max_ticket
    FROM purchases GROUP BY currency HAVING count(*) FILTER (WHERE in_window) > 0
"""
)
BY_CATEGORY = (
    _PURCHASES
    + """
    SELECT currency, coalesce(transaction_category, 'Uncategorized') AS category,
           sum(amount) AS amount, count(*) AS transactions
    FROM purchases WHERE in_window GROUP BY 1, 2 ORDER BY amount DESC
"""
)
TOP_MERCHANTS = (
    _PURCHASES
    + """
    SELECT currency, merchant_name, amount, transactions FROM (
        SELECT currency, merchant_name, sum(amount) AS amount, count(*) AS transactions,
               row_number() OVER (PARTITION BY currency ORDER BY sum(amount) DESC) AS position
        FROM purchases WHERE in_window AND merchant_name IS NOT NULL GROUP BY 1, 2) ranked
    WHERE position <= 5 ORDER BY amount DESC
"""
)
MONTHLY = (
    _PURCHASES
    + """
    SELECT currency, to_char(transaction_date, 'YYYY-MM') AS month, sum(amount) AS amount,
           count(*) AS transactions
    FROM purchases WHERE in_window GROUP BY 1, 2 ORDER BY month
"""
)
FOREIGN = (
    _PURCHASES
    + """
    SELECT p.currency, count(*) FILTER (WHERE p.transaction_country <> c.country) AS transactions,
           coalesce(sum(p.amount) FILTER (WHERE p.transaction_country <> c.country), 0) AS amount
    FROM purchases p JOIN core.customers c ON c.customer_id = p.customer_id
    WHERE p.in_window GROUP BY 1
"""
)
MOVEMENTS = """
    SELECT t.transaction_date, t.transaction_type, t.amount, t.currency, t.merchant_name,
           t.transaction_category, t.channel, t.transaction_status, t.transaction_country,
           t.transaction_city, p.product_type, p.product_number_last4
    FROM core.transactions t
    LEFT JOIN core.products p ON p.product_id = t.product_id AND p.customer_id = t.customer_id
    WHERE t.customer_id = %(customer_id)s
      AND t.transaction_date >= (SELECT max(transaction_date) FROM core.transactions)
          - make_interval(days => %(days)s)
      AND (%(product_type)s::text IS NULL OR p.product_type = %(product_type)s)
      AND (%(last4)s::text IS NULL OR p.product_number_last4 = %(last4)s)
      AND (%(transaction_type)s::text IS NULL OR t.transaction_type = %(transaction_type)s)
      AND (%(status)s::text IS NULL OR t.transaction_status = %(status)s)
      AND (%(category)s::text IS NULL OR t.transaction_category = %(category)s)
      AND (%(merchant)s::text IS NULL
           OR position(lower(%(merchant)s) IN lower(coalesce(t.merchant_name, ''))) > 0)
      AND (%(min_amount)s::numeric IS NULL OR t.amount >= %(min_amount)s)
      AND (%(max_amount)s::numeric IS NULL OR t.amount <= %(max_amount)s)
    ORDER BY CASE WHEN %(largest)s THEN t.amount END DESC NULLS LAST, t.transaction_date DESC
    LIMIT %(limit)s
"""
COMPLAINTS = """
    SELECT creation_date, case_type, category, subcategory, reception_channel, priority, status,
           claimed_amount, currency, resolution_date
    FROM core.complaints
    WHERE customer_id = %(customer_id)s
    ORDER BY creation_date DESC
"""
EXCHANGE_RATE = """
    SELECT date, source_currency, target_currency, exchange_rate, buy_rate, sell_rate
    FROM core.fx_rates
    WHERE source_currency = %(source)s AND target_currency = %(target)s
      AND (%(on)s::date IS NULL OR date <= %(on)s)
    ORDER BY date DESC
    LIMIT 1
"""


class PostgresSpending:
    async def totals(self, customer_id: str, days: int) -> list[dict]:
        return await query(TOTALS, {"customer_id": customer_id, "days": days})

    async def by_category(self, customer_id: str, days: int) -> list[dict]:
        return await query(BY_CATEGORY, {"customer_id": customer_id, "days": days})

    async def top_merchants(self, customer_id: str, days: int) -> list[dict]:
        return await query(TOP_MERCHANTS, {"customer_id": customer_id, "days": days})

    async def monthly(self, customer_id: str, days: int) -> list[dict]:
        return await query(MONTHLY, {"customer_id": customer_id, "days": days})

    async def foreign(self, customer_id: str, days: int) -> list[dict]:
        return await query(FOREIGN, {"customer_id": customer_id, "days": days})

    async def movements(self, customer_id: str, limit: int, **filters) -> list[dict]:
        """`filters`: the MOVEMENTS parameters other than the customer and the limit."""
        return await query(MOVEMENTS, {"customer_id": customer_id, "limit": limit} | filters)

    async def complaints(self, customer_id: str) -> list[dict]:
        return await query(COMPLAINTS, {"customer_id": customer_id})

    async def exchange_rate(self, source: str, target: str, on: date | None) -> dict | None:
        rows = await query(EXCHANGE_RATE, {"source": source, "target": target, "on": on})
        return rows[0] if rows else None
