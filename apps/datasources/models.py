from django.conf import settings
from django.db import models

from apps.common.fields import EncryptedJSONField
from apps.common.models import BaseModel
from apps.workspaces.models import Workspace


class DataSource(BaseModel):
    class SourceType(models.TextChoices):
        FILE = "FILE", "File"
        POSTGRES = "POSTGRES", "Postgres"
        REST_API = "REST_API", "REST API"

    name = models.CharField(max_length=200)
    source_type = models.CharField(max_length=16, choices=SourceType.choices)
    # Fernet-encrypted at rest (dsn/headers/etc. may carry credentials) — see
    # apps.common.fields.EncryptedJSONField. Transparent to callers: still just a dict in Python.
    config = EncryptedJSONField(default=dict, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="data_sources"
    )
    # Nullable at the DB level only to keep the migration painless (see workspaces app docs) —
    # required in practice: DataSourceSerializer treats it as a mandatory field.
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="data_sources",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.source_type})"
