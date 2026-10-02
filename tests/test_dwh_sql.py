"""The database walls against the real demo data. Skipped unless Postgres is up
(`make demo-data`, which also recreates the dwh_reader role)."""

import pytest

from app.adapters.outbound import postgres
from app.adapters.outbound.postgres.readonly import ReadOnlyPostgres
from app.application.run_sql import run_scoped_sql

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def need_demo_data():
    try:
        postgres.ping()
    except Exception:
        pytest.skip("Postgres with the demo data is not running")


async def test_a_customer_only_counts_their_own_transactions():
    db = ReadOnlyPostgres()
    mine = await run_scoped_sql(db, "DEMO-MX-DUPLICATE", "SELECT count(*) AS n FROM transactions")
    everyone = await postgres.query("SELECT count(*) AS n FROM core.transactions", {})
    assert 0 < mine["rows"][0]["n"] < everyone[0]["n"]
    other = await run_scoped_sql(
        db, "DEMO-MX-DUPLICATE", "SELECT DISTINCT customer_id FROM transactions"
    )
    assert other["rows"] == [{"customer_id": "DEMO-MX-DUPLICATE"}]


async def test_business_question_over_the_demo_customer():
    result = await run_scoped_sql(
        ReadOnlyPostgres(),
        "DEMO-MX-DUPLICATE",
        "SELECT merchant_name, count(*) AS n FROM transactions "
        "WHERE merchant_name ILIKE '%uber%' GROUP BY 1",
    )
    assert result["rows"] and result["rows"][0]["merchant_name"] == "Uber Trip"


async def test_the_database_itself_refuses_writes_and_ops_even_without_the_policy():
    db = ReadOnlyPostgres()
    for sql in (
        "DELETE FROM core.transactions",
        "UPDATE core.transactions SET amount = 0",
        "SELECT * FROM ops.decision_log",
        "SELECT pg_sleep(10)",
    ):
        with pytest.raises(Exception, match="read-only|permission denied|timeout"):
            await db.fetch(sql, 1)
