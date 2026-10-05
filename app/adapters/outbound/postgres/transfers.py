"""The ledger behind khipear (see app/application/transfers.py). Reviewed SQL only.

This is the one place that writes to `core`: `execute` changes two balances and adds two
movements in a single database transaction, with the proposal and both products locked. Paying a
service bill changes one balance, marks the bill paid and adds one movement, with the bill locked
the same way. In a real deployment it would call the bank's transfer API instead.
"""

from datetime import datetime

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.adapters.outbound.postgres import plain, query
from app.application.transfers import Recheck
from app.config import get_settings
from app.domain.transfers import ACCOUNT_TYPES, PAY_SERVICE, Block

_PRODUCT = """p.product_id, p.customer_id, p.product_type, p.product_number_last4, p.currency,
           p.current_balance, p.product_status"""
PRODUCTS = f"""
    SELECT {_PRODUCT}, c.customer_status
    FROM core.products p JOIN core.customers c ON c.customer_id = p.customer_id
    WHERE p.customer_id = %(customer_id)s
    ORDER BY p.product_type, p.product_number_last4, p.product_id
"""
_RECIPIENT = f"""
    SELECT {_PRODUCT}, c.first_name, c.last_name, c.customer_status
    FROM core.products p JOIN core.customers c ON c.customer_id = p.customer_id
    WHERE p.product_type = ANY(%(types)s)
"""
BY_NUMBER = _RECIPIENT + " AND p.account_number = %(account_number)s"
ACCOUNTS_OF = (
    _RECIPIENT
    + """ AND p.customer_id = %(customer_id)s
      AND p.product_status = 'Active' AND c.customer_status = 'Active'
    ORDER BY p.opening_date NULLS LAST, p.product_id"""
)
USD_RATE = """
    SELECT exchange_rate FROM core.fx_rates
    WHERE source_currency = %(currency)s AND target_currency = 'USD'
    ORDER BY date DESC LIMIT 1
"""
SENT_TODAY = """
    SELECT coalesce(sum(amount_usd), 0) AS sent FROM ops.transfers
    WHERE customer_id = %(customer_id)s AND kind = 'third_party' AND status = 'executed'
      AND executed_at >= date_trunc('day', now())
"""
_BILL = """
    SELECT b.bill_id, b.customer_id, b.biller_id, s.name, s.category, b.reference, b.amount,
           b.currency, b.due_date::text AS due_date, b.status
    FROM core.service_bills b JOIN core.service_billers s ON s.biller_id = b.biller_id
"""
PENDING_BILLS = (
    _BILL
    + """ WHERE b.customer_id = %(customer_id)s AND b.status = 'pending'
    ORDER BY b.due_date, b.bill_id"""
)
LOCK_BILL = _BILL + " WHERE b.bill_id = %(bill_id)s FOR UPDATE OF b"
PAY_BILL = """
    UPDATE core.service_bills SET status = 'paid', paid_at = now() WHERE bill_id = %(bill_id)s
"""
SAVE = """
    INSERT INTO ops.transfers (transfer_id, customer_id, kind, origin_product_id,
        destination_product_id, destination_customer_id, amount, currency, amount_usd, summary,
        expires_at)
    VALUES (%(transfer_id)s, %(customer_id)s, %(kind)s, %(origin_product_id)s,
        %(destination_product_id)s, %(destination_customer_id)s, %(amount)s, %(currency)s,
        %(amount_usd)s, %(summary)s, now() + make_interval(mins => %(minutes)s))
    RETURNING expires_at
"""
LOCK_TRANSFER = """
    SELECT *, expires_at <= now() AS expired FROM ops.transfers
    WHERE transfer_id = %(transfer_id)s AND customer_id = %(customer_id)s
    FOR UPDATE
"""
# Locked in product_id order, so two transfers between the same accounts cannot deadlock.
LOCK_PRODUCTS = f"""
    SELECT {_PRODUCT}, c.customer_status
    FROM core.products p JOIN core.customers c ON c.customer_id = p.customer_id
    WHERE p.product_id = ANY(%(ids)s)
    ORDER BY p.product_id
    FOR UPDATE OF p
"""
CLOSE = """
    UPDATE ops.transfers SET status = %(status)s, status_reason = %(reason)s
    WHERE transfer_id = %(transfer_id)s
"""
MOVE = """
    UPDATE core.products SET current_balance = current_balance + %(delta)s
    WHERE product_id = %(product_id)s
    RETURNING current_balance
"""
# Dated at the dataset's last moment, not now(): every "last 30 days" in the agent counts back
# from max(transaction_date), and a movement dated today would empty those windows.
MOVEMENT = """
    INSERT INTO core.transactions (transaction_id, customer_id, product_id, transaction_date,
        transaction_type, transaction_category, merchant_name, amount, currency, amount_usd,
        channel, transaction_status, response_code, is_fraud)
    SELECT %(transaction_id)s, %(customer_id)s, %(product_id)s,
        coalesce((SELECT max(transaction_date) FROM core.transactions), now()::timestamp),
        %(transaction_type)s, %(category)s, %(merchant)s, %(amount)s, %(currency)s,
        %(amount_usd)s, 'App', 'Approved', '00', false
"""
EXECUTED = """
    UPDATE ops.transfers
    SET status = 'executed', executed_at = now(), origin_balance_after = %(balance)s
    WHERE transfer_id = %(transfer_id)s
    RETURNING executed_at
"""
CANCEL = """
    UPDATE ops.transfers SET status = 'cancelled'
    WHERE transfer_id = %(transfer_id)s AND customer_id = %(customer_id)s AND status = 'proposed'
    RETURNING transfer_id
"""
GONE = Block("origin_unavailable", "57", "One of the accounts is no longer there.")


def _receipt(transfer: dict, balance: float, executed_at: datetime) -> dict:
    summary = transfer["summary"]
    return {
        "status": "executed",
        "receipt": {
            "transfer_id": str(transfer["transfer_id"]),
            "kind": transfer["kind"],
            "amount": transfer["amount"],
            "currency": transfer["currency"],
            "origin": summary["origin"] | {"new_balance": balance},
            "destination": summary["destination"],
            "executed_at": executed_at.isoformat(),
        },
    }


class PostgresLedger:
    async def products(self, customer_id: str) -> list[dict]:
        return await query(PRODUCTS, {"customer_id": customer_id})

    async def account_by_number(self, account_number: str) -> dict | None:
        rows = await query(
            BY_NUMBER, {"types": list(ACCOUNT_TYPES), "account_number": account_number}
        )
        return rows[0] if rows else None

    async def accounts_of(self, customer_id: str) -> list[dict]:
        return await query(ACCOUNTS_OF, {"types": list(ACCOUNT_TYPES), "customer_id": customer_id})

    async def usd_rate(self, currency: str) -> float | None:
        if currency == "USD":
            return 1.0
        rows = await query(USD_RATE, {"currency": currency})
        return rows[0]["exchange_rate"] if rows else None

    async def sent_today_usd(self, customer_id: str) -> float:
        return (await query(SENT_TODAY, {"customer_id": customer_id}))[0]["sent"]

    async def pending_bills(self, customer_id: str) -> list[dict]:
        return await query(PENDING_BILLS, {"customer_id": customer_id})

    async def save(self, proposal: dict) -> datetime:
        summary = {"origin": proposal["origin"], "destination": proposal["destination"]}
        minutes = get_settings().khipu_confirmation_minutes
        rows = await query(SAVE, proposal | {"summary": Jsonb(summary), "minutes": minutes})
        return rows[0]["expires_at"]

    async def execute(self, transfer_id: str, customer_id: str, recheck: Recheck) -> dict:
        key = {"transfer_id": transfer_id, "customer_id": customer_id}
        async with (
            await psycopg.AsyncConnection.connect(
                get_settings().database_url, row_factory=dict_row
            ) as conn,
            conn.transaction(),
        ):

            async def run(sql: str, params: dict) -> list[dict]:
                cursor = await conn.execute(sql, params)
                return [plain(r) for r in await cursor.fetchall()] if cursor.description else []

            found = await run(LOCK_TRANSFER, key)
            if not found:  # same answer for "does not exist" and "belongs to someone else"
                return {"status": "not_found"}
            transfer = found[0]
            if transfer["status"] == "executed":  # a second click: same receipt, nothing moves
                return _receipt(transfer, transfer["origin_balance_after"], transfer["executed_at"])
            if transfer["status"] != "proposed":
                return {"status": transfer["status"]}
            if transfer["expired"]:
                await run(CLOSE, key | {"status": "expired", "reason": None})
                return {"status": "expired"}

            origin_id, destination_id = (
                transfer["origin_product_id"],
                transfer["destination_product_id"],
            )
            # For a service payment the destination is a bill, locked after the account.
            pays_service = transfer["kind"] == PAY_SERVICE
            ids = [origin_id] if pays_service else [origin_id, destination_id]
            products = {p["product_id"]: p for p in await run(LOCK_PRODUCTS, {"ids": ids})}
            if pays_service:
                bills = await run(LOCK_BILL, {"bill_id": destination_id})
                destination = bills[0] if bills else None
            else:
                destination = products.get(destination_id)
            block = GONE
            if origin_id in products and destination:
                sent = (await run(SENT_TODAY, key))[0]["sent"]
                block = recheck(transfer, products[origin_id], destination, sent)
            if block:
                await run(CLOSE, key | {"status": "blocked", "reason": block.reason})
                return {"status": "blocked", "block": block}

            amount, pays_debt = transfer["amount"], transfer["kind"] == "pay_debt"
            balance = (await run(MOVE, {"product_id": origin_id, "delta": -amount}))[0]
            if pays_service:
                await run(PAY_BILL, {"bill_id": destination_id})
                movements = [("O", origin_id, "Payment", "Services", destination["name"])]
            else:
                await run(
                    MOVE, {"product_id": destination_id, "delta": -amount if pays_debt else amount}
                )
                received = "Payment" if pays_debt else "Deposit"
                movements = [
                    ("O", origin_id, "Transfer", None, None),
                    ("D", destination_id, received, None, None),
                ]
            for side, product_id, transaction_type, category, merchant in movements:
                await run(
                    MOVEMENT,
                    {
                        "transaction_id": f"KHP-{transfer['transfer_id'].hex[:16].upper()}-{side}",
                        "customer_id": products[product_id]["customer_id"],
                        "product_id": product_id,
                        "transaction_type": transaction_type,
                        "category": category,
                        "merchant": merchant,
                        "amount": amount,
                        "currency": transfer["currency"],
                        "amount_usd": transfer["amount_usd"],
                    },
                )
            executed = await run(EXECUTED, key | {"balance": balance["current_balance"]})
            return _receipt(transfer, balance["current_balance"], executed[0]["executed_at"])

    async def cancel(self, transfer_id: str, customer_id: str) -> bool:
        return bool(await query(CANCEL, {"transfer_id": transfer_id, "customer_id": customer_id}))
