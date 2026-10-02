"""The data_lookup skill: use case with a fake database, MCP tools, dev endpoint, agent route."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound import http
from app.adapters.inbound.mcp import dwh
from app.application.run_sql import MAX_CELL_CHARS, MAX_ROWS, run_scoped_sql
from app.config import get_settings
from app.domain.sql_scope import OWNED, REFERENCE

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeDb:
    def __init__(self, rows=None, fail=None):
        self.rows, self.fail, self.ran = rows or [], fail, []

    async def fetch(self, sql, max_rows):
        self.ran.append((sql, max_rows))
        if self.fail:
            raise RuntimeError(self.fail)
        return self.rows[:max_rows]


async def test_blocked_sql_never_reaches_the_database():
    db = FakeDb()
    result = await run_scoped_sql(db, "C1", "DELETE FROM transactions")
    assert result["blocked"] is True and "error" in result
    assert db.ran == []


async def test_the_database_only_receives_the_scoped_sql():
    db = FakeDb(rows=[{"n": 3}])
    result = await run_scoped_sql(db, "C1", "SELECT count(*) AS n FROM transactions")
    assert "customer_id = 'C1'" in db.ran[0][0]
    assert result["rows"] == [{"n": 3}] and result["columns"] == ["n"]
    assert result["evidence_lookup"] == "run_sql" and result["truncated"] is False


async def test_results_are_capped_and_say_so():
    db = FakeDb(rows=[{"n": i} for i in range(500)])
    result = await run_scoped_sql(db, "C1", "SELECT n FROM transactions")
    assert len(result["rows"]) == MAX_ROWS and result["truncated"] is True


async def test_a_database_error_is_an_error_not_an_empty_answer():
    result = await run_scoped_sql(
        FakeDb(fail='column "x" does not exist\nLINE 1'), "C1", "SELECT x FROM transactions"
    )
    assert result["error"] == 'The query failed: column "x" does not exist'
    assert "rows" not in result


async def test_tools_take_no_customer_and_run_as_the_session_customer(monkeypatch):
    from fastmcp import Client

    db, audit = FakeDb(rows=[{"n": 1}]), []

    async def record(tool, proposed, decision, reason, executed):
        audit.append((tool, decision, executed))

    monkeypatch.setattr(dwh, "db", db)
    monkeypatch.setattr(dwh, "record_decision", record)
    async with Client(dwh.mcp) as client:
        for tool in await client.list_tools():
            assert "customer_id" not in tool.input_schema["properties"], tool.name
        ok = await client.call_tool(
            "run_sql", {"sql": "SELECT 1 AS n FROM transactions"}, meta={"customer_id": "C1"}
        )
        bad = await client.call_tool(
            "run_sql", {"sql": "SELECT * FROM ops.sessions"}, meta={"customer_id": "C1"}
        )
        nobody = await client.call_tool("run_sql", {"sql": "SELECT 1"}, raise_on_error=False)
        schema = await client.call_tool("describe_schema", {})
    assert ok.structured_content["rows"] == [{"n": 1}]
    assert bad.structured_content["blocked"] is True
    assert nobody.is_error
    assert "transactions" in schema.data
    assert audit == [("run_sql", "allowed", True), ("run_sql", "blocked", False)]
    assert len(db.ran) == 1  # the blocked query never ran


def test_dev_endpoint_runs_the_guard_locally_and_is_404_elsewhere(monkeypatch):
    class Db:
        async def fetch(self, sql, max_rows):
            return [{"ok": 1}]

    monkeypatch.setattr(http, "ReadOnlyPostgres", Db)
    body = {"customer_id": "C1", "sql": "SELECT 1 AS ok FROM transactions"}
    with TestClient(http.app) as client:
        monkeypatch.setattr(get_settings(), "app_env", "local")
        assert client.post("/api/dev/dwh/sql", json=body).json()["rows"] == [{"ok": 1}]
        blocked = client.post("/api/dev/dwh/sql", json=body | {"sql": "DROP TABLE x"}).json()
        assert blocked["blocked"] is True
        monkeypatch.setattr(get_settings(), "app_env", "cloud")
        assert client.post("/api/dev/dwh/sql", json=body).status_code == 404


SCHEMA_SQL = Path(__file__).parents[1] / "app/adapters/outbound/postgres/schema.sql"


def test_every_core_table_is_classified_and_owned_means_customer_id():
    tables = dict(
        re.findall(r"CREATE TABLE core\.(\w+) \((.*?)\n\);", SCHEMA_SQL.read_text(), re.S)
    )
    assert set(tables) == OWNED | REFERENCE  # a new table must be classified on purpose
    for name, body in tables.items():
        has_customer_id = re.search(r"^\s+customer_id\s", body, re.M) is not None
        assert has_customer_id == (name in OWNED), name


async def test_long_text_cells_are_cut_so_they_cannot_flood_the_context():
    result = await run_scoped_sql(
        FakeDb(rows=[{"t": "x" * 1000}]), "C1", "SELECT t FROM complaints"
    )
    assert len(result["rows"][0]["t"]) == MAX_CELL_CHARS + 1
