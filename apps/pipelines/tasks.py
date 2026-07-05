"""Celery entrypoint for pipeline execution: retries with exponential backoff, then a dead-letter
record if every attempt fails.

Retries are a plain in-task loop rather than Celery's ``self.retry()``: Celery only re-queues a
retry through the broker, and under ``CELERY_TASK_ALWAYS_EAGER=1`` (this project's zero-setup local
dev default) ``self.retry()`` doesn't loop at all — it raises the ``Retry`` exception straight back
to the caller. A manual loop behaves identically whether this runs on a real worker or synchronously
in eager mode.
"""

import logging
import time

from celery import shared_task
from django.conf import settings

from apps.etl.exceptions import EtlError
from apps.monitoring.tracing import extract_context, tracer

from . import services
from .models import Pipeline, PipelineRun

logger = logging.getLogger("dataflow.pipelines")

MAX_RETRIES = 3


@shared_task(name="pipelines.run_pipeline_task")
def run_pipeline_task(
    pipeline_id: str, run_id: str | None = None, trace_context: dict | None = None
) -> str:
    """``trace_context`` (from monitoring.tracing.inject_context) carries the API call's trace
    into this worker span, so a run's trace covers both processes. A cron-triggered run has no
    inbound request to carry a context from, so it just starts a fresh trace."""
    pipeline = Pipeline.objects.get(pk=pipeline_id)
    run = PipelineRun.objects.get(pk=run_id) if run_id else services.start_run(pipeline)

    with tracer.start_as_current_span(
        "pipeline.task.run_pipeline_task",
        context=extract_context(trace_context),
        attributes={"pipeline.id": pipeline_id, "run.id": str(run.id)},
    ):
        base_delay = getattr(settings, "PIPELINE_RETRY_BACKOFF_BASE_SECONDS", 2)
        attempt = 0
        while True:
            try:
                services.execute_attempt(run)
                return str(run.id)
            except EtlError:
                if attempt >= MAX_RETRIES:
                    services.mark_failed(run)
                    return str(run.id)
                attempt += 1
                services.mark_retrying(run, attempt)
                countdown = min(base_delay**attempt, 30)
                logger.warning(
                    "pipeline run retrying",
                    extra={
                        "pipeline_id": pipeline_id,
                        "run_id": str(run.id),
                        "retry_count": attempt,
                        "countdown": countdown,
                    },
                )
                if countdown:
                    time.sleep(countdown)
