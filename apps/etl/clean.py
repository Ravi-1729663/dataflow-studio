"""Cleansing step: repairs fixable data issues before validation sees them, so a pipeline can
succeed on a batch that would otherwise trip a blocking rule or silently load garbage. Pure
pandas, no Django imports.

``spec`` shape (nested under ``transform.clean`` in a pipeline's config)::

    {
        "trim": ["email", "first_name"],           # strip whitespace; "" after trim -> missing
        "lowercase": ["email"],                     # normalize case
        "fill_null": {"country": "UNKNOWN"},        # replace missing values with a default
        "drop_rows_missing": ["email"],              # drop a row outright if any of these is missing
        "min_present_fraction": 0.5,                 # drop a row with fewer than this fraction
                                                      # of its columns populated
    }

Order matters: trim/lowercase run first (so a whitespace-only cell counts as missing for
everything downstream), then fill_null, then the two drop rules. Returns the cleaned DataFrame
plus a stats dict the caller can fold into a run's metrics.
"""

import pandas as pd


def clean(df: pd.DataFrame, spec: dict) -> tuple[pd.DataFrame, dict]:
    df = df.copy()
    stats = {
        "cells_trimmed": 0,
        "cells_lowercased": 0,
        "cells_filled": 0,
        "rows_dropped": 0,
    }

    for column in spec.get("trim", []):
        if column not in df.columns:
            continue
        is_str = df[column].map(lambda v: isinstance(v, str))
        stripped = df[column].where(~is_str, df[column].str.strip())
        stats["cells_trimmed"] += int((stripped != df[column]).fillna(False).sum())
        df[column] = stripped.replace("", pd.NA)

    for column in spec.get("lowercase", []):
        if column not in df.columns:
            continue
        is_str = df[column].map(lambda v: isinstance(v, str))
        lowered = df[column].where(~is_str, df[column].str.lower())
        stats["cells_lowercased"] += int((lowered != df[column]).fillna(False).sum())
        df[column] = lowered

    for column, default in spec.get("fill_null", {}).items():
        if column not in df.columns:
            continue
        stats["cells_filled"] += int(df[column].isna().sum())
        df[column] = df[column].fillna(default)

    rows_before = len(df)

    drop_rows_missing = [
        c for c in spec.get("drop_rows_missing", []) if c in df.columns
    ]
    if drop_rows_missing:
        df = df.dropna(subset=drop_rows_missing)

    min_fraction = spec.get("min_present_fraction")
    if min_fraction is not None and len(df.columns) > 0:
        min_present = int(min_fraction * len(df.columns))
        df = df.dropna(thresh=min_present)

    stats["rows_dropped"] = rows_before - len(df)
    return df.reset_index(drop=True), stats
