"""Build a small, referentially closed sample of the dataset into `data/sample/`.

The sample is meant to be committed so the whole team can run DuckDB and Postgres locally
without S3 access. It keeps the same raw columns as bronze (cleaning happens in silver), so the
same pipeline runs on the sample and on the full dataset.

Selection:
1. One shared time window for every fact table.
2. Customers ranked by how many tables they appear in within the window, stratified by
   country x segment, with a guaranteed minimum for the dispute scenarios the agent needs
   (pending, reversed, declined, fraud, "Cargo no reconocido" complaints, foreign currency).
3. Referential closure: every row of the selected customers in every table, plus the agents,
   branches and exchange rates those rows reference.

Deterministic: ties are broken by a seeded hash of `customer_id`.

    python -m data_pipeline.sample [--customers 1500] [--start 2026-04-01] [--end 2026-06-18]
"""

import argparse
from pathlib import Path

import duckdb

from app.config import get_settings

SEED = "factored-2026"
MIN_PER_SCENARIO = 40
FACT_DATE_COLUMNS = {
    "transactions": "transaction_date",
    "digital_events": "event_date",
    "call_center_interactions": "interaction_date",
    "complaints": "creation_date",
    "satisfaction_surveys": "survey_date",
}
SCENARIOS = [
    "has_pending",
    "has_reversed",
    "has_declined",
    "has_fraud",
    "has_unrecognized_charge",
    "has_foreign_currency",
]


def register_views(con: duckdb.DuckDBPyConnection, bronze: Path, start: str, end: str) -> None:
    for table in [
        *FACT_DATE_COLUMNS,
        "customers",
        "products",
        "service_agents",
        "branches",
        "daily_exchange_rates",
    ]:
        con.execute(f"CREATE VIEW {table}_all AS SELECT * FROM '{bronze / table}.parquet'")
    for table, column in FACT_DATE_COLUMNS.items():
        con.execute(
            f"""CREATE VIEW {table}_w AS SELECT * FROM {table}_all
                WHERE {column} >= TIMESTAMP '{start}'
                  AND {column} < TIMESTAMP '{end}' + INTERVAL 1 DAY"""
        )


def select_customers(con: duckdb.DuckDBPyConnection, n_customers: int) -> None:
    con.execute(
        f"""
        CREATE TABLE activity AS
        WITH tx AS (
            SELECT customer_id, count(*) AS n_tx,
                   bool_or(transaction_status = 'Pending') AS has_pending,
                   bool_or(transaction_status = 'Reversed') AS has_reversed,
                   bool_or(transaction_status = 'Declined') AS has_declined,
                   bool_or(is_fraud) AS has_fraud,
                   count(DISTINCT currency) > 1 AS has_foreign_currency
            FROM transactions_w GROUP BY 1),
        ev AS (SELECT customer_id, count(*) AS n_events FROM digital_events_w GROUP BY 1),
        it AS (SELECT customer_id, count(*) AS n_interactions
               FROM call_center_interactions_w GROUP BY 1),
        co AS (SELECT customer_id, count(*) AS n_complaints,
                      bool_or(subcategory = 'Cargo no reconocido') AS has_unrecognized_charge
               FROM complaints_w GROUP BY 1),
        su AS (SELECT customer_id, count(*) AS n_surveys FROM satisfaction_surveys_w GROUP BY 1)
        SELECT c.customer_id, c.country, c.segment,
               coalesce(n_tx, 0) AS n_tx, coalesce(n_events, 0) AS n_events,
               coalesce(n_interactions, 0) AS n_interactions,
               coalesce(n_complaints, 0) AS n_complaints, coalesce(n_surveys, 0) AS n_surveys,
               coalesce(has_pending, false) AS has_pending,
               coalesce(has_reversed, false) AS has_reversed,
               coalesce(has_declined, false) AS has_declined,
               coalesce(has_fraud, false) AS has_fraud,
               coalesce(has_unrecognized_charge, false) AS has_unrecognized_charge,
               coalesce(has_foreign_currency, false) AS has_foreign_currency,
               (n_tx > 0)::INT + (n_events > 0)::INT + (n_interactions > 0)::INT
                 + (n_complaints > 0)::INT + (n_surveys > 0)::INT AS tables_present,
               hash(c.customer_id || '{SEED}') AS tiebreak
        FROM (SELECT DISTINCT ON (customer_id) * FROM customers_all) c
        LEFT JOIN tx USING (customer_id) LEFT JOIN ev USING (customer_id)
        LEFT JOIN it USING (customer_id) LEFT JOIN co USING (customer_id)
        LEFT JOIN su USING (customer_id)
        WHERE coalesce(n_tx, 0) > 0
        """
    )
    # Guarantee: the most active customers of every dispute scenario the agent needs.
    guaranteed = " UNION ".join(
        f"""(SELECT customer_id FROM activity WHERE {flag}
             ORDER BY tables_present DESC, n_tx DESC, tiebreak LIMIT {MIN_PER_SCENARIO})"""
        for flag in SCENARIOS
    )
    con.execute(f"CREATE TABLE selected AS {guaranteed}")
    # Fill the rest proportionally to each country x segment stratum.
    con.execute(
        f"""
        INSERT INTO selected
        WITH remaining AS (
            SELECT * FROM activity WHERE customer_id NOT IN (SELECT customer_id FROM selected)),
        quota AS (
            SELECT country, segment,
                   round(count(*) * ({n_customers} - (SELECT count(*) FROM selected))
                         / sum(count(*)) OVER ())::INT AS k
            FROM remaining GROUP BY ALL),
        ranked AS (
            SELECT customer_id, country, segment,
                   row_number() OVER (PARTITION BY country, segment
                                      ORDER BY tables_present DESC, n_tx DESC, tiebreak) AS rnk
            FROM remaining)
        SELECT customer_id FROM ranked JOIN quota USING (country, segment) WHERE rnk <= k
        """
    )


def export(con: duckdb.DuckDBPyConnection, out: Path, start: str, end: str) -> dict[str, str]:
    sel = "customer_id IN (SELECT customer_id FROM selected)"
    queries = {
        "customers": f"SELECT * FROM customers_all WHERE {sel}",
        "products": f"SELECT * FROM products_all WHERE {sel}",
        **{t: f"SELECT * FROM {t}_w WHERE {sel}" for t in FACT_DATE_COLUMNS},
    }
    for name, query in queries.items():
        con.execute(f"CREATE TABLE s_{name} AS {query}")

    con.execute(
        """
        CREATE TABLE s_service_agents AS SELECT * FROM service_agents_all WHERE agent_id IN (
            SELECT agent_id FROM s_call_center_interactions
            UNION SELECT assigned_agent_id FROM s_complaints
            UNION SELECT agent_id FROM s_satisfaction_surveys)
        """
    )
    con.execute(
        """
        CREATE TABLE s_branches AS SELECT * FROM branches_all WHERE branch_id IN (
            SELECT registration_branch_id FROM s_customers
            UNION SELECT opening_branch_id FROM s_products
            UNION SELECT branch_id FROM s_transactions
            UNION SELECT related_branch_id FROM s_complaints
            UNION SELECT assigned_branch_id FROM s_service_agents)
        """
    )
    con.execute(
        f"""CREATE TABLE s_daily_exchange_rates AS SELECT * FROM daily_exchange_rates_all
            WHERE date BETWEEN DATE '{start}' AND DATE '{end}'"""
    )

    out.mkdir(parents=True, exist_ok=True)
    written = {}
    names = [*queries, "service_agents", "branches", "daily_exchange_rates"]
    for name in names:
        table = f"s_{name}"
        target = out / f"{name}.parquet"
        con.execute(
            f"COPY (SELECT * EXCLUDE (filename) FROM {table} ORDER BY ALL) TO '{target}' "
            "(FORMAT parquet, COMPRESSION zstd)"
        )
        rows = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        written[name] = f"{rows:>9,d} rows  {target.stat().st_size / 1e6:6.2f} MB"
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--customers", type=int, default=1500)
    parser.add_argument("--start", default="2026-04-01")
    parser.add_argument("--end", default="2026-06-18")
    args = parser.parse_args()

    settings = get_settings()
    con = duckdb.connect()
    register_views(con, settings.data_dir / "bronze", args.start, args.end)
    select_customers(con, args.customers)
    written = export(con, settings.data_dir / "sample", args.start, args.end)
    for name, info in sorted(written.items()):
        print(f"{name:26s} {info}")


if __name__ == "__main__":
    main()
