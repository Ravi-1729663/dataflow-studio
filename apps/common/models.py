"""Shared base model for all domain apps."""

import uuid

from django.db import models


class BaseModel(models.Model):
    """UUID primary key + created/updated timestamps, inherited by every domain model."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
