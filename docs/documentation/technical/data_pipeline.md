# Data Pipeline

How the organizer's CSV files become the agent's operational store. The same code runs on the committed mini-set (local, every teammate) and on the full dataset (Cloud SQL).

## Quick start

```bash
make up                      # local: Postgres + seed (mini-set -> silver -> Postgres) + agent API/web
make down                    # stop (make down V=1 also deletes the database volume)
make etl-cloud CONFIRM=yes   # Cloud SQL: raw CSV -> bronze -> silver -> core, full dataset (needs make db-proxy)
```

Local needs no S3 credentials: the mini-set is committed under `data/sample/`. The cloud ETL reads the CSV files in `data/raw/` (`make data-lite`).

| Environment | Data | Command |
|---|---|---|
| Local Postgres (tests, development) | mini-set of 1,500 customers + 8 team demo customers | `make demo-data` (or `make up`) |
| Cloud SQL (the deployed agent) | everything in `data/raw`: 150,000 customers, 400,000 products, 1,057,918 transactions (2025-10-01 to 2026-06-18) + the same 8 demo customers | `make etl-cloud CONFIRM=yes` |

## Layers

```mermaid
flowchart LR
    S3[("S3: organizer CSV<br/>hive partitions")] -->|download.py| RAW["raw<br/>data/raw/"]
    RAW -->|bronze.py| BRONZE["bronze<br/>1 Parquet / table, as-is<br/>+ source filename"]
    BRONZE -->|sample.py| SAMPLE["sample (committed)<br/>data/sample/"]
    FIX["fixtures.py<br/>team demo scenarios"] --> SAMPLE
    SAMPLE -->|silver.py --source sample| SILVER["silver<br/>dedup, normalization,<br/>orphans, contracts"]
    BRONZE -->|silver.py --source full| SILVER
    SILVER -->|load.py| PG[("Postgres core<br/>+ ops written by the agent")]
    SILVER --> DUCK["DuckDB analytics<br/>EDA, eval, metrics"]
```

| Layer | Script | What it does |
|---|---|---|
| raw | `python -m data_pipeline.download` | Resumable S3 download that keeps the `year=/month=/day=` partitions |
| bronze | `python -m data_pipeline.bronze` | CSV → one Parquet per table. `union_by_name` absorbs schema evolution; the source `filename` is kept for lineage |
| sample | `python -m data_pipeline.sample` | Deterministic, referentially closed mini-set (see [11_data_model.md](../../strategy_analysis_01/11_data_model.md)) |
| fixtures | `python -m data_pipeline.fixtures` | 8 team-made demo customers, labeled `is_synthetic_fixture` |
| silver | `python -m data_pipeline.silver --source sample\|full` | Deduplicates by primary key (latest `last_updated`), normalizes country names, completes `transaction_category` from the merchant, drops rows whose customer doesn't exist, counts soft-FK orphans and source anomalies, validates pandera contracts, and writes `_quality_report.json` |
| serving | `python -m data_pipeline.load --source sample\|full` | Builds `core` from `schema.sql` as `core_staging`, bulk-loads silver + fixtures, generates `core.billing`, checks that every row arrived, then swaps it in for `core` in one transaction. `ops` is never touched. Idempotent |

`--source` in the load must match what silver was built from, so a stale `data/silver/` never puts the mini-set where the full dataset was meant. A load that fails halfway leaves the `core` the agent is reading untouched.

## What is in `core`, and where it comes from

The brief asks to label every input. Each table carries its provenance as a `COMMENT ON TABLE` in `schema.sql`, and the load copies those labels into the quality report.

| Table | Rows are | Provenance |
|---|---|---|
| `customers`, `products`, `transactions`, `fx_rates`, `complaints` | the organizer's rows, only the columns the agent may use | organizer dataset (itself synthetic) |
| `app_sessions` | one row per app/web session | derived from the organizer's `digital_events` |
| `customer_service_summary` | one row per customer: contacts, escalations, open complaints, last CSAT | derived from the organizer's interactions, complaints and surveys |
| `billing` | one row per credit card and loan: statement date, due date, statement balance, minimum payment or installment, past-due amount | **team-generated** by a fixed rule (below) |
| rows with `is_synthetic_fixture = true` | the 8 demo customers and their dispute scenarios | **team-generated** (`fixtures.py`) |

Not loaded: `call_transcripts`, `call_center_interactions` and `satisfaction_surveys`. Their text is templates (every transcript still has `{monto}` placeholders) and the survey scores do not follow their own scales, so the agent only gets what the summary aggregates from them. `service_agents` and `branches` are not loaded either: no question uses them.

**The billing rule.** The dataset has balances, rates and `days_past_due`, but no due dates, statements or installments. `load.py` derives them, as of the dataset's last day (2026-06-18), from a stable hash of the product id, so the same product always gets the same figures:

- a product that is past due was due exactly `days_past_due` days ago; any other is due 1 to 20 days ahead;
- the statement closes 20 days before the due date;
- a card's statement is its whole balance when past due, otherwise 70-100% of it; its minimum is 5% of the statement with a floor per currency, plus what is past due, never more than the statement;
- a loan's installment is the level payment for its balance, annual rate and remaining installments (6-60 personal, 60-360 mortgage).

The load refuses to run if a past-due product's due date disagrees with its `days_past_due`. The tools return these figures with `billing_provenance: team_generated` and the agent states them as illustrative.

## Data contracts and quality

- **Contracts** (pandera, in `silver.py`):
  - primary keys unique and not null;
  - closed vocabularies for the columns the tools branch on (`transaction_status`, `currency`).
- **Quality report:** `data/silver/_quality_report.json` records, per table, the input rows, dropped duplicates, dropped customer orphans, soft-FK orphans, counted anomalies and output rows; the load adds the target host, the rows that arrived in each `core` table and their provenance. It is the lineage evidence for each run. `make etl-cloud` copies the full-dataset report to `quality_report_full.json` in this folder.
- **Known source issues:**
  - "Mexico" vs "México" in `transaction_country` (normalized);
  - `transaction_category` empty on purchases whose merchant has one (completed);
  - `customers.registration_branch_id` almost never matches `branches`;
  - products opened before their customer registered, balances over the limit, movements after the product expired (counted in the report, not fixed);
  - no MXN products: Mexican customers hold USD;
  - amounts are always positive (the type gives the direction) and balances do not reconcile with movements;
  - text fields are templates;
  - row counts are below the data dictionary, and the duplicates it announces are not in the files.

## Freshness and late arrivals (full ETL)

The source is partitioned daily by `process_date` and can arrive late.

- **Incremental rule:** reprocess the last *N* days of partitions on every run (N = 7 by default). Silver keeps one row per key by latest `last_updated`, so a late or corrected row replaces the earlier one.
- **Freshness target:** serving data at most 24 h behind the source. Document it as a policy; the hackathon data is static.
- **Update correctness:** because the supplied data is static, it is demonstrated with a labeled fixture that adds a late partition and a corrected row, then checks that silver keeps the new version. This is still to do.

## Running it as a scheduled job (not built)

Today the full ETL runs from a laptop through the Cloud SQL proxy (`make etl-cloud`). To schedule it:

| Now | Scheduled |
|---|---|
| `data/raw`, `data/bronze` on disk | GCS buckets `raw/`, `bronze/` (Parquet) |
| `bronze.py`, `silver.py --source full`, `load.py --source full` on a laptop | the same three commands in a Cloud Run job, triggered by Cloud Scheduler |
| database password read with `gcloud secrets` | the job's service account reads `factored-database-url` |
