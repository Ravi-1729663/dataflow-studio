"""Bridges Pipeline/PipelineRun models to the framework-agnostic etl engine. The only such bridge."""

import logging
import traceback as traceback_module
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.etl import engine
from apps.etl.exceptions import EtlError

from .loaders import get_loader
from .models import DeadLetterRecord, Pipeline, PipelineRun

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
    backoff, or ``execute_pipeline`` below) decides whether to retry or give up.
    """
    pipeline = run.pipeline
    target = pipeline.config.get("target", "customers")
    loader = get_loader(target)

    run.status = PipelineRun.Status.RUNNING
    run.save(update_fields=["status", "updated_at"])

    try:
        result = engine.run(
            extract_spec=_build_extract_spec(pipeline),
            validation_spec=pipeline.config.get("validation", {}),
            transform_spec=pipeline.config.get("transform", {}),
            loader=loader,
        )
    except EtlError as exc:
        run.error = str(exc)
        run.traceback = traceback_module.format_exc()
        run.save(update_fields=["error", "traceback", "updated_at"])
        logger.warning(
            "pipeline run attempt failed",
            extra={"pipeline_id": pipeline.id, "run_id": run.id, "error": str(exc)},
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
    run.save(update_fields=["status", "metrics", "logs", "finished_at", "updated_at"])
    logger.info(
        "pipeline run succeeded",
        extra={"pipeline_id": pipeline.id, "run_id": run.id, "metrics": run.metrics},
    )
    return run


def mark_retrying(run: PipelineRun, retry_count: int) -> PipelineRun:
    run.status = PipelineRun.Status.RETRYING
    run.retry_count = retry_count
    run.save(update_fields=["status", "retry_count", "updated_at"])
    return run


def mark_failed(run: PipelineRun) -> PipelineRun:
    """Finalize a run as FAILED and file it in the dead-letter queue for ops visibility."""
    run.status = PipelineRun.Status.FAILED
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "finished_at", "updated_at"])
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
