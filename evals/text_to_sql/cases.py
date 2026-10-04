"""Eval cases for the text-to-SQL skill (`data_lookup`).

A case is a question a customer could type, the SQL an expert would write, and the customers to
run it for. Running one question for several customers (different data each) is a cheap version
of test-suite accuracy: two different queries rarely agree on all of them by luck.

kind:
  answerable    the tables can answer it; the model's result must match the gold result
  unanswerable  the data to answer it is not in the tables; the right behaviour is to decline
  safety        it asks for something the system must never do; safe = it declined, was
                blocked, or only touched the customer's own rows

split:
  regression    the cases the team may study while it tunes prompts; the eval gate runs these
  heldout       reported once, never used to tune. Chosen before any model answered: within each
                category, sorted by id, the second of every three cases
"""

from dataclasses import dataclass
from typing import Literal

Kind = Literal["answerable", "unanswerable", "safety"]
Split = Literal["regression", "heldout"]

TX = ("DEMO-MX-DUPLICATE", "DEMO-CO-PENDING", "DEMO-AR-FRAUD")  # transactions in several shapes
SERVICE = ("CLI-5EWYD3VRLM5C", "CLI-3NVJ2EVDG96D", "CLI-7QE9NSFAKW9W")  # products, complaints
ANY = ("DEMO-MX-FX",)
DECLINED = ("CLI-O2MFFRGEVULL", "CLI-9CNNDZJT76RQ", "CLI-CY5XKHJ944ZU")  # each has declined charges
REVERSED = ("CLI-ASWOLNWFVNJ0", "CLI-9DUUBKIL13N5", "CLI-THZPUJOWQXNR")  # each has reversed charges
CARD_AND_MORE = ("CLI-5EWYD3VRLM5C", "CLI-7QE9NSFAKW9W")  # spend split across card and accounts


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    language: str  # "es" or "pt"
    question: str
    kind: Kind = "answerable"
    gold_sql: str | None = None
    customers: tuple[str, ...] = TX
    ordered: bool = False  # True when the gold SQL has a meaningful ORDER BY
    split: Split = "regression"


CASES: tuple[Case, ...] = (
    # counting and filtering
    Case(
        "tx_count",
        "count",
        "es",
        "¿Cuántos movimientos tengo en total?",
        gold_sql="SELECT count(*) AS n FROM transactions",
    ),
    Case(
        "tx_by_status",
        "count",
        "es",
        "¿Cuántas transacciones tengo por estado?",
        gold_sql=(
            "SELECT transaction_status, count(*) AS n FROM transactions "
            "GROUP BY transaction_status ORDER BY transaction_status"
        ),
        ordered=True,
        split="heldout",
    ),
    Case(
        "tx_by_channel",
        "count",
        "es",
        "¿Cuántas operaciones hice por cada canal?",
        gold_sql="SELECT channel, count(*) AS n FROM transactions GROUP BY channel",
    ),
    Case(
        "declined",
        "count",
        "es",
        "¿Cuántas transacciones fueron rechazadas?",
        gold_sql="SELECT count(*) AS n FROM transactions WHERE transaction_status = 'Declined'",
        customers=DECLINED,
    ),
    Case(
        "reversed",
        "count",
        "es",
        "¿Cuántas transacciones se revirtieron?",
        gold_sql="SELECT count(*) AS n FROM transactions WHERE transaction_status = 'Reversed'",
        customers=REVERSED,
    ),
    Case(
        "distinct_merchants",
        "count",
        "es",
        "¿En cuántos comercios distintos compré?",
        gold_sql=(
            "SELECT count(DISTINCT merchant_name) AS n FROM transactions "
            "WHERE transaction_status = 'Approved'"
        ),
        split="heldout",
    ),
    # sums and averages
    Case(
        "spend_total",
        "aggregate",
        "es",
        "¿Cuánto he gastado en compras aprobadas?",
        gold_sql=(
            "SELECT currency, sum(amount) AS total FROM transactions "
            "WHERE transaction_status = 'Approved' AND transaction_type = 'Purchase' "
            "GROUP BY currency"
        ),
    ),
    Case(
        "avg_purchase",
        "aggregate",
        "es",
        "¿Cuál es el monto promedio de mis compras aprobadas?",
        gold_sql=(
            "SELECT round(avg(amount)::numeric, 2) AS promedio FROM transactions "
            "WHERE transaction_status = 'Approved'"
        ),
    ),
    Case(
        "pending_total",
        "aggregate",
        "es",
        "¿Cuánto dinero tengo pendiente de confirmar?",
        gold_sql=(
            "SELECT sum(amount) AS total FROM transactions WHERE transaction_status = 'Pending'"
        ),
        customers=("DEMO-CO-PENDING", "DEMO-MX-DUPLICATE"),
        split="heldout",
    ),
    Case(
        "spend_by_category",
        "group",
        "es",
        "¿Cuánto gasté por categoría?",
        gold_sql=(
            "SELECT transaction_category, sum(amount) AS total FROM transactions "
            "WHERE transaction_status = 'Approved' GROUP BY transaction_category"
        ),
    ),
    # ranking
    Case(
        "biggest_purchase",
        "rank",
        "es",
        "¿Cuál fue mi compra más grande?",
        gold_sql=(
            "SELECT merchant_name, amount, currency FROM transactions "
            "WHERE transaction_status = 'Approved' ORDER BY amount DESC LIMIT 1"
        ),
        ordered=True,
    ),
    Case(
        "top3_merchants",
        "rank",
        "es",
        "¿En qué 3 comercios gasté más?",
        gold_sql=(
            "SELECT merchant_name, sum(amount) AS total FROM transactions "
            "WHERE transaction_status = 'Approved' GROUP BY merchant_name ORDER BY total DESC "
            "LIMIT 3"
        ),
        ordered=True,
    ),
    Case(
        "last_transaction",
        "rank",
        "es",
        "¿Cuál fue mi último movimiento?",
        gold_sql=(
            "SELECT merchant_name, amount, currency FROM transactions "
            "ORDER BY transaction_date DESC LIMIT 1"
        ),
        ordered=True,
        split="heldout",
    ),
    # time (the data ends in June 2026: "last N days" counts back from its latest row)
    Case(
        "first_transaction",
        "time",
        "es",
        "¿Cuándo fue mi primera transacción?",
        gold_sql="SELECT min(transaction_date)::date AS fecha FROM transactions",
    ),
    Case(
        "spend_by_month",
        "time",
        "es",
        "¿Cuánto gasté cada mes?",
        gold_sql=(
            "SELECT date_trunc('month', transaction_date)::date AS mes, sum(amount) AS total "
            "FROM transactions WHERE transaction_status = 'Approved' GROUP BY 1 ORDER BY 1"
        ),
        ordered=True,
    ),
    Case(
        "spend_in_june",
        "time",
        "es",
        "¿Cuánto gasté en junio de 2026?",
        gold_sql=(
            "SELECT sum(amount) AS total FROM transactions WHERE transaction_status = 'Approved' "
            "AND transaction_date >= '2026-06-01' AND transaction_date < '2026-07-01'"
        ),
    ),
    Case(
        "last_30_days",
        "time",
        "es",
        "¿Cuántos movimientos tuve en los últimos 30 días?",
        gold_sql=(
            "SELECT count(*) AS n FROM transactions "
            "WHERE transaction_date >= (SELECT max(transaction_date) "
            "FROM transactions) - interval '30 days'"
        ),
        split="heldout",
    ),
    # other tables
    Case(
        "balance_by_currency",
        "tables",
        "es",
        "¿Cuál es mi saldo total por moneda?",
        gold_sql="SELECT currency, sum(current_balance) AS total FROM products GROUP BY currency",
        customers=SERVICE,
    ),
    Case(
        "count_products",
        "tables",
        "es",
        "¿Cuántos productos tengo con el banco?",
        gold_sql="SELECT count(*) AS n FROM products",
        customers=SERVICE,
    ),
    Case(
        "my_segment",
        "tables",
        "es",
        "¿En qué segmento estoy y de qué país soy?",
        gold_sql="SELECT segment, country FROM customers",
        customers=SERVICE,
    ),
    Case(
        "complaints_by_status",
        "tables",
        "es",
        "¿Cuántas quejas tengo por estado?",
        gold_sql="SELECT status, count(*) AS n FROM complaints GROUP BY status",
        customers=SERVICE,
        split="heldout",
    ),
    Case(
        "open_complaints",
        "tables",
        "es",
        "¿Tengo quejas abiertas?",
        gold_sql=(
            "SELECT count(*) AS n FROM complaints "
            "WHERE status IN ('Open', 'In Process', 'Escalated')"
        ),
        customers=SERVICE,
    ),
    Case(
        "last_contact",
        "tables",
        "es",
        "¿Por qué fue mi último contacto con el banco?",
        gold_sql="SELECT last_contact_reason FROM customer_service_summary",
        customers=SERVICE,
    ),
    Case(
        "last_survey",
        "tables",
        "es",
        "¿Qué calificación di en mi última encuesta?",
        gold_sql="SELECT last_csat FROM customer_service_summary",
        customers=SERVICE,
        split="heldout",
    ),
    # joins and reference data
    Case(
        "spend_on_card",
        "join",
        "es",
        "¿Cuánto he gastado con mi tarjeta de crédito?",
        gold_sql=(
            "SELECT sum(t.amount) AS total FROM transactions t "
            "JOIN products p ON p.product_id = t.product_id "
            "WHERE p.product_type = 'Tarjeta Crédito' AND t.transaction_status = 'Approved'"
        ),
        customers=CARD_AND_MORE,
        split="heldout",
    ),
    Case(
        "foreign_spend",
        "join",
        "es",
        "¿Cuánto he gastado en el extranjero?",
        gold_sql=(
            "SELECT count(*) AS n, sum(t.amount) AS total FROM transactions t, customers c "
            "WHERE t.transaction_country <> c.country"
        ),
        customers=ANY,
    ),
    Case(
        "usd_to_mxn",
        "join",
        "es",
        "¿A cuánto está el dólar en pesos mexicanos?",
        gold_sql=(
            "SELECT exchange_rate FROM fx_rates "
            "WHERE source_currency = 'USD' AND target_currency = 'MXN' ORDER BY date DESC LIMIT 1"
        ),
        customers=ANY,
        ordered=True,
    ),
    Case(
        "uber_charges",
        "filter",
        "es",
        "Muéstrame mis compras en Uber",
        gold_sql=(
            "SELECT transaction_date, amount, currency FROM transactions "
            "WHERE merchant_name ILIKE '%uber%' ORDER BY transaction_date DESC"
        ),
        customers=("DEMO-MX-DUPLICATE",),
        ordered=True,
    ),
    # Portuguese
    Case(
        "pt_top3",
        "language",
        "pt",
        "Quais foram as minhas 3 maiores compras aprovadas?",
        gold_sql=(
            "SELECT merchant_name, amount, currency FROM transactions "
            "WHERE transaction_status = 'Approved' ORDER BY amount DESC LIMIT 3"
        ),
        ordered=True,
    ),
    Case(
        "pt_total",
        "language",
        "pt",
        "Quanto eu gastei no total?",
        gold_sql=(
            "SELECT currency, sum(amount) AS total FROM transactions "
            "WHERE transaction_status = 'Approved' AND transaction_type = 'Purchase' "
            "GROUP BY currency"
        ),
    ),
    Case(
        "pt_declined",
        "language",
        "pt",
        "Quantas transações foram recusadas?",
        gold_sql="SELECT count(*) AS n FROM transactions WHERE transaction_status = 'Declined'",
        customers=DECLINED,
    ),
    Case(
        "pt_open_complaints",
        "language",
        "pt",
        "Quantas reclamações estão abertas?",
        gold_sql=(
            "SELECT count(*) AS n FROM complaints "
            "WHERE status IN ('Open', 'In Process', 'Escalated')"
        ),
        customers=SERVICE,
        split="heldout",
    ),
)
