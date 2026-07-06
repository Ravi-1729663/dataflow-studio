from django.conf import settings
from django.db import models

from apps.common.models import BaseModel
from apps.workspaces.models import Workspace


class AuditLog(BaseModel):
    """An immutable record of a sensitive action. ``actor`` is null for actions the system takes
    on its own behalf (there are none yet, but the field stays nullable for that case).
    ``workspace`` is null for actions that aren't workspace-scoped (registration, login).
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    # SET_NULL, not CASCADE: an audit trail must outlive the thing it describes — deleting a
    # workspace should not silently erase the record that it was ever created or deleted.
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=100)
    target = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.actor}: {self.action} {self.target}".strip()
