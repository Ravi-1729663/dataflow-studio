import os

from celery import Celery
from celery.signals import worker_init

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("dataflow_studio")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@worker_init.connect
def _start_metrics_server(**kwargs):
    """Pipeline execution happens in this worker process, not the web/gunicorn process — the
    custom Prometheus counters in apps.monitoring.metrics live in whichever process incremented
    them, so the worker needs its own /metrics HTTP server (a separate Prometheus scrape target)
    rather than relying on django-prometheus's endpoint, which only sees the web process's
    in-memory registry. Runs once in the main worker process (fires regardless of pool type,
    unlike worker_process_init which prefork would call once per forked child)."""
    from prometheus_client import start_http_server

    start_http_server(int(os.environ.get("CELERY_METRICS_PORT", "9808")))
