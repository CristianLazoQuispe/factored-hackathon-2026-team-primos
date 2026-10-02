"""SQL written by the LLM: what is refused, and proof (in DuckDB) that nothing escapes the
session customer's rows."""

import duckdb
import pytest

from app.domain.sql_scope import PolicyViolation, scope_query


@pytest.fixture
def bank():
    con = duckdb.connect()
    con.execute("CREATE SCHEMA core")
    con.execute(
        "CREATE TABLE core.transactions (customer_id text, transaction_id text, amount int)"
    )
    con.execute("CREATE TABLE core.products (customer_id text, product_id text)")
    con.execute("CREATE TABLE core.fx_rates (source_currency text, exchange_rate double)")
    rows = "('A','a1',10),('A','a2',20),('B','b1',999),('B','b2',1)"
    con.execute(f"INSERT INTO core.transactions VALUES {rows}")
    con.execute("INSERT INTO core.products VALUES ('A','pa'),('B','pb')")
    con.execute("INSERT INTO core.fx_rates VALUES ('MXN', 0.05)")
    return con


def rows_for_a(bank, sql: str) -> list[tuple]:
    return bank.execute(scope_query(sql, "A")).fetchall()


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM transactions",
        "SELECT * FROM core.transactions",
        "SELECT * FROM transactions WHERE customer_id <> 'A'",
        "SELECT * FROM transactions WHERE customer_id = 'B'",
        "SELECT * FROM transactions WHERE 1=1 OR customer_id = 'B'",
        "SELECT * FROM transactions t JOIN products p ON p.customer_id <> t.customer_id",
        "SELECT * FROM (SELECT * FROM transactions) x",
        "WITH x AS (SELECT * FROM transactions) SELECT * FROM x",
        "SELECT * FROM transactions UNION ALL SELECT * FROM transactions",
        "SELECT * FROM transactions WHERE amount IN (SELECT amount FROM transactions)",
        "SELECT * FROM transactions WHERE EXISTS (SELECT 1 FROM transactions b WHERE b.amount>99)",
        "SELECT * FROM transactions -- ' OR customer_id = 'B'",
    ],
)
def test_no_query_can_see_another_customers_rows(bank, sql):
    assert {row[0] for row in rows_for_a(bank, sql)} <= {"A"}


def test_a_plain_select_still_returns_the_customers_own_rows(bank):
    assert len(rows_for_a(bank, "SELECT * FROM transactions")) == 2


def test_aggregates_only_cover_the_session_customer(bank):
    assert rows_for_a(bank, "SELECT sum(amount) FROM transactions") == [(30,)]


def test_reference_tables_are_readable_and_joinable(bank):
    assert rows_for_a(bank, "SELECT count(*) FROM transactions t, fx_rates f") == [(2,)]


def test_alias_and_qualified_columns_still_work(bank):
    sql = "SELECT t.transaction_id FROM core.transactions AS t ORDER BY t.amount DESC"
    assert rows_for_a(bank, sql) == [("a2",), ("a1",)]


def test_customer_id_is_escaped_not_interpolated():
    sql = scope_query("SELECT * FROM transactions", "A' OR '1'='1")
    assert "customer_id = 'A'' OR ''1''=''1'" in sql


def test_comments_never_reach_the_database():
    sql = scope_query("SELECT 1 /* x */ FROM transactions -- ; DROP TABLE x", "A")
    assert "DROP" not in sql and "--" not in sql and "/*" not in sql


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "   ",
        "DELETE FROM transactions",
        "UPDATE transactions SET amount = 0",
        "INSERT INTO transactions VALUES ('x')",
        "DROP TABLE transactions",
        "CREATE TABLE x AS SELECT * FROM transactions",
        "SELECT * INTO backup FROM transactions",
        "SHOW ALL",
        "SET ROLE postgres",
        "COPY transactions TO '/tmp/x'",
        "SELECT 1; SELECT 2",
        "SELECT 1; DROP TABLE transactions",
        "SELECT * FROM ops.decision_log",
        "SELECT * FROM ops.sessions",
        "SELECT * FROM pg_catalog.pg_tables",
        "SELECT * FROM pg_tables",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM public.transactions",
        "SELECT * FROM otherdb.core.transactions",
        "SELECT * FROM users",
        "SELECT pg_sleep(10)",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT query_to_xml('select * from core.transactions', true, true, '')",
        "SELECT * FROM dblink('x', 'select 1') AS t(a int)",
        "SELECT set_config('app.customer_id', 'B', true)",
        "SELECT nextval('s')",
        "WITH transactions AS (SELECT 1) SELECT * FROM transactions",
        "WITH products AS (SELECT * FROM core.products) SELECT * FROM core.products",
        "SELECT * FROM transactions TABLESAMPLE SYSTEM (50)",
        "SELECT * FROM " + "transactions " * 1000,
    ],
)
def test_refused(sql):
    with pytest.raises(PolicyViolation):
        scope_query(sql, "A")


def test_needs_a_session_customer():
    with pytest.raises(PolicyViolation):
        scope_query("SELECT 1", "")


def test_refusals_are_readable_by_the_model():
    with pytest.raises(PolicyViolation, match="Available: "):
        scope_query("SELECT * FROM users", "A")
