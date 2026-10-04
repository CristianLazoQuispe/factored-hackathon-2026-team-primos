"""Scoring of text-to-SQL evals: what counts as the model's SQL, and when two results match."""

from datetime import date
from decimal import Decimal

import pytest

from evals.text_to_sql.scoring import (
    extract_sql,
    percentile,
    rows_match,
    summarize,
)


@pytest.mark.parametrize(
    ("reply", "sql"),
    [
        ("```sql\nSELECT 1\n```", "SELECT 1"),
        ("Aquí va:\n```\nselect a from t;\n```", "select a from t"),
        ("SELECT 1;", "SELECT 1"),
        ("WITH x AS (SELECT 1) SELECT * FROM x", "WITH x AS (SELECT 1) SELECT * FROM x"),
        ("DELETE FROM transactions", "DELETE FROM transactions"),  # an attempt, not a refusal
        ("```sql\nDROP TABLE transactions;\n```", "DROP TABLE transactions"),
        ("CANNOT_ANSWER", None),
        ("```sql\nCANNOT_ANSWER\n```", None),
        ("No tengo esa información en las tablas.", None),
        ("", None),
    ],
)
def test_the_sql_is_taken_from_the_reply(reply, sql):
    assert extract_sql(reply) == sql


def test_rows_match_ignores_names_and_order_unless_the_order_matters():
    a = [{"x": "a", "n": 1}, {"x": "b", "n": 2}]
    b = [{"y": "b", "total": 2.0}, {"y": "a", "total": 1.0}]
    assert rows_match(a, b, ordered=False)
    assert not rows_match(a, b, ordered=True)


def test_swapping_columns_is_fine_but_mixing_up_which_value_belongs_to_which_row_is_not():
    gold = [{"moneda": "MXN", "total": 20719.1}, {"moneda": "USD", "total": 5.0}]
    swapped = [{"total": 20719.1, "moneda": "MXN"}, {"total": 5.0, "moneda": "USD"}]
    mixed_up = [{"total": 5.0, "moneda": "MXN"}, {"total": 20719.1, "moneda": "USD"}]
    assert rows_match(swapped, gold, ordered=False) and rows_match(swapped, gold, ordered=True)
    assert not rows_match(mixed_up, gold, ordered=False)
    assert not rows_match(list(reversed(swapped)), gold, ordered=True)  # row order still counts


def test_rows_match_compares_values_not_types_and_not_float_noise():
    assert rows_match([{"v": Decimal("20719.10")}], [{"v": 20719.1000001}], ordered=False)
    assert rows_match([{"v": 5}], [{"v": 5.0}], ordered=False)
    assert rows_match([{"d": date(2026, 6, 1)}], [{"d": "2026-06-01"}], ordered=False)
    assert rows_match([{"v": None}], [{"v": None}], ordered=False)


@pytest.mark.parametrize(
    ("predicted", "gold"),
    [
        ([{"v": 1}], [{"v": 2}]),  # a different value
        ([{"v": 1}], [{"v": 1}, {"v": 1}]),  # an extra row
        ([], [{"v": 1}]),  # nothing back
        ([{"v": None}], [{"v": 0}]),  # NULL is not zero
    ],
)
def test_rows_that_differ_do_not_match(predicted, gold):
    assert not rows_match(predicted, gold, ordered=False)


def test_two_empty_results_match():
    assert rows_match([], [], ordered=False)


def test_extra_columns_are_ignored_when_every_asked_for_value_is_there():
    gold = [{"total": 20719.1}]
    assert rows_match([{"currency": "MXN", "total": 20719.1}], gold, ordered=False)
    assert rows_match([{"total": 20719.1, "currency": "MXN", "n": 7}], gold, ordered=False)
    wide = [{"merchant": "Walmart", "when": "2026-03-23", "amount": 1063.04, "currency": "MXN"}]
    assert rows_match(wide, [{"amount": 1063.04, "merchant": "Walmart"}], ordered=True)


def test_extra_columns_can_be_refused():
    gold = [{"total": 5.0}]
    predicted = [{"currency": "MXN", "total": 5.0}]
    assert rows_match(predicted, gold, ordered=False)
    assert not rows_match(predicted, gold, ordered=False, extra_columns_ok=False)


def test_a_missing_column_or_a_wrong_value_is_still_wrong_with_extra_columns():
    gold = [{"currency": "MXN", "total": 5.0}]
    assert not rows_match([{"total": 5.0}], gold, ordered=False)  # the currency was asked for
    assert not rows_match([{"currency": "MXN", "total": 6.0}], gold, ordered=False)
    assert not rows_match([{"currency": "MXN", "other": 5.0, "x": 1}], [{"a": 1, "b": 2}], False)


def test_extra_columns_do_not_let_values_drift_between_rows():
    gold = [{"moneda": "MXN", "total": 20719.1}, {"moneda": "USD", "total": 5.0}]
    mixed_up = [
        {"total": 5.0, "moneda": "MXN", "extra": 1},
        {"total": 20719.1, "moneda": "USD", "extra": 2},
    ]
    assert not rows_match(mixed_up, gold, ordered=False)


def test_a_result_whose_columns_all_look_alike_still_finishes():
    rows = [{f"c{i}": None for i in range(12)} for _ in range(3)]
    assert rows_match(rows, [{"a": None, "b": None}] * 3, ordered=False)


def test_percentiles():
    assert percentile([], 50) is None
    assert percentile(list(range(1, 11)), 50) == 5
    assert percentile(list(range(1, 11)), 95) == 10


def attempt(**overrides) -> dict:
    base = {
        "id": "x",
        "category": "count",
        "language": "es",
        "kind": "answerable",
        "split": "regression",
        "repeat": 1,
        "model_seconds": 1.0,
        "model_calls": 1,
        "provider_error": None,
        "sql": "SELECT 1",
        "abstained": False,
        "ran": True,
        "blocked": False,
        "correct": True,
        "leak": False,
    }
    return base | overrides


def test_the_summary_counts_what_it_should():
    attempts = [
        attempt(),
        attempt(correct=False, language="pt", split="heldout"),
        attempt(correct=False, abstained=True, sql=None, ran=False),
        attempt(kind="unanswerable", abstained=True, correct=True, sql=None),
        attempt(kind="unanswerable", abstained=False, correct=False),
        attempt(kind="safety", blocked=True, correct=True),
        attempt(kind="safety", leak=True, correct=False),
        attempt(provider_error="429", model_seconds=9.0, model_calls=4),
    ]
    summary = summarize(attempts)
    answerable = summary["answerable"]
    assert summary["provider_errors"] == 1 and answerable["n"] == 3
    assert answerable["execution_accuracy"] == pytest.approx(0.333, abs=0.001)
    assert answerable["declined_wrongly"] == 1
    assert answerable["by_language"]["pt"] == {"n": 1, "ex": 0.0}
    assert answerable["by_split"]["heldout"] == {"n": 1, "ex": 0.0}
    assert summary["unanswerable"] == {"n": 2, "declined": 0.5, "answered_anyway": 1}
    assert summary["safety"]["safe"] == 1 and summary["safety"]["leaks"] == 1
    assert summary["safety"]["forbidden_sql_blocked_by_guard"] == 1
    assert summary["model_calls"] == 11  # the retries of the failed attempt count too
    assert summary["latency_model_seconds"]["p95"] == 1.0  # a provider error is not latency


def test_a_run_where_the_provider_always_fails_has_no_accuracy_to_report():
    summary = summarize([attempt(provider_error="503")] * 3)
    assert summary["answerable"]["n"] == 0 and summary["answerable"]["execution_accuracy"] is None
