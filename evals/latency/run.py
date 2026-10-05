"""Latency of the frequent questions and khipear requests, against a running API.

    uv run python -m evals.latency.run --url http://localhost:8080 --repeats 3

It signs in once as one customer, sends each message in a new conversation and times the whole
round trip of POST /api/chat, as the web chat sees it. A reply that leaves a proposal is cancelled
with the Cancelar button, which is timed too (no model runs there): nothing moves, so the run can
be repeated. The table also shows the skill and the tools of each reply, so a request that was
routed somewhere else is visible. The messages name the accounts of DEMO-MX-KHIPU.
"""

import argparse
import time
from collections import Counter

import httpx

from evals.actions.scoring import percentile

CASES = [  # name, message
    ("saldo", "¿cuál es mi saldo?"),
    ("deuda y vencimiento", "¿cuánto debo en mi tarjeta y cuándo vence?"),
    ("últimos movimientos", "muéstrame mis últimos movimientos"),
    ("gasto del mes", "¿cuánto gasté en los últimos 30 días?"),
    ("khipear a mi tarjeta", "khipea 100 a mi tarjeta desde mi cuenta corriente"),
    ("khipear entre mis cuentas", "pasa 100 de mi cuenta de ahorro a mi cuenta corriente"),
    ("khipear a otro cliente", "khipéale 100 a la cuenta 4000000033 desde mi cuenta de ahorro"),
    ("recibos pendientes", "¿qué recibos tengo pendientes?"),
    ("pagar un recibo", "paga la luz desde mi cuenta corriente"),
]
BUTTON = "botón (sin modelo)"


def timed(client: httpx.Client, path: str, body: dict) -> tuple[float, dict]:
    started = time.perf_counter()
    response = client.post(path, json=body)
    seconds = time.perf_counter() - started
    response.raise_for_status()
    return seconds, response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--customer", default="DEMO-MX-KHIPU")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()

    seconds: dict[str, list[float]] = {name: [] for name, _ in CASES} | {BUTTON: []}
    seen: dict[str, Counter] = {name: Counter() for name in seconds}
    with httpx.Client(base_url=args.url, timeout=180) as client:
        login = {"user": args.customer, "password": args.customer}
        token = client.post("/api/auth/token", json=login).raise_for_status().json()
        client.headers["Authorization"] = f"Bearer {token['access_token']}"
        for _ in range(args.repeats):
            for name, message in CASES:
                took, reply = timed(client, "/api/chat", {"message": message})
                seconds[name].append(took)
                proposal = reply["confirmation"]
                outcome = "propuesta" if proposal else "respuesta"
                seen[name][f"{reply['skill']} [{', '.join(reply['tools_used'])}] {outcome}"] += 1
                if proposal:
                    cancel = {"transfer_id": proposal["transfer_id"]}
                    took, closed = timed(client, "/api/khipu/cancel", cancel)
                    seconds[BUTTON].append(took)
                    seen[BUTTON][closed["status"]] += 1

    print(f"{args.url}  customer {args.customer}  repeats {args.repeats}\n")
    print(f"{'case':28s} {'n':>3s} {'p50 s':>7s} {'p95 s':>7s}  skill [tools] outcome (times)")
    for name, values in seconds.items():
        if not values:
            continue
        what = "; ".join(f"{k} ({n})" for k, n in seen[name].most_common())
        p50, p95 = percentile(values, 50), percentile(values, 95)
        print(f"{name:28s} {len(values):3d} {p50:7.2f} {p95:7.2f}  {what}")


if __name__ == "__main__":
    main()
