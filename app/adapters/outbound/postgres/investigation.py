"""Reviewed SQL for the `charge_investigation` skill. No LLM writes any of it.

Every statement filters by `customer_id` inside the query, so a transaction id that belongs to
someone else returns nothing. The dataset is static (it ends in June 2026), so "the last N days"
is counted back from the dataset's last transaction (the same day for everyone), not from today.

Known limits, on purpose:
- Duplicates need an equal `merchant_name`; a NULL merchant never matches.
- Only Approved/Pending charges count as a possible double charge (a Declined twin costs nothing).
- The FX reference rate is the latest rate within 7 days before the charge; no rate, no FX figure.
"""

from datetime import date

from app.adapters.outbound.postgres import query

TRANSACTION = """
    SELECT transaction_id, transaction_date, amount, currency, merchant_name, channel,
           transaction_status, transaction_country, transaction_city
    FROM core.transactions
    WHERE customer_id = %(customer_id)s AND transaction_id = %(transaction_id)s
"""
DUPLICATE = """
    SELECT o.transaction_id, o.amount, o.currency, o.merchant_name,
           abs(extract(epoch FROM (t.transaction_date - o.transaction_date)))::int AS seconds_apart
    FROM core.transactions t
    JOIN core.transactions o
      ON o.customer_id = t.customer_id
     AND o.transaction_id <> t.transaction_id
     AND o.merchant_name = t.merchant_name
     AND o.amount = t.amount
     AND o.currency = t.currency
     AND o.transaction_status IN ('Approved', 'Pending')
     AND abs(extract(epoch FROM (t.transaction_date - o.transaction_date))) <= %(window)s
    WHERE t.customer_id = %(customer_id)s
      AND t.transaction_id = %(transaction_id)s
      AND t.transaction_status IN ('Approved', 'Pending')
    ORDER BY seconds_apart, o.transaction_id
    LIMIT 1
"""
HOME_COUNTRY = "SELECT country FROM core.customers WHERE customer_id = %(customer_id)s"
FX_RATE = """
    SELECT date, exchange_rate
    FROM core.fx_rates
    WHERE source_currency = %(currency)s AND target_currency = 'USD'
      AND date <= %(on)s AND date >= %(on)s - 7
    ORDER BY date DESC
    LIMIT 1
"""
SEARCH = """
    SELECT transaction_id, transaction_date, amount, currency, merchant_name, transaction_status
    FROM core.transactions
    WHERE customer_id = %(customer_id)s
      AND transaction_date >= (SELECT max(transaction_date) FROM core.transactions)
          - make_interval(days => %(days)s)
      AND (%(merchant)s::text IS NULL
           OR position(lower(%(merchant)s) IN lower(coalesce(merchant_name, ''))) > 0)
      AND (%(min_amount)s::numeric IS NULL OR amount >= %(min_amount)s)
      AND (%(max_amount)s::numeric IS NULL OR amount <= %(max_amount)s)
    ORDER BY transaction_date DESC
    LIMIT 20
"""


class PostgresWarehouse:
    async def transaction(self, customer_id: str, transaction_id: str) -> dict | None:
        rows = await query(
            TRANSACTION, {"customer_id": customer_id, "transaction_id": transaction_id}
        )
        return rows[0] if rows else None

    async def duplicate_of(
        self, customer_id: str, transaction_id: str, window_seconds: int
    ) -> dict | None:
        params = {
            "customer_id": customer_id,
            "transaction_id": transaction_id,
            "window": window_seconds,
        }
        rows = await query(DUPLICATE, params)
        return rows[0] if rows else None

    async def home_country(self, customer_id: str) -> str | None:
        rows = await query(HOME_COUNTRY, {"customer_id": customer_id})
        return rows[0]["country"] if rows else None

    async def fx_rate_to_usd(self, currency: str, on: date) -> dict | None:
        rows = await query(FX_RATE, {"currency": currency, "on": on})
        return rows[0] if rows else None

    async def search(
        self,
        customer_id: str,
        days: int,
        merchant: str | None,
        min_amount: float | None,
        max_amount: float | None,
    ) -> list[dict]:
        return await query(
            SEARCH,
            {
                "customer_id": customer_id,
                "days": days,
                "merchant": merchant,
                "min_amount": min_amount,
                "max_amount": max_amount,
            },
        )
