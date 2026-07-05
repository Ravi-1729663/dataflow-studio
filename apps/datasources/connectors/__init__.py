from apps.common.exceptions import ConnectorError

from .base import Connector
from .file_connector import FileConnector

_REGISTRY = {
    "FILE": FileConnector,
}


def get_connector(source_type: str, config: dict) -> Connector:
    try:
        connector_cls = _REGISTRY[source_type]
    except KeyError as exc:
        raise ConnectorError(
            f"no connector registered for source_type={source_type!r}"
        ) from exc
    return connector_cls(config)


__all__ = ["Connector", "FileConnector", "get_connector"]
