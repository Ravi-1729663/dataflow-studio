from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class DataSource(BaseModel):
    class SourceType(models.TextChoices):
        FILE = "FILE", "File"
        POSTGRES = "POSTGRES", "Postgres"
        REST_API = "REST_API", "REST API"

    name = models.CharField(max_length=200)
    source_type = models.CharField(max_length=16, choices=SourceType.choices)
    config = models.JSONField(default=dict)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="data_sources"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.source_type})"
