"""Load silver + team fixtures into the agent's Postgres (`core` schema). Idempotent.

The last step of the ETL (raw CSV -> bronze -> silver -> Postgres). `core` is rebuilt from
`schema.sql` as `core_staging` and swapped in at the end in one transaction, so a load that fails
halfway leaves the `core` the agent is reading untouched. `ops` (written by the agent) is created
if missing and never truncated. Bulk inserts go through DuckDB's postgres extension.

`--source` must match what silver was built from, so a stale `data/silver/` never puts the sample
where the full dataset was meant (or the other way round). The row counts and the provenance of
every table are appended to `data/silver/_quality_report.json`.

`core.billing` is generated here (the organizer's data has no due dates or statements): one row
per credit card and loan, by a fixed rule over the product's balance, rate and days past due.

    python -m data_pipeline.load --source sample
"""

import argparse
import json
import re
from pathlib import Path

import duckdb
import psycopg

from app.config import database_host, get_settings
from app.domain.spending import OPEN_STATUSES, STALE_AFTER_DAYS
from data_pipeline.fixtures import NOW

SCHEMA = Path(__file__).resolve().parents[1] / "app/adapters/outbound/postgres/schema.sql"
STAGING = "core_staging"
SWAP = f"DROP SCHEMA IF EXISTS core CASCADE; ALTER SCHEMA {STAGING} RENAME TO core;"
AS_OF = NOW.date()  # the dataset's last day: billing is stated as of it

CUSTOMERS = """
    SELECT customer_id, document_type, document_number, first_name, last_name, date_of_birth,
           email, mobile_phone, city, country, detected_accent, 'es' AS preferred_language,
           segment, customer_status, registration_date::DATE AS registration_date,
           false AS is_synthetic_fixture
    FROM silver.customers
    UNION ALL BY NAME
    SELECT *, true AS is_synthetic_fixture FROM fixtures.customers
"""
PRODUCTS = """
    SELECT product_id, customer_id, product_type,
           right(product_number::VARCHAR, 4) AS product_number_last4,
           currency, current_balance, credit_limit, product_status,
           nullif(interest_rate, 0) AS interest_rate, opening_date, expiration_date,
           days_past_due::INT AS days_past_due, false AS is_synthetic_fixture
    FROM silver.products
    UNION ALL BY NAME
    SELECT *, true AS is_synthetic_fixture FROM fixtures.products
"""
TRANSACTIONS = """
    SELECT transaction_id, customer_id, product_id, transaction_date, transaction_type,
           transaction_category, amount, currency, amount_usd, channel, merchant_name,
           transaction_country, transaction_city, transaction_status,
           response_code::VARCHAR AS response_code, is_fraud, fraud_score,
           false AS is_synthetic_fixture
    FROM silver.transactions
    UNION ALL BY NAME
    SELECT *, true AS is_synthetic_fixture FROM fixtures.transactions
"""
# Reads `core_products` (the PRODUCTS query as a view), so the rule runs without Postgres.
# `h` is a stable hash of the product: the same product always gets the same dates.
#   due_date           past due: as_of - days_past_due. Otherwise 1 to 20 days after as_of.
#   statement_date     20 days before due_date.
#   statement_balance  cards. Past due: the whole balance. Otherwise 70-100% of it.
#   minimum_payment    cards: 5% of the statement, not under a floor per currency, plus what is
#                      past due, never over the statement. Loans: the level installment for the
#                      balance, the annual rate and the remaining installments.
#   past_due_amount    one minimum / installment per 30 days past due, never over the debt.
BILLING = f"""
    WITH p AS (
        SELECT product_id, customer_id, current_balance AS balance,
               product_type = 'Tarjeta Crédito' AS is_card,
               coalesce(days_past_due, 0)::INT AS dpd, interest_rate / 1200 AS r,
               md5_number_lower(product_id) AS h,
               CASE currency WHEN 'USD' THEN 25 WHEN 'MXN' THEN 500 WHEN 'COP' THEN 100000
                             WHEN 'ARS' THEN 25000 ELSE 0 END AS floor,
               product_type
        FROM core_products
        WHERE product_type IN ('Tarjeta Crédito', 'Préstamo Personal', 'Préstamo Hipotecario')
          AND current_balance IS NOT NULL AND product_status <> 'Closed'),
    d AS (
        SELECT *, ceil(dpd / 30.0)::INT AS missed,
               CASE WHEN dpd > 0 THEN DATE '{AS_OF}' - dpd
                    ELSE DATE '{AS_OF}' + 1 + (h % 20)::INT END AS due_date,
               CASE WHEN NOT is_card THEN NULL WHEN dpd > 0 THEN balance
                    ELSE round(balance * (70 + (h // 20) % 31) / 100, 2) END AS statement,
               CASE product_type WHEN 'Préstamo Personal' THEN 6 + ((h // 20) % 55)::INT
                                 WHEN 'Préstamo Hipotecario' THEN 60 + ((h // 20) % 301)::INT
               END AS installments
        FROM p),
    b AS (
        SELECT *, CASE WHEN is_card THEN least(statement, greatest(0.05 * statement, floor))
                       WHEN r IS NULL THEN balance / installments
                       ELSE balance * r / (1 - power(1 + r, -installments)) END AS base
        FROM d)
    SELECT product_id, customer_id, DATE '{AS_OF}' AS as_of, due_date - 20 AS statement_date,
           due_date, statement AS statement_balance,
           round(CASE WHEN is_card THEN least(statement, base * (1 + missed)) ELSE base END, 2)
               AS minimum_payment,
           round(least(coalesce(statement, balance), base * missed), 2) AS past_due_amount,
           installments AS remaining_installments
    FROM b
"""
FX_RATES = """
    SELECT date, source_currency, target_currency, exchange_rate, buy_rate, sell_rate
    FROM silver.daily_exchange_rates
"""
APP_SESSIONS = """
    SELECT session_id, any_value(customer_id) AS customer_id, min(event_date) AS started_at,
           max(event_date) AS ended_at, any_value(channel) AS channel,
           any_value(platform) AS platform,
           any_value(ip_country) AS ip_country, any_value(ip_city) AS ip_city,
           bool_or(event_type = 'Login') AS had_login, count(*)::INT AS events,
           false AS is_synthetic_fixture
    FROM silver.digital_events WHERE customer_id IS NOT NULL GROUP BY session_id
    UNION ALL BY NAME
    SELECT *, true AS is_synthetic_fixture FROM fixtures.app_sessions
"""
SERVICE_SUMMARY = f"""
    WITH it AS (
        SELECT customer_id, count(*) AS contacts, count(*) FILTER (was_escalated) AS escalated,
               max(interaction_date) AS last_at,
               arg_max(contact_reason, interaction_date) AS last_reason
        FROM silver.call_center_interactions GROUP BY 1),
    co AS (
        SELECT customer_id,
               count(*) FILTER (status IN {OPEN_STATUSES} AND creation_date
                                >= TIMESTAMP '{AS_OF}' - INTERVAL {STALE_AFTER_DAYS} DAY)
                   AS open_complaints,
               count(*) FILTER (subcategory = 'Cargo no reconocido') AS unrecognized,
               bool_or(is_repeat_complainer) AS repeat
        FROM silver.complaints GROUP BY 1),
    su AS (
        SELECT customer_id, arg_max(main_score, survey_date)::INT AS last_csat
        FROM silver.satisfaction_surveys WHERE survey_type = 'CSAT' GROUP BY 1)
    SELECT c.customer_id,
           coalesce(it.contacts, 0)::INT AS contacts_in_window,
           coalesce(it.escalated, 0)::INT AS escalated_contacts,
           it.last_at AS last_contact_at, it.last_reason AS last_contact_reason,
           coalesce(co.open_complaints, 0)::INT AS open_complaints,
           coalesce(co.unrecognized, 0)::INT AS unrecognized_charge_complaints,
           coalesce(co.repeat, false) AS is_repeat_complainer, su.last_csat
    FROM silver.customers c
    LEFT JOIN it USING (customer_id)
    LEFT JOIN co USING (customer_id)
    LEFT JOIN su USING (customer_id)
"""
COMPLAINTS = """
    SELECT complaint_id, customer_id, creation_date, case_type, category, subcategory,
           reception_channel, affected_product_id, description, claimed_amount, currency,
           priority, status, first_response_date, resolution_date, closing_date, sla_breached,
           resolution_days::INT AS resolution_days, resolution, compensation_granted,
           resolution_satisfaction::INT AS resolution_satisfaction, is_repeat_complainer
    FROM silver.complaints
"""
TARGETS = [  # dependency order
    ("customers", CUSTOMERS),
    ("products", "SELECT * FROM core_products"),
    ("transactions", TRANSACTIONS),
    ("billing", BILLING),
    ("fx_rates", FX_RATES),
    ("app_sessions", APP_SESSIONS),
    ("customer_service_summary", SERVICE_SUMMARY),
    ("complaints", COMPLAINTS),
]
PROVENANCE = f"""
    SELECT c.relname, obj_description(c.oid) FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = '{STAGING}' AND c.relkind = 'r'
"""
# What ties billing to the organizer's data: a past-due product is overdue by exactly its days.
BILLING_DISAGREES = """
    SELECT count(*) FROM core_billing b JOIN core_products p USING (product_id)
    WHERE p.days_past_due > 0 AND b.as_of - b.due_date <> p.days_past_due
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", choices=["sample", "full"], default="sample")
    args = parser.parse_args()

    settings = get_settings()
    report_path = settings.data_dir / "silver" / "_quality_report.json"
    report = json.loads(report_path.read_text())
    if report["source"] != args.source:
        raise SystemExit(
            f"data/silver was built from {report['source']!r}, not {args.source!r}: "
            f"run `python -m data_pipeline.silver --source {args.source}` first."
        )

    con = duckdb.connect()
    for schema, folder in [
        ("silver", settings.data_dir / "silver"),
        ("fixtures", settings.data_dir / "sample" / "fixtures"),
    ]:
        con.execute(f"CREATE SCHEMA {schema}")
        for path in sorted(folder.glob("*.parquet")):
            con.execute(f"CREATE VIEW {schema}.{path.stem} AS SELECT * FROM '{path}'")
    con.execute(f"CREATE VIEW core_products AS {PRODUCTS}")
    con.execute(f"CREATE VIEW core_billing AS {BILLING}")
    if con.execute(BILLING_DISAGREES).fetchone()[0]:
        raise SystemExit("billing disagrees with days_past_due: nothing was loaded.")

    with psycopg.connect(settings.database_url, autocommit=True) as pg:
        pg.execute(re.sub(r"\bcore\b", STAGING, SCHEMA.read_text()))
        provenance = dict(pg.execute(PROVENANCE).fetchall())
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{settings.database_url}' AS pg (TYPE postgres)")
    rows = {}
    for table, query in TARGETS:
        sent = con.execute(f"INSERT INTO pg.{STAGING}.{table} BY NAME ({query})").fetchone()[0]
        rows[table] = con.execute(f"SELECT count(*) FROM pg.{STAGING}.{table}").fetchone()[0]
        if rows[table] != sent:
            raise SystemExit(f"{table}: sent {sent} rows, {rows[table]} arrived. core is kept.")
        print(f"core.{table:26s} {rows[table]:>9,d} rows")
    con.close()

    with psycopg.connect(settings.database_url) as pg:
        pg.execute(SWAP)
    report["load"] = {
        "target_host": database_host(settings.database_url),
        "billing_as_of": str(AS_OF),
        "rows": rows,
        "provenance": provenance,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
