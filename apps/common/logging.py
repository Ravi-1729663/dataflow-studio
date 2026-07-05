"""Structured JSON logging formatter + correlation-id propagation.

Every logger call goes through JSONFormatter in production and dev. CorrelationIdFilter injects
the current pipeline run id (set via ``set_run_id``) into every log record automatically, so a
run's logs are correlated end-to-end even from code (apps.etl, apps.warehouse, ...) that has never
heard of a "run id" and never passes one via ``extra=``.
"""

import contextvars
import json
import logging

_run_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "run_id", default=None
)


def set_run_id(run_id: str | None) -> None:
    _run_id_var.set(run_id)


def get_run_id() -> str | None:
    return _run_id_var.get()


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        run_id = get_run_id()
        if run_id and not hasattr(record, "run_id"):
            record.run_id = run_id
        return True


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in ("args", "msg", "message") or key in payload:
                continue
            if key in logging.LogRecord("", 0, "", 0, "", (), None).__dict__:
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)
