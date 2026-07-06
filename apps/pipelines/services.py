"""Bridges Pipeline/PipelineRun models to the framework-agnostic etl engine. The only such bridge."""

import logging
import traceback as traceback_module
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from opentelemetry.trace import Status, StatusCode

from apps.common.logging import set_run_id
from apps.etl import engine
from apps.etl.exceptions import EtlError, ValidationFailed
from apps.metadata.services import record_ingest
from apps.monitoring import metrics
from apps.monitoring.tracing import tracer
from apps.notifications.models import NotificationLog
from apps.notifications.services import notify
from apps.validation.services import persist_scorecard

from .loaders import get_loader
from .models import DeadLetterRecord, Pipeline, PipelineRun, PipelineWatermark

logger = logging.getLogger("dataflow.pipelines")


def _build_extract_spec(pipeline: Pipeline) -> dict:
    """Resolve the DataSource's config into a plain extract spec, absolute-pathing file sources
    against BASE_DIR here — the etl engine itself never knows about Django settings."""
    source = pipeline.source
    spec = {"type": source.source_type.lower(), **source.config}
    if spec["type"] == "file":
        path = Path(spec["path"])
        if not path.is_absolute():
            spec["path"] = str(Path(settings.BASE_DIR) / path)
    return spec


def _build_incremental_spec(pipeline: Pipeline) -> dict | None:
    """``pipeline.config["incremental"]`` opts a pipeline into watermark tracking:
    ``{"column": "updated_at", "initial_value": "...", "grace_seconds": 0}``. The current
    watermark is read from PipelineWatermark (or the configured initial value on the very first
    run) and handed to the engine; ``execute_attempt`` persists whatever the engine computes back
    once the run succeeds."""
    config = pipeline.config.get("incremental")
    if not config or not config.get("column"):
        return None
    watermark = (
        PipelineWatermark.objects.filter(pipeline=pipeline)
        .values_list("value", flat=True)
        .first()
    )
    return {
        "column": config["column"],
        "watermark": watermark or config.get("initial_value"),
        "grace_seconds": config.get("grace_seconds", 0),
    }


def start_run(pipeline: Pipeline) -> PipelineRun:
    """Create a fresh PipelineRun row. Reused across retries of the same logical run — a Celery
    retry re-executes the whole task, so the run row is looked up rather than recreated.
    """
    run = PipelineRun.objects.create(
        pipeline=pipeline, status=PipelineRun.Status.RUNNING, started_at=timezone.now()
    )
    logger.info(
        "pipeline run started", extra={"pipeline_id": pipeline.id, "run_id": run.id}
    )
    return run


def execute_attempt(run: PipelineRun) -> PipelineRun:
    """Run one attempt of the etl engine against an existing PipelineRun row.

    Raises the etl engine's ``EtlError`` on failure so the caller (a Celery task with retry +
    backoff, or ``execute_pipeline`` below) decides whether to retry or give up. Every log line
    emitted while this run is executing — including from code that has never heard of a "run id",
    like apps.warehouse — is automatically tagged with this run's id (see
    apps.common.logging.CorrelationIdFilter), and the whole attempt is one OpenTelemetry span so
    a failure's exact step is visible in both the trace and the logs.
    """
    pipeline = run.pipeline
    target = pipeline.config.get("target", "customers")
    loader = get_loader(target)

    run.status = PipelineRun.Status.RUNNING
    run.save(update_fields=["status", "updated_at"])

    set_run_id(str(run.id))
    try:
        with tracer.start_as_current_span(
            "pipeline.execute_attempt",
            attributes={"pipeline.id": str(pipeline.id), "run.id": str(run.id)},
        ) as span:
            try:
                result = engine.run(
                    extract_spec=_build_extract_spec(pipeline),
                    validation_spec=pipeline.config.get("validation", {}),
                    transform_spec=pipeline.config.get("transform", {}),
                    loader=loader,
                    incremental_spec=_build_incremental_spec(pipeline),
                )
            except ValidationFailed as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                run.error = str(exc)
                run.traceback = traceback_module.format_exc()
                run.save(update_fields=["error", "traceback", "updated_at"])
                if exc.outcome is not None:
                    persist_scorecard(run, exc.outcome)
                logger.warning(
                    "pipeline run blocked by validation",
                    extra={
                        "pipeline_id": pipeline.id,
                        "run_id": run.id,
                        "error": str(exc),
                    },
                )
                raise
            except EtlError as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                run.error = str(exc)
                run.traceback = traceback_module.format_exc()
                run.save(update_fields=["error", "traceback", "updated_at"])
                logger.warning(
                    "pipeline run attempt failed",
                    extra={
                        "pipeline_id": pipeline.id,
                        "run_id": run.id,
                        "error": str(exc),
                    },
                )
                raise

            run.status = PipelineRun.Status.SUCCEEDED
            run.metrics = {
                "rows_extracted": result.rows_extracted,
                "rows_loaded": result.rows_loaded,
                "duration_seconds": result.duration_seconds,
                **result.load_result,
            }
            run.logs = result.step_logs
            run.finished_at = timezone.now()
            run.save(
                update_fields=["status", "metrics", "logs", "finished_at", "updated_at"]
            )
            span.set_attribute("rows_loaded", result.rows_loaded)

            if result.validation is not None:
                persist_scorecard(run, result.validation)
            if result.new_watermark is not None:
                PipelineWatermark.objects.update_or_create(
                    pipeline=pipeline, defaults={"value": result.new_watermark}
                )
            record_ingest(pipeline, run, result.raw_df, result.transformed_df)
            metrics.record_run_succeeded(result.duration_seconds, result.rows_loaded)
            notify(NotificationLog.Event.RUN_SUCCEEDED, run)
            logger.info(
                "pipeline run succeeded",
                extra={
                    "pipeline_id": pipeline.id,
                    "run_id": run.id,
                    "metrics": run.metrics,
                },
            )
            return run
    finally:
        set_run_id(None)


def mark_retrying(run: PipelineRun, retry_count: int) -> PipelineRun:
    run.status = PipelineRun.Status.RETRYING
    run.retry_count = retry_count
    run.save(update_fields=["status", "retry_count", "updated_at"])
    metrics.record_run_retrying()
    notify(NotificationLog.Event.RUN_RETRYING, run)
    return run


def mark_failed(run: PipelineRun) -> PipelineRun:
    """Finalize a run as FAILED and file it in the dead-letter queue for ops visibility."""
    run.status = PipelineRun.Status.FAILED
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "finished_at", "updated_at"])
    metrics.record_run_failed()
    notify(NotificationLog.Event.RUN_FAILED, run)
    DeadLetterRecord.objects.get_or_create(
        run=run, defaults={"error": run.error, "traceback": run.traceback}
    )
    logger.error(
        "pipeline run exhausted retries, moved to dead-letter queue",
        extra={
            "pipeline_id": run.pipeline_id,
            "run_id": run.id,
            "retry_count": run.retry_count,
        },
    )
    return run


def execute_pipeline(pipeline: Pipeline) -> PipelineRun:
    """Single synchronous attempt, no retries — used by seed_demo and other direct/manual callers
    outside of Celery. Async execution with retries + a dead-letter queue goes through
    tasks.run_pipeline_task."""
    run = start_run(pipeline)
    try:
        execute_attempt(run)
    except EtlError:
        mark_failed(run)
    return run
