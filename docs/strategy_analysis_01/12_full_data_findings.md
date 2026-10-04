# Full Dataset: What It Holds and What We Can Use

> Date: 2026-10-03. Measured on the **full** organizer dataset (`make data bronze`, 7,671 CSV files, 5.35 GB → 23M rows).
> Follows [11_data_model.md](11_data_model.md), which was measured on a subset.

## 1. What we have

| Table | Rows | Customers | Usable for |
|---|---|---|---|
| customers | 150,000 | 150,000 | Identity, segment, country: **yes** |
| products | 400,000 | — | Balances, cards, loans: **yes** |
| transactions | 4,425,008 | 134,515 | Charges and spending: **yes, but thin** |
| digital_events | 15,620,994 | — | App sessions (login, IP country): **yes, for evidence** |
| call_center_interactions | 686,296 | 148,443 | Contact-reason mix and baseline KPIs: **aggregates only** |
| satisfaction_surveys | 212,759 | 113,640 | Baseline CSAT/NPS: **aggregates only** |
| complaints | 67,095 | 54,145 | Category mix: **aggregates only** |
| call_transcripts | 171,321 | 101,951 | **No** (see §2) |
| campaign_sends / marketing_campaigns | 1,746,801 / 200 | — | No (out of scope) |
| branches, service_agents, daily_exchange_rates | 350 / 1,200 / 13,164 | — | Reference, FX: yes |

Range: 2023-06-17 → 2026-06-18. Bronze Parquet lives in `data/bronze/` (git-ignored).

## 2. The customer-service data is generated from templates, not from real behavior

We checked it to see whether it could drive design decisions (intents, routing, escalation rules, answer style). **It can't.** Every text field is a fixed template, and most outcomes are random draws that don't depend on anything.

| Field | What it really holds |
|---|---|
| `call_transcripts.full_text` | 546 distinct texts in 171k rows. The customer's opening line is **always one of two balance inquiries** ("necesito consultar el saldo de mi tarjeta de crédito" / "...saldo actual en mi cuenta de ahorros"), including transcripts labeled *Queja* or *Retención*. The agent's reply keeps unfilled placeholders: `Su saldo actual es de {monto} {moneda}` |
| `call_transcripts.detected_intents` | Always `consulta_general` (or null) |
| `call_transcripts.detected_keywords` | Permutations of "banco, cuenta, servicio" |
| `call_center_interactions.contact_reason` | Identical to `reason_category`: 6 values, no finer reason |
| `complaints.description` | 5 strings: "Queja relacionada con {category}" |
| `complaints.resolution` | 5 generic sentences, random across categories |
| `satisfaction_surveys.open_comments` | 18 canned sentences |

Outcomes, checked against every dimension:

| Outcome | Depends on | Doesn't depend on |
|---|---|---|
| `was_resolved` (FCR) | `reason_category` (Transaccional 92%, Producto 90%, Técnico 70%, Comercial 65%, Retención 60%, Queja 44%); Neutral sentiment 83% vs 64% for every other sentiment | channel, year |
| `was_escalated` | **nothing**: 10% in every reason, channel and sentiment | — |
| `wait_time_seconds` | **nothing**: about 120 s average everywhere | — |
| `duration_seconds` | reason (221 s Transaccional → 540 s Comercial) | channel |
| Survey `main_score` | **only** `was_resolved`, deterministically: CSAT 3 vs 2, CES 3 vs 2, NPS 6 vs 3 | interaction sentiment, reason |
| Complaint SLA breach / resolution days | **nothing**: 20% breached and about 15.6 days in every category and priority | — |

Scales don't match the data dictionary: CSAT and CES run 1–4 and NPS runs 2–7.

**Consequence:** no intent classifier, no RAG over past conversations, no learned escalation rule, and no tone or style mined from transcripts. The golden eval set and the policy knowledge base must be **team-made and labeled as such**. These tables are good only for **volume mix and baseline KPIs**, which is what the management dashboard needs as its "antes de Quipu" reference.

## 3. Transactions are thin

- **Per customer:** median **29 transactions in 3 years** (p90 59, max 150). 15,485 customers have none. In 2026 a customer with activity in a given month has a median of **1** transaction that month.
- **Merchants:** 77% have no `merchant_category`. Only **24 merchant names** exist in the whole dataset (4 per category: Food, Services, Transport, Entertainment, Health, Other).
- **Status:** Approved 92%, Declined 5%, Pending 2%, Reversed 1%.

This confirms the 11_data_model decision. The spending views (`/mis-finanzas`, `/consola/perfil`) and the charge-investigation demos need the **8 team fixtures** (about 30 purchases in 90 days each). For the organizer customers, keep spending simple: by category and month, no merchant analysis.

## 4. Announced quality problems: what actually appears

| Announced | Found on the full data |
|---|---|
| ~2% duplicates | **0 duplicate primary keys** in transactions, interactions, complaints, surveys or products |
| ~5% nulls | Yes. Some are structural: `merchant_category` 77% null, `customer_detected_accent` 30%, `complaints.subcategory` about 8% |
| Late-arriving partitions | `process_date` is the same day as the event or one day earlier (a time-zone shift), never later. No late data |
| Schema evolution | Bronze reads every daily file with one column set |
| Orphaned FKs | `customers.registration_branch_id` (see 11 §1). Not re-measured |
| — | "Mexico" (40k) vs "México" (2.1M) in `transaction_country`: silver already normalizes it |
| — | `campaign_sends` has 1,083 daily partitions vs 1,097 for the other fact tables |

Silver's dedup and contracts are still worth keeping, because judges score how we handle the announced problems. The quality report should state honestly that dedup removed 0 rows.

## 5. Schema proposal

Rule: **Postgres serves what a screen or a tool reads per customer; Parquet/DuckDB holds the rest.** No cross-table modeling of the call-center data beyond aggregates.

### 5.1 `core`: already defined, keep it

`customers`, `products`, `transactions`, `fx_rates`, `app_sessions`, `customer_service_summary` stay as in `schema.sql`. For the full load, limit `core.transactions` to a window (e.g. the last 12 months, about 1.5M rows) and keep the index on `(customer_id, transaction_date DESC)`.

Drop `core.call_transcripts` from serving: it has nothing the agent should say. The `data_lookup` SQL agent would otherwise answer "your last call" with a template that has `{monto}` in it.

### 5.2 `core`: new, for the screens now on mock data

`web/lib/profile.ts` (`/mis-finanzas`, `/consola/perfil`) needs:

```sql
-- One row per customer, month and category (transactions are thin, so this stays small).
CREATE TABLE core.customer_spend_monthly (
    customer_id      text NOT NULL REFERENCES core.customers,
    month            date NOT NULL,                 -- first day of the month
    category         text NOT NULL,                 -- merchant_category, 'Otros' when null
    currency         text NOT NULL,
    amount           numeric(15, 2) NOT NULL,       -- Approved purchases only
    transactions     integer NOT NULL,
    PRIMARY KEY (customer_id, month, category, currency)
);
```

Totals, ticket size and "spend vs previous period" come from `core.transactions` with one query. The console's `internal.history` comes from `core.call_center_interactions` + `core.complaints` (already in serving): date, `reason_category`, status. Never show their text.

### 5.3 `ops`: the data `/consola/gerencia` will really show

The dashboard KPIs (conversations, % resolved by Quipu, first-response time, CSAT, topics, handoffs) are about **our agent**, so they can only come from what the agent writes. Today the chats live in process memory. Minimum change to `ops`:

```sql
ALTER TABLE ops.conversations
    ADD COLUMN customer_id     text,
    ADD COLUMN topic           text,          -- skill that handled it: balance_inquiry, charge_investigation, data_lookup, handoff, out_of_scope
    ADD COLUMN status          text NOT NULL DEFAULT 'open',   -- open | resolved | handed_off
    ADD COLUMN ended_at        timestamptz,
    ADD COLUMN first_reply_ms  integer;       -- latency of the first agent reply

-- The thumbs / 1-5 rating under a reply (Jhonatan's KPI idea).
CREATE TABLE IF NOT EXISTS ops.feedback (
    feedback_id      bigserial PRIMARY KEY,
    conversation_id  uuid NOT NULL REFERENCES ops.conversations,
    message_id       bigint REFERENCES ops.messages,
    score            smallint NOT NULL CHECK (score BETWEEN 1 AND 5),
    comment          text,
    created_at       timestamptz NOT NULL DEFAULT now()
);
```

`ops.messages` and `ops.handoff_cases` already exist. A view `ops.v_daily_summary` (day, topic, conversations, resolved, handed off, median first reply, avg score) feeds `GET /api/ops/summary`. Eval runs can write through the same tables, tagged with `channel = 'eval'`, to populate it before the demo.

### 5.4 `gold` (Parquet, DuckDB): the "before Quipu" baseline

One small table built from the organizer data, shown next to our KPIs:

```
gold/service_baseline.parquet
  reason_category, channel, contacts, fcr_pct, followup_pct, avg_duration_s, avg_wait_s, avg_csat (1-4)
```

| Baseline (all contacts) | Value |
|---|---|
| Contacts | 686k (Phone 85%) |
| Reason mix | Transaccional 35%, Producto 22%, Queja 17%, Técnico 15%, Comercial 8%, Retención 3% |
| First-contact resolution | 76.6% (Queja 44%) |
| Avg wait | 120 s |
| Avg handle time | 221 s (Transaccional) to 540 s (Comercial) |
| CSAT | 2.77 of 4 |

The reason mix tells us which skills matter: **Transaccional + Producto = 57% of contacts**, which is balances, movements, cards and products. That's the case for Cristian's fixed-query MCPs for balance and latest card movements.

## 6. Next steps

1. `make silver SOURCE=full` → `_quality_report.json` (expect 0 duplicates, country normalization, orphans).
2. Build `gold/service_baseline.parquet` and `core.customer_spend_monthly` (silver → load).
3. Persist `ops.conversations` / `ops.feedback` from the API, then replace the mock in `web/lib/ops.ts`.
4. Remove `call_transcripts` from serving and from the `data_lookup` allowlist (`app/domain/sql_scope.py`).
