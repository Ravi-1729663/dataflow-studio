from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class Workspace(BaseModel):
    """The tenant boundary: every workspace-owned resource (DataSource, Pipeline, ...) belongs to
    exactly one workspace, and a user can only see/act on a resource in a workspace they're a
    member of. This is the unit of "org isolation" for v0.7."""

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class WorkspaceMembership(BaseModel):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner"
        MEMBER = "MEMBER", "Member"

    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workspace_memberships",
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "user"], name="unique_workspace_membership"
            )
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user} in {self.workspace} ({self.role})"
