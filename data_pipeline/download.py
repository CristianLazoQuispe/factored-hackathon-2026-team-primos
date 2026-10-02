"""Download the LATAM Bank dataset from S3 into `data/raw/`, keeping hive partitions.

Resumable: files already on disk with the same size are skipped.

    python -m data_pipeline.download                       # all tables (~5.4 GB)
    python -m data_pipeline.download --skip digital_events # ~1.6 GB
    python -m data_pipeline.download --tables customers complaints
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
from botocore.config import Config

from app.config import get_settings


def table_of(key: str, prefix: str) -> str:
    name = key.removeprefix(prefix).split("/", 1)[0]
    return name.removesuffix(".csv")


def list_objects(client, bucket: str, prefix: str) -> list[dict]:
    pages = client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
    return [obj for page in pages for obj in page.get("Contents", [])]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tables", nargs="*", help="only these tables")
    parser.add_argument("--skip", nargs="*", default=[], help="tables to skip")
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    settings = get_settings()
    client = boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_default_region,
        config=Config(max_pool_connections=args.workers),
    )
    prefix = settings.s3_prefix
    raw_dir = settings.data_dir / "raw"

    objects = [
        obj
        for obj in list_objects(client, settings.s3_bucket, prefix)
        if (not args.tables or table_of(obj["Key"], prefix) in args.tables)
        and table_of(obj["Key"], prefix) not in args.skip
    ]
    pending = []
    for obj in objects:
        target = raw_dir / obj["Key"].removeprefix(prefix)
        if not (target.exists() and target.stat().st_size == obj["Size"]):
            pending.append((obj["Key"], target))

    total_gb = sum(obj["Size"] for obj in objects) / 1e9
    print(f"{len(objects)} files ({total_gb:.2f} GB) selected, {len(pending)} to download")

    def fetch(key: str, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        client.download_file(settings.s3_bucket, key, str(target))

    with ThreadPoolExecutor(args.workers) as pool:
        futures = [pool.submit(fetch, key, target) for key, target in pending]
        for done, future in enumerate(as_completed(futures), 1):
            future.result()
            if done % 200 == 0 or done == len(futures):
                print(f"  {done}/{len(futures)}")


if __name__ == "__main__":
    main()
