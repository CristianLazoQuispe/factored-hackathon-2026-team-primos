"""The eval runner itself, with fake models: no real model is called.

A model that knows every answer must score 100 %, and a model that guesses, attacks or fails must
not. That is what shows the runner measures something.
"""

import json
import sys

import pytest
from langchain_core.messages import AIMessage
from langchain_core.rate_limiters import InMemoryRateLimiter

from app.adapters.outbound import postgres
from app.application.run_sql import run_scoped_sql
from evals.text_to_sql import run as harness
from evals.text_to_sql.cases import CASES, Case
from evals.text_to_sql.scoring import summarize

pytestmark = pytest.mark.anyio
BY_QUESTION = {case.question: case for case in CASES}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def demo_data():
    try:
        postgres.ping()
    except Exception:
        pytest.skip("Postgres with the demo data is not running")


class Fake:
    """A model that answers every question with `answer(question)`."""

    def __init__(self, answer):
        self.answer = answer

    async def ainvoke(self, messages):
        return AIMessage(self.answer(messages[-1].content))


def oracle(question: str) -> str:
    case = BY_QUESTION[question]
    return f"```sql\n{case.golds[0]}\n```" if case.kind == "answerable" else "CANNOT_ANSWER"


def test_every_question_is_different_so_the_fake_oracle_can_tell_them_apart():
    assert len(BY_QUESTION) == len(CASES)


# ---- which cases run ----


def test_only_the_regression_cases_run_by_default():
    chosen = harness.select(CASES, "regression", None)
    assert chosen and all(case.split == "regression" for case in chosen)


def test_the_held_out_cases_run_only_when_asked_for():
    chosen = harness.select(CASES, "heldout", None)
    assert chosen and all(case.split == "heldout" for case in chosen)
    assert len(harness.select(CASES, "all", None)) == len(CASES)


def test_asking_for_a_held_out_case_by_id_needs_its_split():
    with pytest.raises(SystemExit):
        harness.select(CASES, "regression", "forecast")
    assert [c.id for c in harness.select(CASES, "heldout", "forecast")] == ["forecast"]


def test_the_limiter_is_off_at_zero_and_paces_calls_otherwise():
    assert harness.make_limiter(0) is None
    limiter = harness.make_limiter(30)
    assert isinstance(limiter, InMemoryRateLimiter) and limiter.requests_per_second == 0.5


# ---- whole runs against the real demo data (skipped without Postgres) ----


async def test_a_model_that_knows_the_answers_scores_perfectly(demo_data):
    attempts = await harness.run_eval(Fake(oracle), CASES, repeats=2)
    summary = summarize(attempts)
    assert len(attempts) == 2 * len(CASES) and summary["provider_errors"] == 0
    assert summary["answerable"]["execution_accuracy"] == 1.0
    assert summary["answerable"]["per_repeat"] == [1.0, 1.0]
    assert summary["unanswerable"]["declined"] == 1.0
    assert summary["safety"]["safe"] == summary["safety"]["n"] and summary["safety"]["leaks"] == 0
    assert summary["model_calls"] == 2 * len(CASES)  # one call per question: nothing was retried


async def test_a_model_that_guesses_scores_badly_and_never_declines(demo_data):
    summary = summarize(await harness.run_eval(Fake(lambda q: "```sql\nSELECT 1 AS n\n```"), CASES))
    assert summary["answerable"]["execution_accuracy"] < 0.2
    assert summary["unanswerable"]["answered_anyway"] == summary["unanswerable"]["n"]
    assert summary["safety"]["leaks"] == 0  # a wrong answer is still never someone else's data


async def test_a_model_that_attacks_is_stopped_by_the_guard_and_seen_by_the_run(demo_data):
    db = harness.ReadOnlyPostgres()
    count = "SELECT count(*) AS n FROM transactions"
    before = (await run_scoped_sql(db, "DEMO-MX-DUPLICATE", count))["rows"]
    summary = summarize(await harness.run_eval(Fake(lambda q: "DELETE FROM transactions"), CASES))
    assert summary["answerable"]["execution_accuracy"] == 0.0
    assert summary["answerable"]["blocked_by_guard"] == summary["answerable"]["n"]
    assert summary["safety"]["forbidden_sql_blocked_by_guard"] == summary["safety"]["n"]
    assert summary["safety"]["safe"] == summary["safety"]["n"]
    assert (await run_scoped_sql(db, "DEMO-MX-DUPLICATE", count))["rows"] == before


@pytest.fixture
def no_wait(monkeypatch):
    """Retries wait seconds in real life; in a test they must not."""

    async def instant(seconds):
        return None

    monkeypatch.setattr(harness.asyncio, "sleep", instant)


@pytest.fixture
def patient(monkeypatch):
    """For tests about a failing provider that must not be cut short by the circuit breaker."""
    monkeypatch.setattr(harness, "MAX_CONSECUTIVE_PROVIDER_ERRORS", 10_000)


class SpyLimiter:
    def __init__(self):
        self.waits = 0

    async def aacquire(self):
        self.waits += 1


async def test_a_busy_provider_is_retried_counted_and_not_blamed_on_the_sql(
    demo_data, no_wait, patient
):
    def down(question):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    spy = SpyLimiter()
    summary = summarize(await harness.run_eval(Fake(down), CASES[:6], limiter=spy))
    assert summary["provider_errors"] == 6 and summary["answerable"]["n"] == 0
    assert summary["answerable"]["execution_accuracy"] is None
    assert summary["model_calls"] == 6 * harness.MAX_ATTEMPTS
    assert spy.waits == summary["model_calls"]  # every try, retries included, waited its turn


async def test_a_failure_that_is_not_a_busy_provider_is_not_retried(demo_data, no_wait):
    def broken(question):
        raise ValueError("invalid model name")

    summary = summarize(await harness.run_eval(Fake(broken), CASES[:3]))
    assert summary["provider_errors"] == 3 and summary["model_calls"] == 3


# ---- the whole command ----


async def run_command(monkeypatch, tmp_path, *flags):
    monkeypatch.setattr(harness, "chat_model", lambda role, **kwargs: Fake(oracle))
    out = tmp_path / "run.json"
    monkeypatch.setattr(sys, "argv", ["run", "--max-rpm", "0", "--out", str(out), *flags])
    await harness.main()
    return json.loads(out.read_text())


async def test_the_command_writes_a_report_tied_to_the_code_and_the_prompt(
    demo_data, monkeypatch, tmp_path
):
    report = await run_command(monkeypatch, tmp_path, "--ids", "tx_count,credit_score")
    meta = report["meta"]
    assert meta["split"] == "regression" and meta["cases"] == 2
    assert meta["git_sha"] and len(meta["prompt_sha"]) == 12
    assert {a["id"] for a in report["attempts"]} == {"tx_count", "credit_score"}


async def test_the_held_out_split_runs_only_the_held_out_cases(demo_data, monkeypatch, tmp_path):
    report = await run_command(monkeypatch, tmp_path, "--split", "heldout")
    assert report["meta"]["split"] == "heldout"
    assert {a["split"] for a in report["attempts"]} == {"heldout"}
    assert report["summary"]["answerable"]["by_split"].keys() == {"heldout"}


def test_the_prompt_fingerprint_changes_with_the_prompt(monkeypatch):
    first = harness.prompt_version()
    assert first == harness.prompt_version()
    monkeypatch.setattr(harness, "build_prompt", lambda: "another prompt")
    assert harness.prompt_version() != first


async def test_a_failed_call_is_reported_with_the_same_fields_as_any_other_attempt(
    no_wait, patient
):
    """No database needed: the unanswerable cases have no gold query to run."""
    cases = [case for case in CASES if case.kind == "unanswerable"]

    def down(question):
        raise RuntimeError("503 UNAVAILABLE")

    failed = await harness.run_eval(Fake(down), cases)
    answered = await harness.run_eval(Fake(oracle), cases)
    assert {frozenset(a) for a in failed} == {frozenset(a) for a in answered}
    assert all(a["correct"] is None and a["provider_error"] for a in failed)
    json.dumps(failed)  # a report with failed calls must still be writable


def test_the_report_says_n_a_when_there_is_nothing_to_measure():
    assert harness.seconds(None) == "n/a" and harness.seconds(1.5) == "1.5s"


# ---- progress, partial reports and a provider that does not come back (no database needed) ----

UNANSWERABLE = [case for case in CASES if case.kind == "unanswerable"]


async def test_progress_is_reported_after_every_attempt():
    seen = []
    await harness.run_eval(
        Fake(oracle),
        UNANSWERABLE,
        repeats=2,
        on_attempt=lambda a, total: seen.append((len(a), total)),
    )
    assert seen == [(n, 2 * len(UNANSWERABLE)) for n in range(1, 2 * len(UNANSWERABLE) + 1)]


async def test_a_provider_that_keeps_refusing_stops_the_run_with_what_was_measured(
    no_wait, monkeypatch
):
    monkeypatch.setattr(harness, "MAX_CONSECUTIVE_PROVIDER_ERRORS", 3)

    def down(question):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    with pytest.raises(harness.ProviderUnavailable) as stop:
        await harness.run_eval(Fake(down), UNANSWERABLE * 5)
    assert len(stop.value.attempts) == 3 and all(a["provider_error"] for a in stop.value.attempts)


async def test_a_short_streak_of_refusals_does_not_stop_the_run(no_wait, monkeypatch):
    monkeypatch.setattr(harness, "MAX_CONSECUTIVE_PROVIDER_ERRORS", 3)
    calls = {"n": 0}

    def flaky(question):
        calls["n"] += 1
        if calls["n"] in (1, 2, 4, 5):  # two in a row, then a good answer, then two more
            raise ValueError("invalid model name")
        return oracle(question)

    attempts = await harness.run_eval(Fake(flaky), UNANSWERABLE)
    assert len(attempts) == len(UNANSWERABLE)
    assert sum(1 for a in attempts if a["provider_error"]) == 4


async def test_the_command_that_gives_up_leaves_a_readable_partial_report(
    no_wait, monkeypatch, tmp_path
):
    monkeypatch.setattr(harness, "MAX_CONSECUTIVE_PROVIDER_ERRORS", 3)

    def down(question):
        raise RuntimeError("503 UNAVAILABLE")

    monkeypatch.setattr(harness, "chat_model", lambda role, **kwargs: Fake(down))
    out = tmp_path / "partial.json"
    ids = "credit_score,loan_interest,other_bank"  # all regression, none needs the database
    monkeypatch.setattr(sys, "argv", ["run", "--max-rpm", "0", "--ids", ids, "--out", str(out)])
    with pytest.raises(SystemExit) as stop:
        await harness.main()
    report = json.loads(out.read_text())
    assert stop.value.code == 2 and report["meta"]["complete"] is False
    assert len(report["attempts"]) == 3 and report["summary"]["provider_errors"] == 3


async def test_a_finished_run_says_it_is_complete(monkeypatch, tmp_path):
    seen = {}

    def factory(role, **kwargs):
        seen.update(kwargs)
        return Fake(oracle)

    monkeypatch.setattr(harness, "chat_model", factory)
    out = tmp_path / "done.json"
    monkeypatch.setattr(
        sys, "argv", ["run", "--max-rpm", "0", "--ids", "credit_score", "--out", str(out)]
    )
    await harness.main()
    assert json.loads(out.read_text())["meta"]["complete"] is True
    assert seen == {"max_retries": harness.CLIENT_ATTEMPTS}  # the runner is the only retry layer
    assert not list(tmp_path.glob("*.tmp"))  # no staging file left behind


def test_the_progress_line_says_what_happened():
    ok = {"id": "x", "repeat": 1, "model_seconds": 2.5, "provider_error": None, "correct": True}
    assert harness.progress_line([ok], 3) == "[1/3] x (repeat 1): ok, 2.5s"
    assert "wrong" in harness.progress_line([ok | {"correct": False}], 3)
    assert "provider error" in harness.progress_line([ok | {"provider_error": "429"}], 3)


# ---- more than one correct SQL, and the reason an answer was wrong ----

ME = ("DEMO-MX-DUPLICATE",)


def make_case(kind="answerable", gold=None, ordered=False) -> Case:
    return Case(
        "x", "test", "es", "question", kind=kind, gold_sql=gold, customers=ME, ordered=ordered
    )


def test_a_case_lists_every_sql_that_counts_as_correct():
    assert make_case(gold="SELECT 1").golds == ("SELECT 1",)
    assert make_case(gold=("SELECT 1", "SELECT 2")).golds == ("SELECT 1", "SELECT 2")
    assert make_case(kind="safety").golds == ()


async def verdict_of(case: Case, sql: str | None) -> dict:
    db = harness.ReadOnlyPostgres()
    gold = await harness.gold_rows(db, case) if case.kind == "answerable" else {}
    return await harness.judge(db, case, sql, gold)


async def test_any_of_the_correct_sqls_is_accepted(demo_data):
    case = make_case(gold=("SELECT 1 AS a", "SELECT 2 AS a"))
    assert (await verdict_of(case, "SELECT 2 AS a"))["correct"] is True
    assert (await verdict_of(case, "SELECT 1 AS a"))["correct"] is True
    wrong = await verdict_of(case, "SELECT 3 AS a")
    assert wrong["correct"] is False and "different values" in wrong["reason"]


async def test_a_wrong_answer_says_why(demo_data):
    case = make_case(gold="SELECT 1 AS a, 2 AS b")
    ok = await verdict_of(case, "SELECT 1 AS a, 2 AS b, 3 AS c")
    assert ok["correct"] is True and ok["reason"] is None
    short = await verdict_of(case, "SELECT 1 AS a")
    assert "1 rows x 1 columns, the gold has 1 rows x 2 columns" in short["reason"]
    several = await verdict_of(case, "SELECT 1 AS a, 2 AS b UNION ALL SELECT 1, 2")
    assert "2 rows x 2 columns, the gold has 1 rows x 2 columns" in several["reason"]
    broken = await verdict_of(case, "SELECT nothing FROM transactions")
    assert broken["ran"] is False and "DEMO-MX-DUPLICATE" in broken["reason"]
    declined = await verdict_of(case, None)
    assert "declined" in declined["reason"]


async def test_answering_what_the_tables_cannot_answer_says_so(demo_data):
    case = make_case(kind="unanswerable")
    answered = await verdict_of(case, "SELECT 1 AS a")
    assert answered["correct"] is False and "cannot answer" in answered["reason"]
    assert (await verdict_of(case, None))["reason"] is None


def test_the_progress_line_shows_the_reason_of_a_wrong_answer():
    wrong = {
        "id": "x", "repeat": 1, "model_seconds": 2.0, "provider_error": None,
        "correct": False, "reason": "same shape (1 rows x 1 columns), different values",
    }  # fmt: skip
    line = harness.progress_line([wrong], 3)
    assert "wrong (" in line and "different values" in line


# ---- scoring a saved report again ----


async def test_a_saved_report_is_scored_again_with_todays_rules(demo_data):
    from evals.text_to_sql import rescore

    saved = await harness.run_eval(Fake(oracle), CASES)
    stale = [a | {"correct": False, "reason": "old rule"} for a in saved]  # as an old run left it
    again = await rescore.rescore(stale)
    assert summarize(again)["answerable"]["execution_accuracy"] == 1.0
    assert rescore.changes(stale, again) and all(
        "wrong -> ok" in line for line in rescore.changes(stale, again)
    )
    assert rescore.changes(saved, again) == []


async def test_rescoring_leaves_refused_calls_and_unknown_cases_as_they_were(demo_data):
    from evals.text_to_sql import rescore

    refused = {"id": "tx_count", "provider_error": "429", "sql": None, "correct": None, "repeat": 1}
    unknown = {
        "id": "a_case_that_was_removed",
        "provider_error": None,
        "sql": "SELECT 1",
        "correct": True,
    }
    unknown |= {"repeat": 1}
    assert await rescore.rescore([refused, unknown]) == [refused, unknown]


async def test_the_sql_the_model_wrote_is_what_gets_scored_again(demo_data):
    from evals.text_to_sql import rescore

    case = next(c for c in CASES if c.id == "tx_count")
    wrong = Fake(lambda q: "```sql\nSELECT count(*) + 1 AS n FROM transactions\n```")
    (attempt,) = await harness.run_eval(wrong, [case])
    assert attempt["correct"] is False
    (again,) = await rescore.rescore([attempt])
    assert again["correct"] is False and again["sql"] == attempt["sql"]


async def test_the_report_records_where_the_model_was_served_from(demo_data, monkeypatch, tmp_path):
    from app.config import Settings

    monkeypatch.setattr(harness, "get_settings", lambda: Settings(google_cloud_location="global"))
    report = await run_command(monkeypatch, tmp_path, "--ids", "credit_score")
    assert report["meta"]["location"] == "global"


# ---- a held-out run is blind: seeing what failed would be tuning ----

HELD_OUT_IDS = [case.id for case in CASES if case.split == "heldout"]


async def test_a_held_out_run_prints_totals_and_no_case(demo_data, monkeypatch, tmp_path, capsys):
    report = await run_command(monkeypatch, tmp_path, "--split", "heldout")
    out = capsys.readouterr().out
    assert "Blind run" in out and f"[{len(HELD_OUT_IDS)}/{len(HELD_OUT_IDS)}]" in out
    assert not [case_id for case_id in HELD_OUT_IDS if case_id in out]
    assert "category" not in out and "language" not in out
    assert report["meta"]["blind"] is True
    assert {a["id"] for a in report["attempts"]} == set(HELD_OUT_IDS)  # kept for audit


async def test_a_regression_run_still_shows_every_case(demo_data, monkeypatch, tmp_path, capsys):
    report = await run_command(monkeypatch, tmp_path, "--ids", "credit_score,tx_count")
    out = capsys.readouterr().out
    assert "credit_score" in out and "category" in out and "Blind run" not in out
    assert report["meta"]["blind"] is False


def test_the_summary_of_a_blind_run_has_no_breakdown(capsys):
    group = {"x": {"n": 1, "ex": 0.0}}
    answerable = {
        "n": 1, "execution_accuracy": 0.0, "ran_without_error": 1.0, "declined_wrongly": 0,
        "blocked_by_guard": 0, "per_repeat": [0.0], "by_category": group,
        "by_language": group, "by_split": group,
    }  # fmt: skip
    summary = {
        "answerable": answerable, "unanswerable": {"n": 0, "declined": None, "answered_anyway": 0},
        "safety": {
            "n": 0, "safe": 0, "declined": 0, "forbidden_sql_blocked_by_guard": 0, "leaks": 0,
        },
        "latency_model_seconds": {"p50": 1.0, "p95": 1.0}, "model_calls": 1, "provider_errors": 0,
    }  # fmt: skip
    harness.show(summary, blind=True)
    assert "x=" not in capsys.readouterr().out
    harness.show(summary)
    assert "x=0.0(1)" in capsys.readouterr().out


async def test_rescoring_a_held_out_report_says_how_many_changed_not_which(demo_data):
    from evals.text_to_sql import rescore

    saved = await harness.run_eval(Fake(oracle), CASES)
    stale = [a | {"correct": False} for a in saved[:2]] + saved[2:]
    again = await rescore.rescore(stale)
    assert rescore.changes(stale, again, blind=True) == ["2 verdicts changed"]
    assert rescore.changes(saved, again, blind=True) == []
    assert all(
        a["id"] in line for a, line in zip(saved[:2], rescore.changes(stale, again), strict=True)
    )
