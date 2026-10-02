"""Clean bronze-shaped Parquet into `data/silver/`: dedup, orphan handling, data contracts.

Runs the same way on the committed sample (`--source sample`, reads `data/sample/`) and on the
full dataset (`--source full`, reads `data/bronze/`). Writes one Parquet per table plus
`_quality_report.json` with row counts, dropped duplicates and dropped orphans per table
(lineage for the data-quality story).

Rules:
- Primary key: keep one row per key (latest `last_updated` when the table has it).
- Foreign key to customers: rows whose customer does not exist are dropped and counted.
  Other FKs (agents, branches, products) are only counted: they are known synthetic orphans
  and do not block the agent.
- Country names: the source mixes "Mexico" and "México"; silver normalizes to the customer
  spelling ("México").
- Contracts (pandera): key not null and unique, and closed vocabularies for the columns the
  agent's tools branch on.

    python -m data_pipeline.silver --source sample
"""

import argparse
import json
from pathlib import Path

import duckdb
import pandera.polars as pa

from app.config import get_settings

PRIMARY_KEYS = {
    "customers": "customer_id",
    "products": "product_id",
    "transactions": "transaction_id",
    "digital_events": "event_id",
    "call_center_interactions": "interaction_id",
    "call_transcripts": "transcript_id",
    "complaints": "complaint_id",
    "satisfaction_surveys": "survey_id",
    "service_agents": "agent_id",
    "branches": "branch_id",
    "daily_exchange_rates": None,  # composite key, deduplicated on all key columns below
}
FX_KEY = ("date", "source_currency", "target_currency")
CUSTOMER_FK_TABLES = [
    "products",
    "transactions",
    "digital_events",
    "call_center_interactions",
    "call_transcripts",
    "complaints",
    "satisfaction_surveys",
]
SOFT_FKS = [  # (table, column, parent table, parent key)
    ("transactions", "product_id", "products", "product_id"),
    ("call_center_interactions", "agent_id", "service_agents", "agent_id"),
    ("complaints", "assigned_agent_id", "service_agents", "agent_id"),
    ("customers", "registration_branch_id", "branches", "branch_id"),
]
CONTRACTS = {
    "transactions": pa.DataFrameSchema(
        {
            "transaction_id": pa.Column(str, unique=True, nullable=False),
            "customer_id": pa.Column(str, nullable=False),
            "amount": pa.Column(float, nullable=False),
            "currency": pa.Column(str, pa.Check.isin(["MXN", "COP", "ARS", "USD"])),
            "transaction_status": pa.Column(
                str, pa.Check.isin(["Approved", "Declined", "Pending", "Reversed"])
            ),
        }
    ),
    "customers": pa.DataFrameSchema(
        {
            "customer_id": pa.Column(str, unique=True, nullable=False),
            "country": pa.Column(str, nullable=False),
        }
    ),
    "products": pa.DataFrameSchema(
        {
            "product_id": pa.Column(str, unique=True, nullable=False),
            "customer_id": pa.Column(str, nullable=False),
        }
    ),
}


def dedup_sql(table: str, source: str, columns: list[str]) -> str:
    if table == "daily_exchange_rates":
        return f"SELECT DISTINCT ON ({', '.join(FX_KEY)}) * FROM {source}"
    order = "ORDER BY last_updated DESC" if "last_updated" in columns else ""
    key = PRIMARY_KEYS[table]
    return f"SELECT * FROM {source} QUALIFY row_number() OVER (PARTITION BY {key} {order}) = 1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", choices=["sample", "full"], default="sample")
    args = parser.parse_args()

    settings = get_settings()
    src_dir = settings.data_dir / ("sample" if args.source == "sample" else "bronze")
    out_dir = settings.data_dir / "silver"
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    report: dict[str, dict] = {"source": args.source}

    tables = [t for t in PRIMARY_KEYS if (src_dir / f"{t}.parquet").exists()]
    for table in tables:
        con.execute(f"CREATE VIEW raw_{table} AS SELECT * FROM '{src_dir / table}.parquet'")
        columns = [r[0] for r in con.execute(f"DESCRIBE raw_{table}").fetchall()]
        con.execute(f"CREATE TABLE {table} AS {dedup_sql(table, f'raw_{table}', columns)}")
        raw_rows = con.execute(f"SELECT count(*) FROM raw_{table}").fetchone()[0]
        rows = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        report[table] = {"input_rows": raw_rows, "dropped_duplicates": raw_rows - rows}

    if "transactions" in tables:
        con.execute(
            "UPDATE transactions SET transaction_country = 'México' "
            "WHERE transaction_country = 'Mexico'"
        )

    for table in CUSTOMER_FK_TABLES:
        if table not in tables:
            continue
        before = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        con.execute(
            f"DELETE FROM {table} WHERE customer_id NOT IN (SELECT customer_id FROM customers)"
        )
        after = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        report[table]["dropped_customer_orphans"] = before - after

    for table, column, parent, key in SOFT_FKS:
        if table in tables and parent in tables:
            orphans = con.execute(
                f"""SELECT count(*) FROM {table} WHERE {column} IS NOT NULL
                    AND {column} NOT IN (SELECT {key} FROM {parent})"""
            ).fetchone()[0]
            report[table][f"orphan_{column}"] = orphans

    for table in tables:
        if table in CONTRACTS:
            CONTRACTS[table].validate(con.execute(f"SELECT * FROM {table}").pl(), lazy=True)
        target = out_dir / f"{table}.parquet"
        con.execute(f"COPY {table} TO '{target}' (FORMAT parquet, COMPRESSION zstd)")
        report[table]["output_rows"] = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        print(f"{table:26s} {json.dumps(report[table])}")

    Path(out_dir / "_quality_report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
