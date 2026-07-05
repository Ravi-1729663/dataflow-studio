import logging

import pytest
from rest_framework.test import APIClient

from apps.common.logging import CorrelationIdFilter, get_run_id, set_run_id


@pytest.mark.django_db
def test_health_check_is_public_and_ok():
    client = APIClient()
    response = client.get("/api/health/")
    assert response.status_code == 200
    assert response.data["status"] == "ok"
    assert response.data["checks"]["database"] == "ok"


@pytest.mark.django_db
def test_health_check_skips_broker_probe_in_eager_mode(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    client = APIClient()
    response = client.get("/api/health/")
    assert response.status_code == 200
    assert response.data["checks"]["broker"] == "skipped (eager mode)"


@pytest.mark.django_db
def test_health_check_reports_degraded_when_broker_unreachable(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = False
    settings.CELERY_BROKER_URL = "redis://localhost:1/0"
    client = APIClient()
    response = client.get("/api/health/")
    assert response.status_code == 503
    assert response.data["status"] == "degraded"


def _make_record() -> logging.LogRecord:
    return logging.LogRecord(
        "dataflow.somewhere", logging.INFO, __file__, 1, "hello", (), None
    )


def test_correlation_id_filter_injects_run_id_when_set():
    set_run_id("abc-123")
    try:
        record = _make_record()
        CorrelationIdFilter().filter(record)
        assert record.run_id == "abc-123"
    finally:
        set_run_id(None)


def test_correlation_id_filter_does_not_overwrite_an_explicit_run_id():
    set_run_id("context-run-id")
    try:
        record = _make_record()
        record.run_id = "explicit-run-id"
        CorrelationIdFilter().filter(record)
        assert record.run_id == "explicit-run-id"
    finally:
        set_run_id(None)


def test_correlation_id_filter_is_a_noop_when_nothing_is_set():
    assert get_run_id() is None
    record = _make_record()
    CorrelationIdFilter().filter(record)
    assert not hasattr(record, "run_id")
