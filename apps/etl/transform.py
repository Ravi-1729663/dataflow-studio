"""Transform step: rename/select/cast/dedupe. Pure pandas, no Django imports.

``spec`` shape:
    {
        "rename": {"old_name": "new_name"},
        "select": ["col_a", "col_b"],
        "cast": {"col_a": "str"},
        "drop_duplicates": ["col_a"],
    }
"""

import pandas as pd

from .exceptions import TransformError


def transform(df: pd.DataFrame, spec: dict) -> pd.DataFrame:
    df = df.copy()

    rename = spec.get("rename")
    if rename:
        df = df.rename(columns=rename)

    cast = spec.get("cast")
    if cast:
        try:
            df = df.astype(cast)
        except (ValueError, TypeError) as exc:
            raise TransformError(f"could not cast columns: {cast}") from exc

    drop_duplicates = spec.get("drop_duplicates")
    if drop_duplicates:
        df = df.drop_duplicates(subset=drop_duplicates)

    select = spec.get("select")
    if select:
        missing = [c for c in select if c not in df.columns]
        if missing:
            raise TransformError(f"cannot select missing columns: {missing}")
        df = df[select]

    return df.reset_index(drop=True)
