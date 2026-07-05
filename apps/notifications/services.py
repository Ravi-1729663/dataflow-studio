"""Dispatches run-lifecycle notifications through each owner's enabled channels, respecting
their NotificationPreference. Called from pipelines.services at failure/success/retry — the same
"bridge a Django model to a side-effect" role that app already plays for the warehouse loader,
the validation scorecard, and the metadata catalog."""

import logging

from django.template.loader import render_to_string

from apps.pipelines.models import PipelineRun

from .channels import EmailChannel, SlackChannel
from .models import NotificationLog, NotificationPreference

logger = logging.getLogger("dataflow.notifications")

_CHANNELS = {
    NotificationLog.Channel.EMAIL: EmailChannel(),
    NotificationLog.Channel.SLACK: SlackChannel(),
}

_SUBJECTS = {
    NotificationLog.Event.RUN_FAILED: "Pipeline run failed",
    NotificationLog.Event.RUN_SUCCEEDED: "Pipeline run succeeded",
    NotificationLog.Event.RUN_RETRYING: "Pipeline run retrying",
}

_TEMPLATES = {
    NotificationLog.Event.RUN_FAILED: "notifications/run_failed.txt",
    NotificationLog.Event.RUN_SUCCEEDED: "notifications/run_succeeded.txt",
    NotificationLog.Event.RUN_RETRYING: "notifications/run_retrying.txt",
}


def get_or_create_preference(owner) -> NotificationPreference:
    preference, _ = NotificationPreference.objects.get_or_create(owner=owner)
    return preference


def notify(event: str, run: PipelineRun) -> list[NotificationLog]:
    pipeline = run.pipeline
    preference = get_or_create_preference(pipeline.owner)
    subject = _SUBJECTS[event]
    body = render_to_string(_TEMPLATES[event], {"run": run, "pipeline": pipeline})

    recipients = []
    if preference.email_enabled:
        recipients.append((NotificationLog.Channel.EMAIL, pipeline.owner.email))
    if preference.slack_enabled and preference.slack_webhook_url:
        recipients.append((NotificationLog.Channel.SLACK, preference.slack_webhook_url))

    logs = []
    for channel_key, recipient in recipients:
        channel = _CHANNELS[channel_key]
        try:
            channel.send(subject, body, preference)
        except (
            Exception
        ) as exc:  # noqa: BLE001 - a notification failure must never break a run
            logger.warning(
                "notification delivery failed",
                extra={
                    "run_id": run.id,
                    "event": event,
                    "channel": channel_key,
                    "error": str(exc),
                },
            )
            logs.append(
                NotificationLog.objects.create(
                    run=run,
                    event=event,
                    channel=channel_key,
                    recipient=recipient,
                    success=False,
                    error=str(exc),
                )
            )
            continue
        logger.info(
            "notification sent",
            extra={"run_id": run.id, "event": event, "channel": channel_key},
        )
        logs.append(
            NotificationLog.objects.create(
                run=run,
                event=event,
                channel=channel_key,
                recipient=recipient,
                success=True,
            )
        )
    return logs
