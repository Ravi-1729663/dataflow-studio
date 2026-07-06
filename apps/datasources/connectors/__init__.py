from apps.common.exceptions import ConnectorError

from .base import Connector
from .file_connector import FileConnector
from .postgres_connector import PostgresConnector
from .rest_api_connector import RestApiConnector

_REGISTRY = {
    "FILE": FileConnector,
    "POSTGRES": PostgresConnector,
    "REST_API": RestApiConnector,
}


def get_connector(source_type: str, config: dict) -> Connector:
    try:
        connector_cls = _REGISTRY[source_type]
    except KeyError as exc:
        raise ConnectorError(
            f"no connector registered for source_type={source_type!r}"
        ) from exc
    return connector_cls(config)


__all__ = [
    "Connector",
    "FileConnector",
    "PostgresConnector",
    "RestApiConnector",
    "get_connector",
]
