from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

from apps.common.models import BaseModel
from apps.pipelines.models import PipelineRun

# Restricting this to Slack's own webhook host prevents a user from pointing the server at an
# arbitrary internal URL (SSRF) via a field they fully control.
_slack_webhook_validator = RegexValidator(
    regex=r"^https://hooks\.slack\.com/services/.+",
    message="slack_webhook_url must be a real Slack webhook URL (https://hooks.slack.com/services/...)",
)


class NotificationPreference(BaseModel):
    """Per-user opt-in/out for each channel. Deliberately kept user-scoped rather than
    workspace-scoped even after v0.7 introduced workspaces — a person's alerting preferences are
    personal, not a property of any one workspace they belong to."""

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preference",
    )
    email_enabled = models.BooleanField(default=True)
    slack_enabled = models.BooleanField(default=False)
    slack_webhook_url = models.URLField(
        blank=True, validators=[_slack_webhook_validator]
    )

    def __str__(self) -> str:
        return f"Notification preference for {self.owner}"


class NotificationLog(BaseModel):
    class Event(models.TextChoices):
        RUN_FAILED = "RUN_FAILED", "Run failed"
        RUN_SUCCEEDED = "RUN_SUCCEEDED", "Run succeeded"
        RUN_RETRYING = "RUN_RETRYING", "Run retrying"

    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        SLACK = "SLACK", "Slack"

    run = models.ForeignKey(
        PipelineRun, on_delete=models.CASCADE, related_name="notifications"
    )
    event = models.CharField(max_length=20, choices=Event.choices)
    channel = models.CharField(max_length=10, choices=Channel.choices)
    recipient = models.CharField(max_length=255, blank=True)
    success = models.BooleanField(default=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.event} -> {self.channel} ({'ok' if self.success else 'failed'})"
