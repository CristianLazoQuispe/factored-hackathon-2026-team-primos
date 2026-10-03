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
# billing is team-generated (see schema.sql): a product without a billing row has no schedule.
DEBTS = """
    SELECT p.product_type, p.product_number_last4, p.currency, p.current_balance AS debt,
           p.interest_rate, p.days_past_due, p.product_status, b.statement_date, b.due_date,
           b.statement_balance, b.minimum_payment, b.past_due_amount, b.remaining_installments,
           b.as_of
    FROM core.products p
    LEFT JOIN core.billing b ON b.product_id = p.product_id
    WHERE p.customer_id = %(customer_id)s AND p.product_type = ANY(%(product_types)s)
    ORDER BY p.product_type, p.product_number_last4
"""
PROFILE = """
    SELECT first_name, last_name, city, country, segment, preferred_language, customer_status,
           registration_date AS customer_since, (SELECT max(date) FROM core.fx_rates) AS as_of
    FROM core.customers WHERE customer_id = %(customer_id)s
"""
PRODUCTS_HELD = """
    SELECT product_type, count(*) AS products,
           count(*) FILTER (WHERE product_status = 'Active') AS active
    FROM core.products WHERE customer_id = %(customer_id)s
    GROUP BY product_type ORDER BY product_type
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


async def fetch_debts(customer_id: str, product_types: list[str]) -> list[dict]:
    return await query(DEBTS, {"customer_id": customer_id, "product_types": product_types})


async def fetch_profile(customer_id: str) -> dict | None:
    rows = await query(PROFILE, {"customer_id": customer_id})
    return rows[0] if rows else None


async def fetch_products_held(customer_id: str) -> list[dict]:
    return await query(PRODUCTS_HELD, {"customer_id": customer_id})


async def find_customer(customer_id: str) -> dict | None:
    rows = await query(CUSTOMER, {"customer_id": customer_id})
    return rows[0] if rows else None


async def list_customers(customer_ids: list[str]) -> list[dict]:
    rows = {r["customer_id"]: r for r in await query(CUSTOMERS, {"ids": customer_ids})}
    return [rows[i] for i in customer_ids if i in rows]
