"""Comparing two runs case by case. No database and no model."""

import json

from evals.text_to_sql import compare
from evals.text_to_sql.scoring import summarize


def attempt(case_id: str, repeat: int, correct: bool | None, error: str | None = None) -> dict:
    return {
        "id": case_id,
        "category": "c",
        "language": "es",
        "kind": "answerable",
        "split": "regression",
        "repeat": repeat,
        "model_seconds": 1.0,
        "model_calls": 1,
        "provider_error": error,
        "sql": "SELECT 1",
        "abstained": False,
        "ran": True,
        "blocked": False,
        "correct": correct,
        "leak": False,
        "reason": None,
    }


def report(results: dict[str, list], **meta) -> dict:
    """`results` maps a case to its attempts: True, False, or None for a refused call."""
    attempts = [
        attempt(
            case_id, n, None if outcome is None else outcome, "429" if outcome is None else None
        )
        for case_id, outcomes in results.items()
        for n, outcome in enumerate(outcomes, 1)
    ]
    meta = {
        "split": "regression",
        "model": "m",
        "location": "global",
        "repeats": 3,
        "prompt_sha": "p",
    } | meta
    return {"meta": meta, "summary": summarize(attempts), "attempts": attempts}


def test_the_cases_that_moved_are_listed_with_their_direction():
    before = report({"a": [False] * 3, "b": [True] * 3, "c": [True] * 3})
    after = report({"a": [True] * 3, "b": [True, False, True], "c": [True] * 3})
    lines, worse = compare.render(before, after)
    text = "\n".join(lines)
    assert "a" in text and "0 of 3 -> 3 of 3   better" in text
    assert "b" in text and "3 of 3 -> 2 of 3   WORSE" in text
    assert "1 better, 1 worse" in text and worse == 1


def test_a_better_total_does_not_hide_a_case_that_got_worse():
    before = report({"a": [False] * 3, "b": [True] * 3, "c": [True] * 3, "d": [True] * 3})
    after = report({"a": [True] * 3, "b": [True] * 3, "c": [True] * 3, "d": [False] * 3})
    assert (
        after["summary"]["answerable"]["execution_accuracy"]
        == before["summary"]["answerable"]["execution_accuracy"]
    )  # the totals are the same, and the change is invisible in them
    assert compare.render(before, after)[1] == 1


def test_a_refused_call_is_neither_right_nor_wrong():
    counts = compare.tally(report({"a": [True, None, True]}))
    assert counts == {"a": (2, 2)}


def test_a_case_whose_rate_did_not_change_is_not_listed():
    run = report({"a": [True, False, True]})
    lines, worse = compare.render(run, run)
    assert "no case changed" in "\n".join(lines) and worse == 0


def test_rates_are_compared_not_counts_when_a_call_was_refused():
    before = report({"a": [True, True, True]})
    after = report({"a": [True, True, None]})  # 2 of 2 served: the same rate, not worse
    assert compare.render(before, after)[1] == 0


def write(path, data) -> str:
    path.write_text(json.dumps(data))
    return str(path)


def test_the_command_exits_with_whether_anything_got_worse(tmp_path, capsys):
    before = write(tmp_path / "before.json", report({"a": [False] * 3}))
    better = write(tmp_path / "better.json", report({"a": [True] * 3}))
    same_then_worse = write(tmp_path / "worse.json", report({"a": [False] * 3, "b": [False] * 3}))
    assert compare.main([before, better]) == 0
    assert compare.main([better, before]) == 1
    assert "WORSE" in capsys.readouterr().out
    assert compare.main([before, same_then_worse]) == 0  # a case in only one report is not compared


def test_held_out_runs_are_not_compared_so_nobody_tunes_on_them(tmp_path, capsys):
    held_out = write(tmp_path / "held.json", report({"secret_case": [False] * 3}, split="heldout"))
    regression = write(tmp_path / "reg.json", report({"secret_case": [True] * 3}))
    assert compare.main([regression, held_out]) == 2
    out = capsys.readouterr().out
    assert "held-out" in out and "secret_case" not in out


def test_runs_from_another_model_or_place_are_flagged_as_not_like_for_like(tmp_path, capsys):
    one = write(tmp_path / "one.json", report({"a": [True] * 3}))
    other = write(tmp_path / "other.json", report({"a": [True] * 3}, location="us-central1"))
    assert compare.main([one, other]) == 0
    assert "not like for like" in capsys.readouterr().out
