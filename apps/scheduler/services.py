"""Bridges Pipeline.schedule (a cron string) to django-celery-beat's PeriodicTask/CrontabSchedule.

The only app that touches django_celery_beat models. Reacts to Pipeline saves via signals.py so
the pipelines app never needs to know scheduler exists — a one-directional dependency.
"""

import json
import logging

from django_celery_beat.models import CrontabSchedule, PeriodicTask

from apps.common.exceptions import DataflowError
from apps.pipelines.models import Pipeline

logger = logging.getLogger("dataflow.scheduler")

RUN_PIPELINE_TASK_NAME = "pipelines.run_pipeline_task"


class SchedulerError(DataflowError):
    """A pipeline's schedule could not be translated into a cron entry."""


def _periodic_task_name(pipeline: Pipeline) -> str:
    return f"pipeline:{pipeline.id}"


def _parse_crontab(expression: str) -> dict:
    fields = expression.split()
    if len(fields) != 5:
        raise SchedulerError(
            f"invalid cron expression {expression!r}: expected 5 space-separated fields"
        )
    minute, hour, day_of_month, month_of_year, day_of_week = fields
    return {
        "minute": minute,
        "hour": hour,
        "day_of_month": day_of_month,
        "month_of_year": month_of_year,
        "day_of_week": day_of_week,
    }


def sync_schedule(pipeline: Pipeline) -> PeriodicTask | None:
    """Create/update/remove the PeriodicTask backing a pipeline's cron schedule.

    No ``schedule`` -> no PeriodicTask. A paused pipeline (``is_active=False``) keeps its
    PeriodicTask but disabled, so resuming doesn't need to recreate anything.
    """
    name = _periodic_task_name(pipeline)

    if not pipeline.schedule:
        deleted, _ = PeriodicTask.objects.filter(name=name).delete()
        if deleted:
            logger.info("periodic task removed", extra={"pipeline_id": pipeline.id})
        return None

    crontab, _ = CrontabSchedule.objects.get_or_create(
        **_parse_crontab(pipeline.schedule)
    )
    task, created = PeriodicTask.objects.update_or_create(
        name=name,
        defaults={
            "task": RUN_PIPELINE_TASK_NAME,
            "crontab": crontab,
            "interval": None,
            "kwargs": json.dumps({"pipeline_id": str(pipeline.id)}),
            "enabled": pipeline.is_active,
        },
    )
    logger.info(
        "periodic task synced",
        extra={
            "pipeline_id": pipeline.id,
            "task_created": created,
            "enabled": task.enabled,
        },
    )
    return task
