import pandas as pd

from apps.common.exceptions import ConnectorError
from apps.etl.exceptions import ExtractError
from apps.etl.extract import extract as etl_extract

from .base import Connector


class PostgresConnector(Connector):
    """Runs a fixed SQL query against a Postgres source. Config: {"dsn": ..., "query": ...}.

    Incremental filtering happens client-side at the engine level (apps.etl.incremental) rather
    than being pushed down into the query, so it applies uniformly across every source type.
    """

    def test_connection(self) -> None:
        dsn = self.config.get("dsn")
        if not dsn:
            raise ConnectorError("postgres connector config requires a 'dsn'")
        try:
            import psycopg2
        except (
            ImportError
        ) as exc:  # pragma: no cover - psycopg2-binary is a project dependency
            raise ConnectorError("psycopg2 is required for postgres sources") from exc
        try:
            with psycopg2.connect(dsn):
                pass
        except psycopg2.Error as exc:
            raise ConnectorError(f"could not connect to {dsn}: {exc}") from exc

    def extract(self) -> pd.DataFrame:
        try:
            return etl_extract("postgres", self.config)
        except ExtractError as exc:
            raise ConnectorError(str(exc)) from exc
