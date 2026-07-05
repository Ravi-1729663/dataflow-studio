from django.conf import settings
from django.db import models

from apps.common.models import BaseModel
from apps.datasources.models import DataSource


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
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class PipelineRun(BaseModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
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

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.pipeline.name} run {self.id} ({self.status})"
