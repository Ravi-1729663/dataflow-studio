"""Shared base model for all domain apps."""

import uuid

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class BaseModel(models.Model):
    """UUID primary key + created/updated timestamps, inherited by every domain model."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class IdempotencyKey(BaseModel):
    """Caches a side-effecting endpoint's response against a client-supplied ``Idempotency-Key``
    header, so a retried request (e.g. after a network timeout) replays the original result
    instead of re-triggering the action. See apps.common.idempotency for the decorator that uses
    this."""

    key = models.CharField(max_length=255)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="idempotency_keys",
    )
    endpoint = models.CharField(max_length=255)
    response_status = models.PositiveIntegerField()
    response_body = models.JSONField(encoder=DjangoJSONEncoder)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["key", "user", "endpoint"], name="unique_idempotency_key"
            )
        ]

    def __str__(self) -> str:
        return f"{self.endpoint} [{self.key}] -> {self.response_status}"
