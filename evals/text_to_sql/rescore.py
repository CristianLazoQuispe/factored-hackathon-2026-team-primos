"""Score a saved report again with today's gold queries and comparator, without calling the model.

    uv run python -m evals.text_to_sql.rescore results/baseline_regression_1.json

The SQL the model wrote is in the report, so a fix to a gold query or to the comparator can be
measured on the same answers, for free and in seconds. Attempts the provider refused, and cases
that no longer exist, are kept as they were.
"""

import argparse
import asyncio
import json
from pathlib import Path

from app.adapters.outbound.postgres.readonly import ReadOnlyPostgres
from evals.text_to_sql.cases import CASES
from evals.text_to_sql.run import gold_rows, judge, show, verdict, write_report
from evals.text_to_sql.scoring import summarize


async def rescore(attempts: list[dict], db=None) -> list[dict]:
    db, by_id, gold, rescored = db or ReadOnlyPostgres(), {c.id: c for c in CASES}, {}, []
    for attempt in attempts:
        case = by_id.get(attempt["id"])
        if attempt["provider_error"] or case is None:
            rescored.append(attempt)
            continue
        if case.kind == "answerable" and case.id not in gold:
            gold[case.id] = await gold_rows(db, case)
        rescored.append(attempt | await judge(db, case, attempt["sql"], gold.get(case.id, {})))
    return rescored


def changes(before: list[dict], after: list[dict]) -> list[str]:
    return [
        f"{new['id']} (repeat {new['repeat']}): {verdict(old)} -> {verdict(new)}"
        for old, new in zip(before, after, strict=True)
        if verdict(old) != verdict(new)
    ]


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("report", help="a JSON written by evals.text_to_sql.run")
    parser.add_argument("--out", help="where to write the rescored report")
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text())
    attempts = await rescore(report["attempts"])
    for line in changes(report["attempts"], attempts) or ["no verdict changed"]:
        print(line)
    show(summarize(attempts))
    out = Path(args.out or args.report.replace(".json", ".rescored.json"))
    meta = report["meta"] | {"rescored_from": args.report}
    write_report(out, meta, attempts, complete=report["meta"].get("complete", True))
    print(f"\nWritten: {out}")


if __name__ == "__main__":
    asyncio.run(main())
