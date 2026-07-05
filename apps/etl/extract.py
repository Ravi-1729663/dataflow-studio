"""Extraction step: turns a plain source spec into a pandas DataFrame. No Django imports."""

import pandas as pd

from .exceptions import ExtractError


def extract(source_type: str, config: dict) -> pd.DataFrame:
    """Extract raw data for a source spec.

    ``source_type`` is a plain string (e.g. "file"); ``config`` is a plain dict, never an ORM
    object, so this function stays usable outside of Django entirely.
    """
    if source_type == "file":
        return _extract_file(config)
    raise ExtractError(f"Unsupported source_type: {source_type!r}")


def _extract_file(config: dict) -> pd.DataFrame:
    path = config.get("path")
    if not path:
        raise ExtractError("file source config requires a 'path'")
    try:
        return pd.read_csv(path)
    except FileNotFoundError as exc:
        raise ExtractError(f"file not found: {path}") from exc
    except pd.errors.EmptyDataError as exc:
        raise ExtractError(f"file is empty: {path}") from exc
    except pd.errors.ParserError as exc:
        raise ExtractError(f"could not parse file: {path}") from exc
