"""Integrity of the committed mini-set in data/sample/ (the data every teammate runs on)."""

from pathlib import Path

import duckdb
import pytest

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample"
WINDOW = ("2026-04-01", "2026-06-18")
FACTS = {
    "transactions": "transaction_date",
    "digital_events": "event_date",
    "call_center_interactions": "interaction_date",
    "complaints": "creation_date",
    "satisfaction_surveys": "survey_date",
}
CUSTOMER_TABLES = ["products", *FACTS]

pytestmark = pytest.mark.skipif(
    not (SAMPLE / "customers.parquet").exists(), reason="mini-set not generated"
)


@pytest.fixture(scope="module")
def con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    for path in SAMPLE.glob("*.parquet"):
        con.execute(f"CREATE VIEW {path.stem} AS SELECT * FROM '{path}'")
    return con


def scalar(con: duckdb.DuckDBPyConnection, sql: str) -> int:
    return con.execute(sql).fetchone()[0]


@pytest.mark.parametrize("table", CUSTOMER_TABLES)
def test_every_row_belongs_to_a_sampled_customer(con, table) -> None:
    assert (
        scalar(
            con,
            f"""SELECT count(*) FROM {table}
                           WHERE customer_id NOT IN (SELECT customer_id FROM customers)""",
        )
        == 0
    )


@pytest.mark.parametrize(("table", "column"), FACTS.items())
def test_facts_fall_inside_the_window(con, table, column) -> None:
    start, end = WINDOW
    assert (
        scalar(
            con,
            f"""SELECT count(*) FROM {table} WHERE {column} < TIMESTAMP '{start}'
                           OR {column} >= TIMESTAMP '{end}' + INTERVAL 1 DAY""",
        )
        == 0
    )


def test_customers_cross_tables(con) -> None:
    in_three_or_more = scalar(
        con,
        """
        SELECT count(*) FROM (
            SELECT customer_id FROM (
                SELECT DISTINCT customer_id, 'tx' AS t FROM transactions UNION ALL
                SELECT DISTINCT customer_id, 'ev' FROM digital_events UNION ALL
                SELECT DISTINCT customer_id, 'it' FROM call_center_interactions)
            GROUP BY 1 HAVING count(*) = 3)""",
    )
    assert in_three_or_more >= 100


@pytest.mark.parametrize(
    "condition",
    [
        "transaction_status = 'Pending'",
        "transaction_status = 'Reversed'",
        "transaction_status = 'Declined'",
        "is_fraud",
    ],
)
def test_dispute_scenarios_are_covered(con, condition) -> None:
    assert scalar(con, f"SELECT count(*) FROM transactions WHERE {condition}") >= 30


def test_unrecognized_charge_complaints_are_covered(con) -> None:
    assert (
        scalar(con, "SELECT count(*) FROM complaints WHERE subcategory = 'Cargo no reconocido'")
        >= 30
    )


def test_fixtures_cover_every_demo_scenario() -> None:
    con = duckdb.connect()
    customers = con.execute(
        f"SELECT customer_id FROM '{SAMPLE / 'fixtures' / 'customers.parquet'}'"
    ).fetchall()
    assert len(customers) == 10  # the eight scenarios and the two khipear customers
    accounts = scalar(
        con,
        f"""
        SELECT count(*) FROM '{SAMPLE / "fixtures" / "products.parquet"}'
        WHERE customer_id = 'DEMO-MX-KHIPU' AND account_number IS NOT NULL""",
    )
    assert accounts == 2  # more than one, so the agent has to ask "from which account?"
    duplicates = scalar(
        con,
        f"""
        SELECT count(*) FROM '{SAMPLE / "fixtures" / "transactions.parquet"}' a
        JOIN '{SAMPLE / "fixtures" / "transactions.parquet"}' b
          ON a.customer_id = b.customer_id AND a.merchant_name = b.merchant_name
         AND a.amount = b.amount AND a.transaction_id < b.transaction_id
         AND abs(epoch(b.transaction_date) - epoch(a.transaction_date)) <= 10""",
    )
    assert duplicates == 2  # MX + PT duplicate-charge scenarios


def test_sample_stays_small() -> None:
    size = sum(p.stat().st_size for p in SAMPLE.rglob("*.parquet"))
    assert size < 30e6
