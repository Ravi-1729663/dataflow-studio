from pathlib import Path

import pandas as pd
from django.conf import settings

from apps.common.exceptions import ConnectorError

from .base import Connector


class FileConnector(Connector):
    """Reads a delimited file (CSV) from disk, relative to BASE_DIR if not absolute."""

    def _resolve_path(self) -> Path:
        raw_path = self.config.get("path")
        if not raw_path:
            raise ConnectorError("file connector config requires a 'path'")
        path = Path(raw_path)
        return path if path.is_absolute() else Path(settings.BASE_DIR) / path

    def test_connection(self) -> None:
        path = self._resolve_path()
        if not path.exists():
            raise ConnectorError(f"file not found: {path}")

    def extract(self) -> pd.DataFrame:
        path = self._resolve_path()
        try:
            return pd.read_csv(path)
        except (
            FileNotFoundError,
            pd.errors.EmptyDataError,
            pd.errors.ParserError,
        ) as exc:
            raise ConnectorError(f"could not read file {path}: {exc}") from exc
