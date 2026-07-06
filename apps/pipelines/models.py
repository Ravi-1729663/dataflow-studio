from django.conf import settings
from django.db import models

from apps.common.models import BaseModel
from apps.datasources.models import DataSource
from apps.workspaces.models import Workspace


class Pipeline(BaseModel):
    """A pipeline binds a DataSource to validation/transform/target specs (JSON, schema-free)."""

    name = models.CharField(max_length=200)
    source = models.ForeignKey(
        DataSource, on_delete=models.CASCADE, related_name="pipelines"
    )
    config = models.JSONField(default=dict)
    schedule = models.CharField(max_length=100, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pipelines"
    )
    # Always the same workspace as `source` (see save() below) — a pipeline can't reach across
    # workspaces to read someone else's source. Not client-settable; derived, not requested.
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="pipelines",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.source_id and not self.workspace_id:
            self.workspace_id = self.source.workspace_id
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class PipelineRun(BaseModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        RETRYING = "RETRYING", "Retrying"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"

    pipeline = models.ForeignKey(
        Pipeline, on_delete=models.CASCADE, related_name="runs"
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    logs = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    traceback = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.pipeline.name} run {self.id} ({self.status})"


class DeadLetterRecord(BaseModel):
    """A run that exhausted all automatic retries. Kept separate from PipelineRun so ops can see
    what needs attention/reprocessing without scanning every FAILED run."""

    run = models.OneToOneField(
        PipelineRun, on_delete=models.CASCADE, related_name="dead_letter"
    )
    error = models.TextField()
    traceback = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"DLQ: {self.run.pipeline.name} run {self.run.id}"


class PipelineWatermark(BaseModel):
    """The incremental cursor for a pipeline's source (e.g. the max value of ``updated_at`` seen
    so far), so the next run only extracts new/changed rows. Only exists for pipelines with
    ``config["incremental"]`` set; updated after each successful run."""

    pipeline = models.OneToOneField(
        Pipeline, on_delete=models.CASCADE, related_name="watermark"
    )
    value = models.CharField(max_length=200, blank=True)

    def __str__(self) -> str:
        return f"watermark for {self.pipeline.name}: {self.value!r}"
