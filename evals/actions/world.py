# ruff: noqa: E501  (SQL statements stay on one line each, so they read as the table they fill)
"""The customers an action eval runs for: built in `core` for one scenario, removed afterwards.

Each scenario gets customers of its own (`DEMO-EVL-<8 hex>`; the agent only recognises an ID typed in
the chat if it starts with CLI- or DEMO-), so none depends on what another did to a card or a case. They are real rows in the developer's database, in the same tables the agent
reads, and they are removed by a pattern that no real customer can match.
"""

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import psycopg

from app.config import Settings, get_settings

# Exactly the shape of the test customers, anchored at both ends: TEST-ACT-/TEST-OTH- and eight lower
# case hex digits (SQL tests), DEMO-EVL- and eight upper case ones (evals: the agent upper-cases an ID
# typed in the chat before looking it up). No real customer (CLI-..., DEMO-MX-FX...) can match.
TEST_CUSTOMER_ID = r"^(TEST-(ACT|OTH)-[0-9a-f]{8}|DEMO-EVL-[0-9A-F]{8})$"
OPS_TABLES = ("actions", "outbox", "preferences", "card_actions", "handoff_cases", "disputes")
CORE_TABLES = ("billing", "transactions", "products", "customers")
CREDIT, DEBIT, SAVINGS = "Tarjeta Crédito", "Tarjeta Débito", "Cuenta Ahorro"
DEBT_TYPES = (CREDIT, "Préstamo Personal", "Préstamo Hipotecario")


# Customers are written to the database: only the one every developer has, unless asked for another.
DEVELOPMENT_DATABASE = Settings.model_fields["database_url"].default
UNREACHABLE = (
    "postgresql://nobody:nobody@127.0.0.1:1/none"  # what tests are given instead of a shared one
)


def is_development_database() -> bool:
    """Is this the database tests and evals may write to? The development one, or one the developer
    says is not shared (ALLOW_TEST_DATABASE=1). The Cloud SQL proxy on localhost is not."""
    return (
        get_settings().database_url == DEVELOPMENT_DATABASE
        or os.environ.get("ALLOW_TEST_DATABASE") == "1"
    )


@dataclass(frozen=True)
class Card:
    name: str
    type: str
    last4: str
    balance: float
    status: str = "Active"
    days_past_due: int = 0


@dataclass(frozen=True)
class Charge:
    name: str
    status: str
    merchant: str
    amount: float
    card: str
    country: str = "México"
    fraud: bool = False
    score: float = 5.0
    age_days: int = 7
    seconds: int = 0


UBER = (
    Charge("uber1", "Approved", "Uber Trip", 312.40, "main", age_days=7),
    Charge("uber2", "Approved", "Uber Trip", 312.40, "main", age_days=7, seconds=4),
)
SHOPS = (
    Charge("shop1", "Approved", "OXXO", 85.00, "main", age_days=20),
    Charge("shop2", "Approved", "Amazon", 640.00, "main", age_days=12),
)
MAIN = Card("main", CREDIT, "2951", 8100.0)

# fixture -> (cards, charges, email?). The first card is the one called "main" in the charges.
FIXTURES: dict[str, tuple[tuple[Card, ...], tuple[Charge, ...], bool]] = {
    "single": ((MAIN,), UBER + SHOPS, True),
    "two_cards": ((MAIN, Card("debit", DEBIT, "0042", 500.0)), UBER + SHOPS, True),
    "cancelable": (
        (Card("main", DEBIT, "0042", 500.0), Card("savings", SAVINGS, "7777", 900.0)),
        SHOPS,
        True,
    ),
    "indebted": ((Card("main", CREDIT, "2951", 1000.0, days_past_due=12),), SHOPS, True),
    "bank_blocked": ((Card("main", CREDIT, "2951", 8100.0, status="Blocked"),), SHOPS, True),
    "fraud": (
        (MAIN,),
        UBER
        + (
            Charge(
                "fraud",
                "Approved",
                "Tienda X",
                999.00,
                "main",
                "Rusia",
                fraud=True,
                score=91.0,
                age_days=2,
            ),
        ),
        True,
    ),
    "charges": (
        (MAIN,),
        UBER
        + (
            Charge("reversed", "Reversed", "Cine", 80.00, "main", age_days=9),
            Charge("pending_new", "Pending", "Gasolinera", 600.00, "main", age_days=1),
            Charge("pending_old", "Pending", "Hotel Sol", 700.00, "main", age_days=6),
        ),
        True,
    ),
    "no_email": ((MAIN,), UBER, False),
    # Somebody else's customer, never the one a scenario signs in as: its card ends in 9090.
    "neighbor": (
        (Card("main", CREDIT, "9090", 3000.0),),
        (Charge("walmart", "Approved", "Walmart", 1500.0, "main", age_days=3),),
        True,
    ),
}


@dataclass
class Customer:
    id: str
    country: str
    segment: str
    cards: dict[str, str]  # name -> product_id
    charges: dict[str, str]  # name -> transaction_id
    last4: dict[str, str] = field(default_factory=dict)  # name -> last 4 digits
    neighbor: "Customer | None" = None  # a customer whose things this one must never reach


def _connect():
    settings = get_settings()
    if settings.app_env != "local":
        raise SystemExit("The action evals build customers in the database: local only.")
    if not is_development_database():
        raise SystemExit(
            "This writes test customers into the database, and the database in use is not the development "
            f"one ({DEVELOPMENT_DATABASE}). Cloud SQL through the proxy is not. If it is yours and not "
            "shared, set ALLOW_TEST_DATABASE=1."
        )
    return psycopg.connect(settings.database_url, connect_timeout=5)


def dataset_day() -> datetime:
    with _connect() as conn:
        return conn.execute("SELECT max(transaction_date) FROM core.transactions").fetchone()[0]


def build(
    fixture: str, segment: str, country: str, language: str, neighbor: bool = False
) -> Customer:
    cards, charges, with_email = FIXTURES[fixture]
    tag = uuid.uuid4().hex[:8].upper()
    customer = Customer(f"DEMO-EVL-{tag}", country, segment, {}, {})
    day = dataset_day()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO core.customers (customer_id, country, segment, preferred_language, email, first_name) "
            "VALUES (%s, %s, %s, %s, %s, 'Prueba')",
            (
                customer.id,
                country,
                segment,
                language,
                f"{customer.id.lower()}@demo.bank" if with_email else None,
            ),
        )
        for card in cards:
            product = f"{customer.id}-{card.name}"
            customer.cards[card.name], customer.last4[card.name] = product, card.last4
            conn.execute(
                "INSERT INTO core.products (product_id, customer_id, product_type, product_number_last4, currency, "
                "current_balance, credit_limit, product_status, days_past_due) VALUES (%s,%s,%s,%s,%s,%s,27000,%s,%s)",
                (product, customer.id, card.type, card.last4, "USD" if country == "Brazil" else "MXN",
                 card.balance, card.status, card.days_past_due),
            )  # fmt: skip
            if (
                card.type in DEBT_TYPES and card.status != "Closed"
            ):  # the billing rule other tests check
                late = card.days_past_due
                due = day.date() - timedelta(days=late) if late else day.date() + timedelta(days=10)
                minimum = min(100.0, card.balance) if late else min(450.0, card.balance)
                conn.execute(
                    "INSERT INTO core.billing (product_id, customer_id, as_of, statement_date, due_date, "
                    "minimum_payment, past_due_amount) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (product, customer.id, day.date(), day.date() - timedelta(days=30), due, minimum,
                     minimum if late else 0),
                )  # fmt: skip
        for charge in charges:
            tx = f"{customer.id}-{charge.name}"
            customer.charges[charge.name] = tx
            when = day.replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(
                days=charge.age_days
            )
            conn.execute(
                "INSERT INTO core.transactions (transaction_id, customer_id, product_id, transaction_date, "
                "transaction_type, amount, currency, merchant_name, transaction_country, transaction_status, "
                "is_fraud, fraud_score) VALUES (%s,%s,%s,%s,'Purchase',%s,'MXN',%s,%s,%s,%s,%s)",
                (tx, customer.id, customer.cards[charge.card], when + timedelta(seconds=charge.seconds),
                 charge.amount, charge.merchant, charge.country, charge.status, charge.fraud, charge.score),
            )  # fmt: skip
    if neighbor:
        customer.neighbor = build("neighbor", "Basic", "México", "es")
    return customer


# The audit has no customer column: what was proposed carries the ids of the card or charge, which for a
# test customer start with its own id. Contains, not anchored; the shape is as strict as the customer's.
AUDIT_OF_A_TEST_CUSTOMER = r"(TEST-(ACT|OTH)-[0-9a-f]{8}|DEMO-EVL-[0-9A-F]{8})"


def _chat_memory_ready(conn) -> bool:
    """Has 003_chat_memory.sql been applied here? Without it there is nothing of the chat to clean."""
    found = conn.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'ops' AND table_name = 'conversations' AND column_name = 'customer_id'"
    ).fetchone()
    return found is not None


def drop(customer: Customer) -> None:
    ids = [customer.id] + ([customer.neighbor.id] if customer.neighbor else [])
    with _connect() as conn:
        for schema, tables in (("ops", OPS_TABLES), ("core", CORE_TABLES)):
            for table in tables:
                conn.execute(f"DELETE FROM {schema}.{table} WHERE customer_id = ANY(%s)", (ids,))
        for one in ids:
            conn.execute("DELETE FROM ops.decision_log WHERE proposed::text LIKE %s", (f"%{one}%",))
        if _chat_memory_ready(conn):
            conn.execute(
                "DELETE FROM ops.messages WHERE conversation_id IN "
                "(SELECT conversation_id FROM ops.conversations WHERE customer_id = ANY(%s))",
                (ids,),
            )
            conn.execute("DELETE FROM ops.conversations WHERE customer_id = ANY(%s)", (ids,))


def purge() -> None:
    """Whatever an interrupted run left, by the strict pattern, in one transaction."""
    try:
        conn = _connect()
    except (Exception, SystemExit):  # noqa: BLE001 - no local database: nothing to clean
        return
    with conn:
        has_ops = conn.execute("SELECT to_regclass('ops.actions')").fetchone()[0] is not None
        tables = [("ops", t) for t in OPS_TABLES if has_ops] + [("core", t) for t in CORE_TABLES]
        for schema, table in tables:
            conn.execute(
                f"DELETE FROM {schema}.{table} WHERE customer_id ~ %s", (TEST_CUSTOMER_ID,)
            )
        if has_ops:
            conn.execute(
                "DELETE FROM ops.decision_log WHERE proposed::text ~ %s",
                (AUDIT_OF_A_TEST_CUSTOMER,),
            )
        if has_ops and _chat_memory_ready(conn):
            conn.execute(
                "DELETE FROM ops.messages WHERE conversation_id IN "
                "(SELECT conversation_id FROM ops.conversations WHERE customer_id ~ %s)",
                (TEST_CUSTOMER_ID,),
            )
            conn.execute(
                "DELETE FROM ops.conversations WHERE customer_id ~ %s", (TEST_CUSTOMER_ID,)
            )
