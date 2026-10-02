"""Convert raw CSVs to one Parquet file per table in `data/bronze/`.

Bronze keeps the data as-is (no dedup, no casting beyond inference). `union_by_name`
absorbs schema evolution across daily partitions; hive columns (year/month/day) are kept.

    python -m data_pipeline.bronze [--tables customers complaints]
"""

import argparse

import duckdb

from app.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tables", nargs="*", help="only these tables")
    args = parser.parse_args()

    settings = get_settings()
    raw_dir = settings.data_dir / "raw"
    bronze_dir = settings.data_dir / "bronze"
    bronze_dir.mkdir(parents=True, exist_ok=True)

    sources = {p.stem: p for p in raw_dir.glob("*.csv")}
    sources |= {p.name: p for p in raw_dir.iterdir() if p.is_dir()}
    if args.tables:
        sources = {name: path for name, path in sources.items() if name in args.tables}

    con = duckdb.connect()
    for name, path in sorted(sources.items()):
        pattern = f"{path}/**/*.csv" if path.is_dir() else str(path)
        target = bronze_dir / f"{name}.parquet"
        con.execute(
            f"""
            COPY (
                SELECT * FROM read_csv('{pattern}', hive_partitioning = true,
                                       union_by_name = true, filename = true)
            ) TO '{target}' (FORMAT parquet, COMPRESSION zstd)
            """
        )
        rows = con.execute(f"SELECT count(*) FROM '{target}'").fetchone()[0]
        print(f"{name:30s} {rows:>12,d} rows -> {target}")


if __name__ == "__main__":
    main()
