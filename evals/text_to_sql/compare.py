"""Compare two runs of the same cases, case by case: what a change to the agent did.

    uv run python -m evals.text_to_sql.compare results/before.json results/after.json

The total can hide a change (one case fixed, another broken), so the cases that moved are listed.
Only regression runs are compared: naming the held-out cases that changed would be tuning on them.
Exit code 0: no case got worse. 1: some did. 2: the two runs cannot be compared.
"""

import argparse
import json
from pathlib import Path

BETTER, WORSE, SAME = 0, 1, 2


def tally(report: dict) -> dict[str, tuple[int, int]]:
    """For each case: attempts answered correctly and attempts served. A refused call is neither."""
    counts: dict[str, tuple[int, int]] = {}
    for attempt in report["attempts"]:
        if attempt["provider_error"]:
            continue
        right, served = counts.get(attempt["id"], (0, 0))
        counts[attempt["id"]] = (right + bool(attempt["correct"]), served + 1)
    return counts


def moved(before: dict, after: dict) -> list[tuple[str, tuple[int, int], tuple[int, int], int]]:
    """The cases whose share of correct attempts changed, with the direction."""
    rows = []
    for case_id in sorted(before.keys() & after.keys()):
        (b_right, b_served), (a_right, a_served) = before[case_id], after[case_id]
        if not b_served or not a_served:
            continue
        b_rate, a_rate = b_right / b_served, a_right / a_served
        if a_rate != b_rate:
            rows.append(
                (case_id, before[case_id], after[case_id], BETTER if a_rate > b_rate else WORSE)
            )
    return rows


def label(report: dict) -> str:
    meta = report["meta"]
    return (
        f"prompt {meta.get('prompt_sha')}, {meta.get('model')}, {meta.get('location')}, "
        f"{meta.get('repeats')} repeats"
    )


def not_comparable(before: dict, after: dict) -> list[str]:
    reasons = []
    for report, name in ((before, "before"), (after, "after")):
        if report["meta"]["split"] != "regression":
            reasons.append(
                f"the {name} run is not a regression run: held-out cases are not compared"
            )
    for key in ("model", "location"):
        if before["meta"].get(key) != after["meta"].get(key):
            reasons.append(
                f"the runs differ in {key}: {before['meta'].get(key)} / {after['meta'].get(key)}"
            )
    return reasons


def render(before: dict, after: dict) -> tuple[list[str], int]:
    b, a = before["summary"], after["summary"]
    lines = [f"before: {label(before)}", f"after : {label(after)}", ""]
    lines.append(
        f"execution accuracy   {b['answerable']['execution_accuracy']} -> "
        f"{a['answerable']['execution_accuracy']}   per repeat {b['answerable']['per_repeat']} -> "
        f"{a['answerable']['per_repeat']}"
    )
    lines.append(
        f"unanswerable declined {b['unanswerable']['declined']} -> "
        f"{a['unanswerable']['declined']}   leaks {b['safety']['leaks']} -> {a['safety']['leaks']}"
    )
    rows = moved(tally(before), tally(after))
    lines.append("")
    if not rows:
        lines.append("no case changed")
    for case_id, (b_right, b_served), (a_right, a_served), direction in rows:
        arrow = "better" if direction == BETTER else "WORSE"
        lines.append(
            f"  {case_id:<22} {b_right} of {b_served} -> {a_right} of {a_served}   {arrow}"
        )
    worse = sum(1 for row in rows if row[3] == WORSE)
    lines += ["", f"{len(rows) - worse} better, {worse} worse"]
    return lines, worse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("before")
    parser.add_argument("after")
    args = parser.parse_args(argv)
    before, after = (json.loads(Path(p).read_text()) for p in (args.before, args.after))
    reasons = not_comparable(before, after)
    split_problem = [r for r in reasons if "held-out" in r]
    if split_problem:
        print("\n".join(split_problem))
        return 2
    lines, worse = render(before, after)
    print("\n".join(lines))
    for reason in reasons:
        print(f"warning: {reason}: the comparison is not like for like")
    return 1 if worse else 0


if __name__ == "__main__":
    raise SystemExit(main())
