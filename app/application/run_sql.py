"""Run SQL written by the agent: policy first, then a read-only database, then a bounded result.

The database is reached only through `ReadOnlyDb`. Errors come back as data (`error`) so the
agent can fix its query; an error is an unknown, never an empty answer.
"""

from typing import Any, Protocol

from app.domain.sql_scope import PolicyViolation, scope_query

MAX_ROWS = 100
MAX_CELL_CHARS = 300
EVIDENCE_LOOKUP = "run_sql"


class ReadOnlyDb(Protocol):
    async def fetch(self, sql: str, max_rows: int) -> list[dict]: ...


def _short(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_CELL_CHARS:
        return value[:MAX_CELL_CHARS] + "…"
    return value


async def run_scoped_sql(db: ReadOnlyDb, customer_id: str, sql: str) -> dict[str, Any]:
    try:
        safe_sql = scope_query(sql, customer_id)
    except PolicyViolation as violation:
        return {"error": str(violation), "blocked": True}
    try:
        rows = await db.fetch(safe_sql, MAX_ROWS + 1)
    except Exception as error:  # the database's message is what lets the agent correct itself
        return {"error": f"The query failed: {str(error).splitlines()[0]}", "blocked": False}
    return {
        "sql": safe_sql,
        "columns": list(rows[0]) if rows else [],
        "rows": [{k: _short(v) for k, v in row.items()} for row in rows[:MAX_ROWS]],
        "truncated": len(rows) > MAX_ROWS,
        "evidence_lookup": EVIDENCE_LOOKUP,
    }
