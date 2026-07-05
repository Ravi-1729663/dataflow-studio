"""Custom User with a platform role. Keeps the default integer PK per CLAUDE.md."""

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        ENGINEER = "ENGINEER", "Engineer"
        ANALYST = "ANALYST", "Analyst"
        VIEWER = "VIEWER", "Viewer"

    role = models.CharField(max_length=16, choices=Role.choices, default=Role.ENGINEER)

    def __str__(self) -> str:
        return self.username
