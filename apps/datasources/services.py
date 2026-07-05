"""Business logic for datasources. Bridges DataSource models to the connectors package."""

from .connectors import get_connector
from .models import DataSource


def test_connection(data_source: DataSource) -> None:
    """Raises ``apps.common.exceptions.ConnectorError`` if the source is unreachable."""
    connector = get_connector(data_source.source_type, data_source.config)
    connector.test_connection()
