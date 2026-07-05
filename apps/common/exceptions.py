"""Domain exceptions and the DRF exception handler that produces a consistent error envelope."""

import logging

from rest_framework.views import exception_handler

logger = logging.getLogger("dataflow.common")


class DataflowError(Exception):
    """Base class for domain errors raised by apps (as opposed to the framework-agnostic etl package)."""


class ConnectorError(DataflowError):
    """A data source connector failed to connect to or read from its source."""


class PipelineExecutionError(DataflowError):
    """A pipeline run failed while bridging models to the etl engine."""


def custom_exception_handler(exc, context):
    """Wrap every DRF error response in a consistent {"error": {...}} envelope."""
    response = exception_handler(exc, context)
    if response is None:
        logger.exception(
            "Unhandled exception",
            extra={"view": context.get("view").__class__.__name__},
        )
        return response

    detail = response.data
    response.data = {
        "error": {
            "code": response.status_code,
            "message": (
                detail.get("detail")
                if isinstance(detail, dict) and "detail" in detail
                else "Request failed"
            ),
            "details": detail,
        }
    }
    return response
