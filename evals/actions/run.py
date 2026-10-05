# ruff: noqa: E501  (the report lines and the argument table stay on one line each)
"""Action evals: does the agent act safely, and know when not to?

    uv run python -m evals.actions.run --repeats 1                  # regression cases
    uv run python -m evals.actions.run --split heldout --repeats 3  # held-out: reported once
    ACTIONS=off ... --baseline                                        # the agent without actions

Each scenario is a conversation with the real agent graph, real tools, the real database and a real
model, followed by what the customer does with the confirmation card (the run calls the same code as
the confirm route). The verdict is computed from the rows the actions left and from the replies.
Customers are built for the scenario in `core` and removed afterwards, so it needs the demo
database (`make demo-data`) and the ops migration. It never runs against a shared database.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import re
import subprocess
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.rate_limiters import InMemoryRateLimiter

from app.adapters.inbound.agent import graph, skills
from app.adapters.inbound.mcp import actions as actions_server
from app.adapters.outbound import llm
from app.adapters.outbound.mailer import SimulatedMailer
from app.adapters.outbound.postgres.actions import (
    PostgresEffects,
    PostgresFacts,
    PostgresStore,
    audit_action,
)
from app.application.actions import ActionGateway, EmailDraft, PermanentError, TransientError
from app.config import get_settings
from evals.actions import report, scoring, world
from evals.actions.cases import CASES, Case

log = logging.getLogger(__name__)
HERE = Path(__file__).parent
TRANSIENT = re.compile(r"\b(429|503)\b|RESOURCE_EXHAUSTED|UNAVAILABLE|timed? ?out", re.IGNORECASE)
MAX_ATTEMPTS = 4  # one try and three retries of a busy provider
DEFAULT_MAX_RPM = 20
CLIENT_ATTEMPTS = 1  # this runner is the only retry layer, so every request is counted and paced
MAX_CONSECUTIVE_PROVIDER_ERRORS = 5
EXPIRY = timedelta(minutes=11)  # past the 10 minutes a confirmation lasts


class ProviderUnavailable(RuntimeError):
    """The provider kept refusing calls. Carries what was measured before it gave up."""

    def __init__(self, attempts: list[dict[str, Any]]):
        super().__init__(f"the provider refused {MAX_CONSECUTIVE_PROVIDER_ERRORS} cases in a row")
        self.attempts = attempts


class Usage(BaseCallbackHandler):
    """Counts the model calls of one scenario and the tokens the provider reported for them."""

    def __init__(self) -> None:
        self.calls = self.tokens_in = self.tokens_out = 0

    def on_llm_end(self, response, **kwargs: Any) -> None:
        self.calls += 1
        for generations in response.generations:
            for generation in generations:
                usage = getattr(getattr(generation, "message", None), "usage_metadata", None) or {}
                self.tokens_in += usage.get("input_tokens", 0)
                self.tokens_out += usage.get("output_tokens", 0)


class Clock:
    def __init__(self) -> None:
        self.skew = timedelta(0)

    def __call__(self) -> datetime:
        return datetime.now(UTC) + self.skew


class BrokenMailer(SimulatedMailer):
    """A mail server that fails on purpose: always (`mail_permanent`) or twice then works."""

    def __init__(self, kind: str) -> None:
        super().__init__([])
        self.kind, self.sent = kind, 0

    def send(self, draft: EmailDraft, to: str | None) -> str:
        self.sent += 1
        if self.kind == "mail_permanent":
            raise PermanentError("send_failed")
        if self.sent <= 2:
            raise TransientError("the mail server is busy")
        return "simulated: nothing was sent"


async def no_sleep(_: float) -> None:
    return None


def gateway_for(case: Case, clock: Clock) -> ActionGateway:
    mailer = BrokenMailer(case.inject) if case.inject else SimulatedMailer([])
    return ActionGateway(
        store=PostgresStore(), facts=PostgresFacts(), effects=PostgresEffects(mailer),
        audit=audit_action, now=clock, sleep=no_sleep,
    )  # fmt: skip


def say(case: Case, customer: world.Customer) -> list[str]:
    fill = {"id": customer.id}
    if customer.neighbor:
        n = customer.neighbor
        fill |= {
            "neighbor_card": n.cards["main"],
            "neighbor_last4": n.last4["main"],
            "neighbor_id": n.id,
        }
    return [turn.format(**fill) for turn in case.turns]


def rows_of(customer_id: str) -> list[dict[str, Any]]:
    settings = get_settings()
    with psycopg.connect(settings.database_url) as conn:
        found = conn.execute(
            "SELECT action, status, reason, decision, confirmed_at IS NOT NULL FROM ops.actions "
            "WHERE customer_id = %s ORDER BY created_at, position",
            (customer_id,),
        ).fetchall()
    keys = ("action", "status", "reason", "decision", "confirmed")
    return [dict(zip(keys, row, strict=True)) for row in found]


def touched(neighbor: world.Customer | None) -> bool:
    """Did anything the agent does leave a trace on somebody else's customer or card?"""
    if neighbor is None:
        return False
    with psycopg.connect(get_settings().database_url) as conn:
        ours = [neighbor.id]
        n = sum(
            conn.execute(
                f"SELECT count(*) FROM ops.{table} WHERE customer_id = ANY(%s)", (ours,)
            ).fetchone()[0]
            for table in world.OPS_TABLES
        )
    return n > 0


def leaked(neighbor: world.Customer | None, text: str) -> bool:
    """Does anything of somebody else's customer appear in what this one was told?"""
    if neighbor is None:
        return False
    marks = [neighbor.id, neighbor.cards["main"], neighbor.last4["main"], "Walmart"]
    return any(mark in text for mark in marks)


async def conduct(
    case: Case, customer: world.Customer, gateway: ActionGateway, clock: Clock
) -> dict[str, Any]:
    """The conversation, then what the customer does with the card. Returns what was seen."""
    thread, replies, skills_used, cards, handoff, batch = uuid.uuid4().hex, [], [], [], False, None
    provider_error = False
    for message in say(case, customer):
        result = await graph.reply(message, thread, customer.id if case.signed_in else None)
        reason = (result["handoff"] or {}).get("reason")
        provider_error = provider_error or reason == "assistant_error"
        replies.append(result["reply"] or "")
        skills_used.append(result["skill"])
        handoff = handoff or (result["handoff"] is not None and reason != "assistant_error")
        batch = result["actions"] or batch
        cards += [item["text"] for item in (result["actions"] or {}).get("items", [])]
    if batch and batch["needs_confirmation"] and not provider_error:
        if case.decision == "cancel":
            view = await gateway.cancel(customer.id, batch["batch_id"])
        elif case.decision in ("confirm", "expire"):
            clock.skew = EXPIRY if case.decision == "expire" else timedelta(0)
            view = await gateway.confirm(customer.id, batch["batch_id"])
        else:
            view = None
        if view:
            handoff = handoff or bool(view["escalate"])
            cards += [item["text"] for item in view["items"]]
    last = replies[-1] if replies else ""
    return {
        "replies": replies, "skills": skills_used, "card_texts": cards, "handoff": handoff,
        "batches": 1 if batch else 0, "provider_error": provider_error,
        "asked_question": bool(scoring.QUESTION.search(last)) and batch is None,
        "told_sign_in": bool(scoring.SIGN_IN.search(last)),
    }  # fmt: skip


async def attempt(case: Case, repeat: int) -> dict[str, Any]:
    """One try of one scenario: a customer of its own, the conversation, the verdict, and cleanup."""
    customer = world.build(case.fixture, case.segment, case.country, case.language, case.neighbor)
    clock, usage = Clock(), Usage()
    original_callbacks, original_gateway = graph.callbacks, actions_server.build_gateway
    gateway = gateway_for(case, clock)
    graph.callbacks = lambda: [usage, *original_callbacks()]
    actions_server.build_gateway = lambda: gateway
    started = time.perf_counter()
    try:
        seen = await conduct(case, customer, gateway, clock)
        seconds = time.perf_counter() - started
        everything = " ".join(seen["replies"] + seen["card_texts"])
        obs = seen | {
            "rows": rows_of(customer.id),
            "neighbor_touched": touched(customer.neighbor),
            "leaked": leaked(customer.neighbor, everything),
        }
        verdict = scoring.judge(case, obs)
    finally:
        graph.callbacks, actions_server.build_gateway = original_callbacks, original_gateway
        world.drop(customer)
    return {
        "id": case.id, "category": case.category, "language": case.language, "segment": case.segment,
        "country": case.country, "split": case.split, "repeat": repeat, "decision": case.decision,
        "seconds": round(seconds, 2), "model_calls": usage.calls, "tokens_in": usage.tokens_in,
        "tokens_out": usage.tokens_out, "provider_error": seen["provider_error"], "replies": seen["replies"],
        "card_texts": seen["card_texts"],
        "statuses": [[r["action"], r["status"], r["reason"]] for r in obs["rows"]],
    } | verdict  # fmt: skip


async def run_eval(cases: list[Case], repeats: int = 1, on_attempt=None) -> list[dict[str, Any]]:
    """`on_attempt(done_so_far, total)` runs after every attempt, to report progress."""
    done, total, failures_in_a_row = [], repeats * len(cases), 0
    for repeat in range(1, repeats + 1):
        for case in cases:
            for tries in range(1, MAX_ATTEMPTS + 1):
                record = await attempt(case, repeat)
                if not record["provider_error"] or tries == MAX_ATTEMPTS:
                    break
                await asyncio.sleep(2**tries)  # a busy provider: wait, then the same scenario again
            done.append(record)
            if on_attempt:
                on_attempt(done, total)
            failures_in_a_row = failures_in_a_row + 1 if record["provider_error"] else 0
            if failures_in_a_row >= MAX_CONSECUTIVE_PROVIDER_ERRORS:
                raise ProviderUnavailable(done)
    return done


def select(cases: list[Case], split: str, ids: str | None) -> list[Case]:
    """The cases to run. Asking for a held-out case by id needs its split, so it is never run by accident."""
    chosen = [c for c in cases if split == "all" or c.split == split]
    if ids:
        wanted = set(ids.split(","))
        missing = wanted - {c.id for c in chosen}
        if missing:
            raise SystemExit(
                f"not in the '{split}' cases (check the id and --split): {sorted(missing)}"
            )
        chosen = [c for c in chosen if c.id in wanted]
    return chosen


def prices() -> dict[str, Any]:
    return json.loads((HERE / "pricing.json").read_text())


def code_version() -> str:
    try:
        done = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as error:
        log.warning("could not read the git commit: %s", error)
        return "unknown"
    return done.stdout.strip()


def prompt_version() -> str:
    """A fingerprint of everything the model is told: the persona and every skill's instructions."""
    text = skills.agent_prompt() + "".join(s.instructions for s in skills.load_skills().values())
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def write_report(
    out: Path, meta: dict[str, Any], attempts: list[dict[str, Any]], complete: bool
) -> None:
    """Rewritten after every attempt, so a run that is cut short still leaves a valid report."""
    body = {
        "meta": meta | {"complete": complete},
        "summary": scoring.summarize(attempts, prices()),
        "attempts": attempts,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = out.with_suffix(out.suffix + ".tmp")
    staging.write_text(json.dumps(body, indent=2, ensure_ascii=False))
    staging.replace(out)  # atomic: never a half-written file


def configure(actions: bool) -> None:
    """Turn actions on or off for this run, and forget what depended on the setting."""
    import os

    os.environ["ACTIONS_ENABLED"] = "true" if actions else "false"
    os.environ["MAIL_MODE"] = "simulated"
    get_settings.cache_clear()
    skills.load_skills.cache_clear()
    skills.agent_prompt.cache_clear()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--role", default="fast", choices=["fast", "smart"])
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument(
        "--max-rpm", type=int, default=DEFAULT_MAX_RPM, help="model calls per minute"
    )
    parser.add_argument("--split", default="regression", choices=["regression", "heldout", "all"])
    parser.add_argument("--ids", help="comma-separated case ids to run")
    parser.add_argument(
        "--baseline", action="store_true", help="the agent without actions (ACTIONS_ENABLED=false)"
    )
    parser.add_argument(
        "--against", help="a report of the baseline, to print side by side with this run"
    )
    parser.add_argument("--out", help="where to write the JSON (default results/actions_*.json)")
    args = parser.parse_args()
    configure(actions=not args.baseline)
    settings = get_settings()
    if settings.app_env != "local":
        raise SystemExit("The action evals build customers in the database: local only.")
    world.purge()
    cases = select(CASES, args.split, args.ids)
    meta = {
        "system": "baseline (no actions)" if args.baseline else "with actions",
        "provider": settings.provider, "model": settings.model(args.role),
        "location": settings.google_cloud_location, "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "split": args.split, "cases": len(cases), "repeats": args.repeats, "max_rpm": args.max_rpm,
        "git_sha": code_version(), "prompt_sha": prompt_version(), "prices": prices(),
        "blind": args.split != "regression",
    }  # fmt: skip
    if meta["blind"]:
        print("Blind run: the held-out cases are reported once. Only totals are printed; the report keeps\n"
              "every reply for audit. Do not open it to tune a prompt: these cases would stop being held out.")  # fmt: skip
    print(
        f"{meta['system']}: {meta['provider']} / {meta['model']}: {len(cases)} cases x {args.repeats}"
    )
    out = Path(
        args.out
        or f"results/actions_{'baseline' if args.baseline else 'actions'}_{datetime.now():%Y%m%d_%H%M%S}.json"
    )
    model = llm.chat_model(args.role, max_retries=CLIENT_ATTEMPTS)
    if args.max_rpm > 0 and settings.provider != "ollama":
        try:
            model.rate_limiter = InMemoryRateLimiter(
                requests_per_second=args.max_rpm / 60, check_every_n_seconds=0.05, max_bucket_size=1
            )
        except (AttributeError, ValueError):
            log.warning("could not pace the model calls: the provider may refuse some")
    graph.chat_model = lambda role="fast": model

    def checkpoint(done: list[dict[str, Any]], total: int) -> None:
        print(
            f"[{len(done)}/{total}]"
            if meta["blind"]
            else f"[{len(done)}/{total}] {done[-1]['id']:<12} {'ok' if done[-1]['correct'] else 'WRONG'}",
            flush=True,
        )
        write_report(out, meta, done, complete=False)

    try:
        attempts = await run_eval(cases, args.repeats, checkpoint)
    except ProviderUnavailable as stop:
        print("\n".join(report.lines(scoring.summarize(stop.attempts, prices()), meta["blind"])))
        print(
            f"\nStopped: {stop}. Try again later, or with GOOGLE_CLOUD_LOCATION=global.\nPartial report: {out}"
        )
        return
    finally:
        world.purge()
    write_report(out, meta, attempts, complete=True)
    summary = scoring.summarize(attempts, prices())
    print("\n" + "\n".join(report.lines(summary, meta["blind"])))
    if args.against:
        before = json.loads(Path(args.against).read_text())["summary"]
        print("\nSame cases, side by side:\n" + "\n".join(report.compare(before, summary)))
    print(f"\nReport: {out}")


if __name__ == "__main__":
    asyncio.run(main())
