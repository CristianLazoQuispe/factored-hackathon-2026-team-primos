"""Postgres, the agent's operational store (tables in schema.sql)."""

from decimal import Decimal

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings


def ping() -> str:
    with psycopg.connect(get_settings().database_url, connect_timeout=2) as pg:
        pg.execute("SELECT 1")
    return "ok"


async def query(sql: str, params: dict) -> list[dict]:
    """Run one reviewed, parameterized statement. Decimals come back as floats."""
    async with await psycopg.AsyncConnection.connect(
        get_settings().database_url, row_factory=dict_row
    ) as conn:
        rows = await (await conn.execute(sql, params)).fetchall()
    return [{k: float(v) if isinstance(v, Decimal) else v for k, v in r.items()} for r in rows]
