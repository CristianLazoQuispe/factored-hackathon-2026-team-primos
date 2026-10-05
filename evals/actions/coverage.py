# ruff: noqa: E501  (the SQL and the table columns stay on one line each)
"""What each demo customer can do with each action: a dry run of the policy against their data.

    uv run python -m evals.actions.coverage            # the DEMO-* customers and DEMO_CUSTOMER_IDS
    uv run python -m evals.actions.coverage CLI-ABC... # some customers

Nothing is proposed, stored or executed: it asks the same policy the chat asks, with the same data. It is
the answer to "will this action work for this customer in the demo?". Run it against Cloud SQL through the
proxy (DATABASE_URL pointing at localhost) to check the customers that are really offered.
"""

import asyncio
import sys
from collections import Counter

from app.adapters.outbound.postgres import query
from app.adapters.outbound.postgres.actions import PostgresFacts
from app.config import get_settings
from app.domain import actions as policy
from app.domain.actions import CATALOG, Decision, Facts, Verdict

WORDS = {
    Verdict.ALLOW: "direct",
    Verdict.CONFIRM: "confirm",
    Verdict.DENY: "refused",
    Verdict.ESCALATE: "person",
}
RECENT_CHARGES = 25


def say(decision: Decision) -> str:
    word = WORDS[decision.verdict]
    return f"{word}: {decision.reason}" if decision.reason else word


def params(action: str, **values):
    return CATALOG[action].params(**values)


async def customers(asked: list[str]) -> list[str]:
    if asked:
        return asked
    demo = await query(
        "SELECT customer_id FROM core.customers WHERE customer_id ~ '^DEMO-' "
        "AND customer_id !~ '^DEMO-EVL-' ORDER BY customer_id",
        {},
    )
    offered = [i.strip() for i in get_settings().demo_customer_ids.split(",") if i.strip()]
    return list(dict.fromkeys([r["customer_id"] for r in demo] + offered))


async def row(customer_id: str) -> dict[str, str]:
    facts = PostgresFacts()
    cards = await query(
        "SELECT product_id FROM core.products WHERE customer_id = %(c)s AND product_status <> 'Closed' "
        "AND product_type = ANY(%(types)s) ORDER BY product_id",
        {"c": customer_id, "types": sorted(policy.CARD_TYPES)},
    )
    out = {"customer": customer_id, "cards": str(len(cards))}
    # Every card, not the first: a customer who owes on one card may hold another that can be cancelled.
    possible = {"block_card": 0, "cancel_card": 0}
    refused: Counter[str] = Counter()
    for found in cards:
        card = await facts.card(customer_id, found["product_id"])
        for action in possible:
            wanted = params(action, product_id=found["product_id"])
            decision = policy.decide(action, wanted, Facts(card=card))
            if decision.verdict in (Verdict.CONFIRM, Verdict.ALLOW):
                possible[action] += 1
            else:
                refused[f"{action.split('_')[0]}: {decision.reason}"] += 1
    for action, count in possible.items():
        out[action] = f"{count} of {len(cards)}"
    out["card_refusals"] = "; ".join(f"{k} x{n}" for k, n in sorted(refused.items()))
    charges = await query(
        "SELECT transaction_id FROM core.transactions WHERE customer_id = %(c)s "
        "ORDER BY transaction_date DESC LIMIT %(n)s",
        {"c": customer_id, "n": RECENT_CHARGES},
    )
    seen: Counter[str] = Counter()
    for charge in charges:
        tx = await facts.transaction(customer_id, charge["transaction_id"])
        decision = policy.decide(
            "open_payment_inquiry",
            params("open_payment_inquiry", transaction_id=charge["transaction_id"]),
            Facts(tx=tx),
        )
        seen[say(decision)] += 1
    eligible = sum(n for k, n in seen.items() if k.startswith(("confirm", "direct")))
    out["inquiry"] = f"{eligible} of {len(charges)} charges"
    out["inquiry_refusals"] = ", ".join(
        f"{k.split(': ')[-1]} x{n}" for k, n in seen.items() if k.startswith("refused")
    )
    email = await facts.email_masked(customer_id)
    out["email"] = say(
        policy.decide(
            "send_summary_email",
            params("send_summary_email", topic="balances"),
            Facts(email_masked=email),
        )
    )
    out["callback"] = say(
        policy.decide("request_callback", params("request_callback", window="evening"), Facts())
    )
    out["alert"] = say(policy.decide("set_alert", params("set_alert", kind="payment_due"), Facts()))
    return out


def table(rows: list[dict[str, str]]) -> list[str]:
    columns = (
        "customer",
        "cards",
        "block_card",
        "cancel_card",
        "inquiry",
        "email",
        "callback",
        "alert",
    )
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    for r in rows:
        lines.append("| " + " | ".join(r[c] for c in columns) + " |")
    notes = []
    for r in rows:
        parts = []
        if r["card_refusals"]:
            parts.append(f"cards not possible: {r['card_refusals']}")
        if r["inquiry_refusals"]:
            parts.append(f"charges not eligible: {r['inquiry_refusals']}")
        if parts:
            notes.append(f"- {r['customer']}: " + " | ".join(parts))
    return lines + ([""] + notes if notes else [])


async def main() -> None:
    asked = sys.argv[1:]
    print("\n".join(table([await row(c) for c in await customers(asked)])))


if __name__ == "__main__":
    asyncio.run(main())
