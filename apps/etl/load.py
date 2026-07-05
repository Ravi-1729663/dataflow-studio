"""Load step: hands transformed rows to a caller-supplied loader callable.

The engine never touches the ORM directly — ``loader`` is injected by the pipelines app, which is
the only place allowed to bridge Django models into the etl engine.
"""

from typing import Callable

import pandas as pd

from .exceptions import LoadError


def load(df: pd.DataFrame, loader: Callable[[list[dict]], dict]) -> dict:
    rows = df.to_dict(orient="records")
    try:
        return loader(rows)
    except Exception as exc:  # noqa: BLE001 - re-raised as a domain error with context
        raise LoadError(f"loader failed: {exc}") from exc
