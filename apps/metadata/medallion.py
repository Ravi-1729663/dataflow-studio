"""Writes bronze/silver/gold Parquet snapshots and queries them back via DuckDB.

Bronze/silver are per-run extraction/transformation batches — querying unions every run's file.
Gold is a full-table snapshot taken after each successful load, so only the most recent file is
meaningful; querying older gold files would double-count rows already superseded by a later run.

Files are Hive-style partitioned by date (``dt=YYYY-MM-DD/``) so a large dataset's history doesn't
sit as one giant flat directory, and a query engine that understands Hive partitioning (DuckDB,
Spark, ...) can prune whole days without opening every file.
"""

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
from django.conf import settings


def _dataset_dir(layer: str, dataset_name: str) -> Path:
    # Read settings.BASE_DIR fresh on every call rather than caching it at import time, so
    # per-test overrides (settings.BASE_DIR = tmp_path) are respected.
    return Path(settings.BASE_DIR) / "data" / "medallion" / layer.lower() / dataset_name


def _partition_dir(layer: str, dataset_name: str, partition_date: date) -> Path:
    path = _dataset_dir(layer, dataset_name) / f"dt={partition_date.isoformat()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_layer(
    layer: str,
    dataset_name: str,
    df: pd.DataFrame,
    run_id: str,
    partition_date: date | None = None,
) -> Path:
    directory = _partition_dir(layer, dataset_name, partition_date or date.today())
    path = directory / f"{run_id}.parquet"
    df.to_parquet(path, index=False)
    return path


def query_layer(layer: str, dataset_name: str, limit: int = 100) -> list[dict]:
    """Query every Parquet file for a dataset's layer, across every date partition, via DuckDB
    (gold: latest file only)."""
    directory = _dataset_dir(layer, dataset_name)
    files = sorted(directory.rglob("*.parquet"), key=lambda p: p.stat().st_mtime)
    if not files:
        return []

    if layer.upper() == "GOLD":
        files = files[-1:]

    file_list_sql = ", ".join(f"'{f.as_posix()}'" for f in files)
    con = duckdb.connect(database=":memory:")
    try:
        result = con.execute(
            f"SELECT * FROM read_parquet([{file_list_sql}]) LIMIT {int(limit)}"
        ).fetch_df()
    finally:
        con.close()
    return result.to_dict(orient="records")
