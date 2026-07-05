"""Celery entrypoint for pipeline execution. Runs synchronously in-process when CELERY_TASK_ALWAYS_EAGER=1."""

from celery import shared_task

from .models import Pipeline
from .services import execute_pipeline


@shared_task(name="pipelines.run_pipeline_task")
def run_pipeline_task(pipeline_id: str) -> str:
    pipeline = Pipeline.objects.get(pk=pipeline_id)
    run = execute_pipeline(pipeline)
    return str(run.id)
