"""Bridges Pipeline/PipelineRun models to the framework-agnostic etl engine. The only such bridge."""

import logging
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.etl import engine
from apps.etl.exceptions import EtlError

from .loaders import get_loader
from .models import Pipeline, PipelineRun

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


def execute_pipeline(pipeline: Pipeline) -> PipelineRun:
    """Run a pipeline synchronously and persist a PipelineRun with its outcome."""
    run = PipelineRun.objects.create(
        pipeline=pipeline, status=PipelineRun.Status.RUNNING, started_at=timezone.now()
    )
    logger.info(
        "pipeline run started", extra={"pipeline_id": pipeline.id, "run_id": run.id}
    )

    target = pipeline.config.get("target", "customers")
    loader = get_loader(target)

    try:
        result = engine.run(
            extract_spec=_build_extract_spec(pipeline),
            validation_spec=pipeline.config.get("validation", {}),
            transform_spec=pipeline.config.get("transform", {}),
            loader=loader,
        )
    except EtlError as exc:
        run.status = PipelineRun.Status.FAILED
        run.error = str(exc)
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at", "updated_at"])
        logger.warning(
            "pipeline run failed",
            extra={"pipeline_id": pipeline.id, "run_id": run.id, "error": str(exc)},
        )
        return run

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
