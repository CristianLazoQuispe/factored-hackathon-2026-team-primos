"""Scoring of text-to-SQL evals: what counts as the model's SQL, and when two results match."""

from datetime import date
from decimal import Decimal

import pytest

from evals.text_to_sql.scoring import MAX_PERMUTED_COLUMNS, extract_sql, rows_match


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
        ([{"a": 1, "b": 2}], [{"a": 1}]),  # an extra column
    ],
)
def test_rows_that_differ_do_not_match(predicted, gold):
    assert not rows_match(predicted, gold, ordered=False)


def test_two_empty_results_match():
    assert rows_match([], [], ordered=False)


def test_a_very_wide_result_is_compared_in_the_order_written():
    width = MAX_PERMUTED_COLUMNS + 1
    gold = [{f"c{i}": i for i in range(width)}]
    reversed_columns = [{f"c{i}": i for i in reversed(range(width))}]
    assert rows_match(gold, gold, ordered=False)
    assert not rows_match(reversed_columns, gold, ordered=False)
