from abc import ABC, abstractmethod

import pandas as pd


class Connector(ABC):
    """One class per DataSource.source_type. Returns pandas DataFrames, never touches the ORM."""

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def test_connection(self) -> None:
        """Raise ``apps.common.exceptions.ConnectorError`` if the source is unreachable."""

    @abstractmethod
    def extract(self) -> pd.DataFrame:
        """Return the full dataset as a DataFrame."""
