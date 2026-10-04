"""The catalog tells the model how to write the query: what it recommends must pass the SQL guard,
and what it says does not exist must really be rejected."""

import pytest

from app.adapters.inbound.mcp.dwh import CATALOG
from app.domain.sql_scope import PolicyViolation, scope_query

RECOMMENDED = [
    "SELECT date_trunc('month', transaction_date) AS month FROM transactions",
    "SELECT extract(year FROM transaction_date) AS year FROM transactions",
    "SELECT to_char(transaction_date, 'YYYY-MM') AS month FROM transactions",
    "SELECT transaction_date::date AS day FROM transactions",
    "SELECT amount FROM transactions WHERE transaction_date >= date '2026-06-01'",
    "SELECT amount FROM transactions WHERE merchant_name ILIKE '%uber%'",
    "SELECT exchange_rate FROM fx_rates WHERE source_currency = 'USD' "
    "AND target_currency = 'MXN' ORDER BY date DESC LIMIT 1",
]
SAID_NOT_TO_EXIST = ["strftime", "date_format", "julianday"]


@pytest.mark.parametrize("sql", RECOMMENDED)
def test_what_the_catalog_recommends_passes_the_guard(sql):
    scope_query(sql, "CLI-X")  # raises PolicyViolation if the guard would refuse it


@pytest.mark.parametrize("function", SAID_NOT_TO_EXIST)
def test_what_the_catalog_says_does_not_exist_is_rejected(function):
    with pytest.raises(PolicyViolation, match="not allowed"):
        scope_query(f"SELECT {function}(transaction_date, 'x') FROM transactions", "CLI-X")
    assert function in CATALOG


def test_the_catalog_states_its_query_writing_rules():
    for rule in ("date_trunc('month', col)", "ILIKE '%text%'", "ORDER BY date DESC LIMIT 1"):
        assert rule in CATALOG
    assert "public reference: use it for any exchange-rate question" in CATALOG
