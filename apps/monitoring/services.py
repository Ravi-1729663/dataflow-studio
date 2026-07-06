"""Execution dashboard: success rate, failed jobs, runtime metrics — computed on the fly from
PipelineRun, no separate storage needed. Duration is read from PipelineRun.metrics (a JSONField)
in Python rather than via an ORM aggregate, since JSON-key aggregation isn't equally portable
across SQLite (local dev) and PostgreSQL (production)."""

from apps.accounts.models import User
from apps.pipelines.models import PipelineRun


def get_dashboard(owner: User) -> dict:
    runs = PipelineRun.objects.filter(pipeline__workspace__memberships__user=owner)
    total = runs.count()
    succeeded_runs = runs.filter(status=PipelineRun.Status.SUCCEEDED)
    succeeded = succeeded_runs.count()
    failed = runs.filter(status=PipelineRun.Status.FAILED)

    durations = [
        run.metrics.get("duration_seconds")
        for run in succeeded_runs
        if run.metrics.get("duration_seconds") is not None
    ]

    return {
        "total_runs": total,
        "succeeded": succeeded,
        "failed": failed.count(),
        "retrying": runs.filter(status=PipelineRun.Status.RETRYING).count(),
        "pending_or_running": runs.filter(
            status__in=[PipelineRun.Status.PENDING, PipelineRun.Status.RUNNING]
        ).count(),
        "success_rate_percent": round(100 * succeeded / total, 2) if total else None,
        "avg_duration_seconds": (
            round(sum(durations) / len(durations), 4) if durations else None
        ),
        "failed_jobs": [
            {
                "run_id": run.id,
                "pipeline": run.pipeline.name,
                "error": run.error,
                "created_at": run.created_at,
            }
            for run in failed.select_related("pipeline").order_by("-created_at")[:20]
        ],
    }
