"""Execution of already-scoped SQL as `dwh_reader`: SELECT on `core` only, read-only transaction,
short timeout. This is the second wall; the first is `app.domain.sql_scope`, which decides whose
rows the query can see. Needs the role from schema.sql (`make demo-data` recreates it)."""

from decimal import Decimal

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings

STATEMENT_TIMEOUT_MS = 3000


class ReadOnlyPostgres:
    async def fetch(self, sql: str, max_rows: int) -> list[dict]:
        async with (
            await psycopg.AsyncConnection.connect(
                get_settings().database_url, row_factory=dict_row
            ) as conn,
            conn.transaction(),
        ):
            await conn.execute("SET TRANSACTION READ ONLY")
            await conn.execute("SET LOCAL ROLE dwh_reader")
            await conn.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
            cursor = await conn.execute(sql)  # no params: a '%' in the SQL is just a '%'
            rows = await cursor.fetchmany(max_rows)
        return [{k: float(v) if isinstance(v, Decimal) else v for k, v in r.items()} for r in rows]
