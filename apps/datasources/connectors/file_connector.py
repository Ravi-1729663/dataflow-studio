from pathlib import Path

import pandas as pd
from django.conf import settings

from apps.common.exceptions import ConnectorError
from apps.etl.exceptions import ExtractError
from apps.etl.extract import extract as etl_extract

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
        """Delegates to apps.etl.extract, which owns the actual (framework-agnostic) read
        logic — this class only adds the Django-settings-aware path resolution above."""
        try:
            return etl_extract(
                "file", {**self.config, "path": str(self._resolve_path())}
            )
        except ExtractError as exc:
            raise ConnectorError(str(exc)) from exc
