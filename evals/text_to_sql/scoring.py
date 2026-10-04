"""Scoring for text-to-SQL evals. Pure functions: no database, no model."""

import re
from datetime import date, datetime
from decimal import Decimal
from itertools import permutations

CANNOT_ANSWER = "CANNOT_ANSWER"
MAX_PERMUTED_COLUMNS = 6  # beyond this, columns are compared in the order the model wrote them
_FENCE = re.compile(r"```[a-zA-Z]*\s*(.*?)```", re.DOTALL)
_STATEMENT = re.compile(
    r"(?is)^\s*(select|with|insert|update|delete|drop|alter|create|truncate|grant)\b"
)


def extract_sql(reply: str) -> str | None:
    """The SQL in a model reply, or None when it declined or wrote no query.

    Any statement counts as an attempt, a DELETE included: refusing it is the guard's job, and
    the eval must see that the model tried. Only CANNOT_ANSWER or plain prose is a refusal."""
    text = (reply or "").strip()
    fenced = _FENCE.search(text)
    candidate = (fenced.group(1) if fenced else text).strip().rstrip(";").strip()
    if not candidate or candidate.upper().startswith(CANNOT_ANSWER):
        return None
    return candidate if fenced or _STATEMENT.match(candidate) else None


def _cell(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int | float | Decimal):
        return round(float(value), 2)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def _key(value) -> tuple:
    """A sort key that works with None and with values of different types in one column."""
    return (value is None, str(value))


def _column_orders(predicted: list[tuple], gold: list[tuple]) -> list[tuple]:
    """Ways to arrange the predicted columns to line up with the gold ones: the order the model
    wrote them first, then any other arrangement where each column holds the same values."""
    width = len(gold[0])
    written = tuple(range(width))
    if width > MAX_PERMUTED_COLUMNS:
        return [written]
    gold_columns = [sorted(map(_key, (row[j] for row in gold))) for j in range(width)]
    predicted_columns = [sorted(map(_key, (row[i] for row in predicted))) for i in range(width)]
    others = [
        order
        for order in permutations(range(width))
        if order != written
        and all(predicted_columns[order[j]] == gold_columns[j] for j in range(width))
    ]
    return [written, *others]


def rows_match(predicted: list[dict], gold: list[dict], ordered: bool) -> bool:
    """Execution accuracy: the two queries return the same values, whatever the SQL looks like.

    Column names and column order are ignored (the question does not say how to order them), but
    each row must keep its values together: swapping two columns is fine, mixing up which value
    belongs to which row is not. Numbers are compared to 2 decimals. Row order only counts when
    the gold query has a meaningful ORDER BY."""
    a = [tuple(_cell(v) for v in row.values()) for row in predicted]
    b = [tuple(_cell(v) for v in row.values()) for row in gold]
    if len(a) != len(b):
        return False
    if not b:
        return True
    if len(a[0]) != len(b[0]):
        return False
    wanted = b if ordered else sorted(b, key=lambda row: tuple(map(_key, row)))
    for order in _column_orders(a, b):
        arranged = [tuple(row[i] for i in order) for row in a]
        if not ordered:
            arranged = sorted(arranged, key=lambda row: tuple(map(_key, row)))
        if arranged == wanted:
            return True
    return False
