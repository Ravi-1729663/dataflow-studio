from django.db import models

from apps.common.models import BaseModel


class PlatformConfig(BaseModel):
    """A single platform-wide key/value setting, editable by admins at runtime (e.g. feature
    flags, default limits) without a deploy. Deliberately untyped (string value) — callers parse
    whatever they expect."""

    key = models.CharField(max_length=100, unique=True)
    value = models.TextField(blank=True)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key
