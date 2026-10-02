"""Load silver + team fixtures into the agent's Postgres (`core` schema). Idempotent.

Recreates `core` from `schema.sql` on every run; `ops` (written by the agent) is created if
missing and never truncated. Bulk inserts go through DuckDB's postgres extension.

    python -m data_pipeline.load
"""

from pathlib import Path

import duckdb
import psycopg

from app.config import get_settings

SCHEMA = Path(__file__).resolve().parents[1] / "app/adapters/outbound/postgres/schema.sql"

CUSTOMERS = """
    SELECT customer_id, document_type, document_number, first_name, last_name, date_of_birth,
           email, mobile_phone, city, country, detected_accent, 'es' AS preferred_language,
           segment, customer_status, false AS is_synthetic_fixture
    FROM silver.customers
    UNION ALL BY NAME
    SELECT *, true AS is_synthetic_fixture FROM fixtures.customers
"""
PRODUCTS = """
    SELECT product_id, customer_id, product_type,
           right(product_number::VARCHAR, 4) AS product_number_last4,
           currency, current_balance, credit_limit, product_status, false AS is_synthetic_fixture
    FROM silver.products
    UNION ALL BY NAME
    SELECT *, true AS is_synthetic_fixture FROM fixtures.products
"""
TRANSACTIONS = """
    SELECT transaction_id, customer_id, product_id, transaction_date, transaction_type,
           transaction_category, amount, currency, amount_usd, channel, merchant_name,
           merchant_category, transaction_country, transaction_city, transaction_status,
           response_code::VARCHAR AS response_code, is_fraud, fraud_score,
           false AS is_synthetic_fixture
    FROM silver.transactions
    UNION ALL BY NAME
    SELECT *, true AS is_synthetic_fixture FROM fixtures.transactions
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
SERVICE_SUMMARY = """
    WITH it AS (
        SELECT customer_id, count(*) AS contacts, count(*) FILTER (was_escalated) AS escalated,
               max(interaction_date) AS last_at,
               arg_max(contact_reason, interaction_date) AS last_reason
        FROM silver.call_center_interactions GROUP BY 1),
    co AS (
        SELECT customer_id,
               count(*) FILTER (status IN ('Open', 'In Process', 'Escalated')) AS open_complaints,
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
INTERACTIONS = """
    SELECT interaction_id, customer_id, interaction_date, interaction_type, channel,
           contact_reason, duration_seconds::INT AS duration_seconds,
           wait_time_seconds::INT AS wait_time_seconds, was_resolved, requires_followup,
           detected_sentiment, sentiment_score, was_escalated, mentioned_products, has_transcript
    FROM silver.call_center_interactions
"""
SURVEYS = """
    SELECT survey_id, customer_id, interaction_id, survey_date, survey_type, send_channel,
           main_score, nps_category, question_1_text,
           question_1_response::INT AS question_1_response,
           question_2_text, question_2_response::INT AS question_2_response,
           question_3_text, question_3_response::INT AS question_3_response,
           open_comments, comment_sentiment
    FROM silver.satisfaction_surveys
"""
TRANSCRIPTS = """
    SELECT transcript_id, customer_id, interaction_id, full_text, customer_text, agent_text,
           detected_language, main_topics, duration_seconds::INT AS duration_seconds
    FROM silver.call_transcripts
"""
TARGETS = [  # dependency order
    ("customers", CUSTOMERS),
    ("products", PRODUCTS),
    ("transactions", TRANSACTIONS),
    ("fx_rates", FX_RATES),
    ("app_sessions", APP_SESSIONS),
    ("customer_service_summary", SERVICE_SUMMARY),
    ("complaints", COMPLAINTS),
    ("call_center_interactions", INTERACTIONS),
    ("satisfaction_surveys", SURVEYS),
    ("call_transcripts", TRANSCRIPTS),
]


def main() -> None:
    settings = get_settings()
    with psycopg.connect(settings.database_url, autocommit=True) as pg:
        pg.execute(SCHEMA.read_text())

    con = duckdb.connect()
    for schema, folder in [
        ("silver", settings.data_dir / "silver"),
        ("fixtures", settings.data_dir / "sample" / "fixtures"),
    ]:
        con.execute(f"CREATE SCHEMA {schema}")
        for path in sorted(folder.glob("*.parquet")):
            con.execute(f"CREATE VIEW {schema}.{path.stem} AS SELECT * FROM '{path}'")
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{settings.database_url}' AS pg (TYPE postgres)")
    for table, query in TARGETS:
        con.execute(f"INSERT INTO pg.core.{table} BY NAME ({query})")
        rows = con.execute(f"SELECT count(*) FROM pg.core.{table}").fetchone()[0]
        print(f"core.{table:26s} {rows:>9,d} rows")


if __name__ == "__main__":
    main()
