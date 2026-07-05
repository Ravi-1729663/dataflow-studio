"""Writes bronze/silver/gold Parquet snapshots and queries them back via DuckDB.

Bronze/silver are per-run extraction/transformation batches — querying unions every run's file.
Gold is a full-table snapshot taken after each successful load, so only the most recent file is
meaningful; querying older gold files would double-count rows already superseded by a later run.
"""

from pathlib import Path

import duckdb
import pandas as pd
from django.conf import settings


def _layer_dir(layer: str, dataset_name: str) -> Path:
    # Read settings.BASE_DIR fresh on every call rather than caching it at import time, so
    # per-test overrides (settings.BASE_DIR = tmp_path) are respected.
    root = Path(settings.BASE_DIR) / "data" / "medallion"
    path = root / layer.lower() / dataset_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_layer(layer: str, dataset_name: str, df: pd.DataFrame, run_id: str) -> Path:
    path = _layer_dir(layer, dataset_name) / f"{run_id}.parquet"
    df.to_parquet(path, index=False)
    return path


def query_layer(layer: str, dataset_name: str, limit: int = 100) -> list[dict]:
    """Query every Parquet file for a dataset's layer via DuckDB (gold: latest file only)."""
    directory = _layer_dir(layer, dataset_name)
    files = sorted(directory.glob("*.parquet"), key=lambda p: p.stat().st_mtime)
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
