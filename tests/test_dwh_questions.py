"""The reference question set, through the guarded path, against the real demo data.
Skipped unless Postgres is up (`make demo-data`)."""

import pytest

from app.adapters.outbound import postgres
from app.adapters.outbound.postgres.readonly import ReadOnlyPostgres
from app.application.run_sql import run_scoped_sql
from tests.dwh_questions import QUESTIONS

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


@pytest.mark.parametrize("q", QUESTIONS, ids=lambda q: q["id"])
async def test_reference_sql_gives_the_expected_answer(q):
    result = await run_scoped_sql(ReadOnlyPostgres(), q["customer"], q["sql"])
    if q.get("blocked"):
        assert result["blocked"] is True
        return
    assert "error" not in result, result
    if "rows" in q:
        assert result["rows"] == pytest.approx(q["rows"])
    if "min_rows" in q:
        assert len(result["rows"]) >= q["min_rows"]
    for column, value in q.get("first", {}).items():
        assert result["rows"][0][column] == pytest.approx(value)
