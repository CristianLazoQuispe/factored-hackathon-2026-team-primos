# 0002. Hexagonal layout: `app/` backend, `data_pipeline/` batch data, `web/` frontend

- Status: accepted
- Date: 2026-09-27

## Context
The system's core claim is that the LLM never decides permissions or policy: deterministic code does. The code base was one flat package (`src/factored`), where business rules, frameworks and I/O could mix. Four people are about to write code in parallel. No product name has been chosen yet.

## Decision
- **`app/`** is the backend, a Python package called `app`:
  - `domain/` holds pure business rules. It has no I/O and no framework imports.
  - `application/` holds the use cases, which are the agent's skills. It may import `domain` only.
  - `adapters/inbound/` holds what drives the app: FastAPI, Telegram, the MCP tool server, and the LLM agent.
  - `adapters/outbound/` holds what the app drives: Postgres (`schema.sql`), LLM providers, and tracing.
- **`data_pipeline/`** holds the batch data jobs (download, bronze, sample, fixtures, silver, load). It is not hexagonal, because it is batch ETL rather than a service.
- **`web/`** holds the Next.js frontend, unchanged.
- `tests/test_architecture.py` fails if `domain` or `application` import adapters or frameworks.
- Names stay neutral (`app`, database `agent`) until the team picks a product name.

## Alternatives considered
- **Keep the flat package.** It is faster today, but the rule "the LLM doesn't decide" would not be visible or enforced in the code.
- **Ports as `Protocol`/ABC for every dependency now.** Rejected: each would have one implementation. A port is added when a second implementation exists, for example Cloud SQL next to local Postgres, or a second LLM provider.

## Consequences
- Deterministic rules (escalation, amount tiers, duplicate/pending/FX checks) live in `domain/` as unit-testable functions. Judges can read them without reading the LLM code.
- Swapping infrastructure (local Postgres ↔ Cloud SQL, Gemini ↔ another provider) touches only `adapters/outbound/`.
- Imports changed from `factored.*` to `app.*` and `data_pipeline.*`. Branches created before this change need a rebase.
