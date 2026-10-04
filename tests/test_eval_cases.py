"""The eval cases are well formed, and each gold query really answers its question."""

import math
from collections import defaultdict

import pytest

from app.adapters.outbound import postgres
from app.adapters.outbound.postgres.readonly import ReadOnlyPostgres
from app.application.run_sql import run_scoped_sql
from app.domain.sql_scope import scope_query
from evals.text_to_sql.cases import CASES

ANSWERABLE = [case for case in CASES if case.kind == "answerable"]
by_id = pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def demo_data():
    try:
        postgres.ping()
    except Exception:
        pytest.skip("Postgres with the demo data is not running")


def test_ids_are_unique():
    ids = [case.id for case in CASES]
    assert len(ids) == len(set(ids))


@by_id
def test_every_case_is_complete(case):
    assert case.question and case.customers
    assert case.language in {"es", "pt"}
    assert case.kind in {"answerable", "unanswerable", "safety"}
    assert case.split in {"regression", "heldout"}
    assert (case.kind == "answerable") == bool(case.gold_sql)


@pytest.mark.parametrize("case", ANSWERABLE, ids=lambda case: case.id)
def test_the_gold_sql_passes_the_sql_guard(case):
    scope_query(case.gold_sql, case.customers[0])  # raises PolicyViolation if it would be refused


def test_every_category_with_three_cases_or_more_is_in_both_splits():
    splits = defaultdict(set)
    sizes = defaultdict(int)
    for case in CASES:
        splits[case.category].add(case.split)
        sizes[case.category] += 1
    assert {
        c for c, n in sizes.items() if n >= 3 and splits[c] != {"regression", "heldout"}
    } == set()


def test_about_a_third_of_the_cases_are_held_out():
    share = sum(case.split == "heldout" for case in CASES) / len(CASES)
    assert 0.2 <= share <= 0.4


def is_vacuous(rows: list[dict]) -> bool:
    """No rows, or only NULLs and zeros: a wrong query could match this by luck."""
    return all(value in (None, 0) for row in rows for value in row.values())


@pytest.mark.anyio
async def test_each_gold_query_returns_real_data_for_most_of_its_customers(demo_data):
    db = ReadOnlyPostgres()
    for case in ANSWERABLE:
        useful = 0
        for customer in case.customers:
            result = await run_scoped_sql(db, customer, case.gold_sql)
            assert "error" not in result, f"{case.id} for {customer}: {result.get('error')}"
            useful += not is_vacuous(result["rows"])
        assert useful >= math.ceil(len(case.customers) / 2), f"{case.id}: gold is mostly empty"


# Columns whose absence is what makes the "unanswerable" cases unanswerable. The raw sample has a
# credit_score, but nobody loads it today: the day someone does, `credit_score` stops being a
# question to refuse and the case must be rewritten, or it would punish a correct answer.
MISSING_COLUMNS = {"credit_score", "interest_paid", "interest_charged"}


@pytest.mark.anyio
async def test_the_data_behind_the_unanswerable_cases_is_still_missing(demo_data):
    rows = await postgres.query(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'core'",
        {},
    )
    present = sorted(
        f"{r['table_name']}.{r['column_name']}" for r in rows if r["column_name"] in MISSING_COLUMNS
    )
    assert not present, f"now answerable, rewrite the unanswerable cases: {present}"
