"""Incremental extraction: filters a batch down to new/changed rows against a watermark, and
computes the next watermark from what's left. Framework-agnostic — the caller (pipelines app)
persists the watermark value between runs; this module only ever sees plain DataFrames/strings.

Works source-type-agnostically: it filters client-side after extraction, so it applies uniformly
whether the row-level filter happened to be pushed down into a source query or not.
"""

import pandas as pd


def filter_incremental(
    df: pd.DataFrame, column: str, watermark: str | None, grace_seconds: float = 0
) -> pd.DataFrame:
    """Keep only rows newer than ``watermark`` on ``column``.

    ``grace_seconds`` is the late-arriving-data strategy: rows within that window *before* the
    watermark are still included, tolerating a row that arrives after its neighbours despite an
    earlier logical timestamp. Idempotent loads make the resulting overlap harmless.
    """
    if column not in df.columns or not watermark:
        return df

    parsed_values = pd.to_datetime(df[column], errors="coerce")
    parsed_watermark = pd.to_datetime(watermark, errors="coerce")
    if pd.notna(parsed_watermark) and not parsed_values.isna().all():
        effective_watermark = parsed_watermark - pd.Timedelta(seconds=grace_seconds)
        return df[parsed_values > effective_watermark].reset_index(drop=True)

    # Non-date watermark column (e.g. an auto-incrementing id): plain comparison, no grace period.
    return df[df[column].astype(str) > str(watermark)].reset_index(drop=True)


def compute_watermark(df: pd.DataFrame, column: str) -> str | None:
    """The next watermark: the max value seen on ``column`` in this batch, or None if nothing
    came through (in which case the caller should keep the previous watermark)."""
    if column not in df.columns or df.empty:
        return None
    return str(df[column].max())
