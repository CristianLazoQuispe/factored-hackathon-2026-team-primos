"""Customer and product lookups against `core` (see schema.sql). Read-only."""

from app.adapters.outbound.postgres import query

BALANCES = """
    SELECT product_type, product_number_last4, currency, current_balance, credit_limit,
           product_status
    FROM core.products
    WHERE customer_id = %(customer_id)s
      AND (%(product_type)s::text IS NULL OR product_type = %(product_type)s)
    ORDER BY product_type, product_number_last4
"""
CUSTOMERS = """
    SELECT customer_id, first_name, country, segment
    FROM core.customers WHERE customer_id = ANY(%(ids)s)
"""
CUSTOMER = """
    SELECT customer_id, first_name, preferred_language, customer_status
    FROM core.customers WHERE customer_id = %(customer_id)s
"""


async def fetch_balances(customer_id: str, product_type: str | None = None) -> list[dict]:
    return await query(BALANCES, {"customer_id": customer_id, "product_type": product_type})


async def find_customer(customer_id: str) -> dict | None:
    rows = await query(CUSTOMER, {"customer_id": customer_id})
    return rows[0] if rows else None


async def list_customers(customer_ids: list[str]) -> list[dict]:
    rows = {r["customer_id"]: r for r in await query(CUSTOMERS, {"ids": customer_ids})}
    return [rows[i] for i in customer_ids if i in rows]
