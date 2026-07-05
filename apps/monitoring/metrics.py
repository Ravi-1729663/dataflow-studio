"""Custom Prometheus metrics for pipeline execution, exported alongside django-prometheus's
built-in HTTP metrics at /metrics."""

from prometheus_client import Counter, Histogram

pipeline_runs_total = Counter(
    "dataflow_pipeline_runs_total", "Total pipeline runs by terminal status", ["status"]
)
pipeline_run_duration_seconds = Histogram(
    "dataflow_pipeline_run_duration_seconds", "Pipeline run duration in seconds"
)
pipeline_rows_processed_total = Counter(
    "dataflow_pipeline_rows_processed_total",
    "Total rows loaded across all pipeline runs",
)
pipeline_run_retries_total = Counter(
    "dataflow_pipeline_run_retries_total",
    "Total retry attempts across all pipeline runs",
)


def record_run_succeeded(duration_seconds: float, rows_loaded: int) -> None:
    pipeline_runs_total.labels(status="SUCCEEDED").inc()
    pipeline_run_duration_seconds.observe(duration_seconds)
    pipeline_rows_processed_total.inc(rows_loaded)


def record_run_failed() -> None:
    pipeline_runs_total.labels(status="FAILED").inc()


def record_run_retrying() -> None:
    pipeline_run_retries_total.inc()
