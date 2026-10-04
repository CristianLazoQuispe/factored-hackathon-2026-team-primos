"""Variants of the table catalog to test a change to it one rule at a time.

    uv run python -m evals.text_to_sql.variants <catalog.md> /tmp/catalogs

Give it the catalog WITHOUT the query-writing rules. It writes the same catalog (`old.md`, the
control), each rule alone (`A_dates.md`, `B_names.md`, `C_fx.md`) and all of them (`ABC.md`), and
prints the prompt fingerprint of each. Run the evals with `run --catalog <file>`: the fingerprint in
the report must match the one printed here, so a variant is never mistaken for another.
"""

import argparse
from pathlib import Path

from evals.text_to_sql.run import prompt_version

TRANSACTIONS = "## transactions  (one row per card/account movement)\n"
DATES = (
    "- Dates: `date_trunc('month', col)`, `extract(year FROM col)`, `to_char(col, 'YYYY-MM')`,"
    " `col::date`,\n  `col >= date '2026-06-01'`. Functions from SQLite or MySQL (`strftime`,"
    " `date_format`, `julianday`)\n  do not exist here and are rejected.\n"
)
NAMES = (
    "- Names of merchants, cities and products are written as the bank recorded them and vary in"
    " spelling\n  (`Uber` and `Uber Trip` are both Uber): match them with `ILIKE '%text%'`, never"
    " with `=`.\n"
)
FX_OLD = (
    "## fx_rates  (public reference, not customer data)\n"
    "date, source_currency, target_currency (MXN|COP|ARS|USD), exchange_rate (1 source = rate"
    " target),\nbuy_rate, sell_rate.\n"
)
FX_NEW = (
    "## fx_rates  (public reference: use it for any exchange-rate question)\n"
    "date, source_currency, target_currency (MXN|COP|ARS|USD), exchange_rate (1 source = rate"
    " target),\nbuy_rate, sell_rate.\n"
    '- "The dollar in Mexican pesos" is source USD, target MXN. For the current rate take the row'
    " with the\n  greatest `date`: `ORDER BY date DESC LIMIT 1`.\n"
)


def build(old: str, dates: bool, names: bool, fx: bool) -> str:
    """The catalog with the chosen rules added. Refuses one that is not the old catalog."""
    for anchor in (TRANSACTIONS, FX_OLD):
        if old.count(anchor) != 1:
            raise ValueError(
                f"the catalog must have this exactly once (and no rules yet):\n{anchor[:70]}"
            )
    text = old
    bullets = (DATES if dates else "") + (NAMES if names else "")
    if bullets:
        text = text.replace(
            TRANSACTIONS, f"## Writing the query (PostgreSQL)\n\n{bullets}\n{TRANSACTIONS}"
        )
    return text.replace(FX_OLD, FX_NEW) if fx else text


def variants(old: str) -> dict[str, str]:
    return {
        "old": old,
        "A_dates": build(old, dates=True, names=False, fx=False),
        "B_names": build(old, dates=False, names=True, fx=False),
        "C_fx": build(old, dates=False, names=False, fx=True),
        "ABC": build(old, dates=True, names=True, fx=True),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("catalog", help="the catalog without the query-writing rules")
    parser.add_argument("out", help="a folder to write the variants to")
    args = parser.parse_args(argv)
    try:
        made = variants(Path(args.catalog).read_text())
    except ValueError as problem:
        print(problem)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, text in made.items():
        (out / f"{name}.md").write_text(text)
        print(f"{out / f'{name}.md'}   prompt {prompt_version(text)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
