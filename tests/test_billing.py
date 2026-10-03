"""The team-generated billing rule (data_pipeline/load.py), on hand-made products. No database."""

from datetime import timedelta

import duckdb
import pytest

from data_pipeline.load import AS_OF, BILLING

PRODUCTS = [  # id, type, currency, current_balance, interest_rate, days_past_due, status
    ("CARD-OK", "Tarjeta Crédito", "USD", 1000.0, 30.0, 0, "Active"),
    ("CARD-LATE", "Tarjeta Crédito", "USD", 1000.0, 30.0, 60, "Blocked"),
    ("CARD-SMALL", "Tarjeta Crédito", "COP", 40_000.0, 30.0, None, "Active"),
    ("CARD-CLOSED", "Tarjeta Crédito", "USD", 800.0, 30.0, 0, "Closed"),
    ("LOAN-OK", "Préstamo Personal", "ARS", 500_000.0, 24.0, 0, "Active"),
    ("LOAN-LATE", "Préstamo Hipotecario", "COP", 90_000_000.0, None, 180, "Suspended"),
    ("SAVINGS", "Cuenta Ahorro", "USD", 2500.0, 2.0, None, "Active"),
]


def billing() -> dict[str, dict]:
    con = duckdb.connect()
    con.execute(
        """CREATE TABLE core_products (product_id VARCHAR, customer_id VARCHAR,
               product_type VARCHAR, currency VARCHAR, current_balance DOUBLE,
               interest_rate DOUBLE, days_past_due INT, product_status VARCHAR)"""
    )
    con.executemany(
        "INSERT INTO core_products VALUES (?, 'C1', ?, ?, ?, ?, ?, ?)", [list(p) for p in PRODUCTS]
    )
    result = con.execute(BILLING)
    columns = [d[0] for d in result.description]
    return {row[0]: dict(zip(columns, row, strict=True)) for row in result.fetchall()}


def test_only_open_credit_cards_and_loans_get_a_schedule_and_it_never_changes():
    rows = billing()
    assert set(rows) == {"CARD-OK", "CARD-LATE", "CARD-SMALL", "LOAN-OK", "LOAN-LATE"}
    assert rows == billing()  # same products, same dates and amounts


def test_a_past_due_product_is_overdue_by_exactly_its_days_past_due():
    rows = billing()
    assert rows["CARD-LATE"]["due_date"] == AS_OF - timedelta(days=60)
    assert rows["LOAN-LATE"]["due_date"] == AS_OF - timedelta(days=180)
    for name in ("CARD-OK", "CARD-SMALL", "LOAN-OK"):
        assert AS_OF < rows[name]["due_date"] <= AS_OF + timedelta(days=20)
        assert rows[name]["past_due_amount"] == 0
    for row in rows.values():
        assert row["as_of"] == AS_OF
        assert row["statement_date"] == row["due_date"] - timedelta(days=20) <= AS_OF


def test_card_minimum_has_a_floor_and_never_exceeds_the_statement():
    rows = billing()
    ok, late, small = rows["CARD-OK"], rows["CARD-LATE"], rows["CARD-SMALL"]
    assert 700 <= ok["statement_balance"] <= 1000
    assert ok["minimum_payment"] == pytest.approx(0.05 * ok["statement_balance"], abs=0.01)
    assert small["minimum_payment"] == small["statement_balance"] <= 40_000  # under the COP floor
    assert late["statement_balance"] == 1000  # past due: the whole balance is on the statement
    assert late["past_due_amount"] == 100 and late["minimum_payment"] == 150  # 2 missed + 1
    assert all(r["remaining_installments"] is None for r in (ok, late, small))


def test_loan_installment_pays_the_balance_off_over_the_remaining_installments():
    rows = billing()
    loan, late = rows["LOAN-OK"], rows["LOAN-LATE"]
    assert loan["statement_balance"] is None and 6 <= loan["remaining_installments"] <= 60
    rate, n = 24.0 / 1200, loan["remaining_installments"]
    assert loan["minimum_payment"] == pytest.approx(
        500_000 * rate / (1 - (1 + rate) ** -n), abs=0.01
    )
    assert 60 <= late["remaining_installments"] <= 360  # no rate on record: balance / n
    assert late["minimum_payment"] == pytest.approx(
        90_000_000 / late["remaining_installments"], abs=0.01
    )
    assert late["past_due_amount"] == pytest.approx(6 * late["minimum_payment"], abs=0.05)
