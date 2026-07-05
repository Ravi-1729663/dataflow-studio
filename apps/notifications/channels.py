"""Pluggable notification channels. Each raises on delivery failure; the caller
(services.notify) is responsible for catching that and recording it in a NotificationLog.
"""

import json
import urllib.request
from abc import ABC, abstractmethod

from django.core.mail import send_mail


class NotificationChannel(ABC):
    @abstractmethod
    def send(self, subject: str, body: str, preference) -> None:
        """Raise on failure."""


class EmailChannel(NotificationChannel):
    def send(self, subject: str, body: str, preference) -> None:
        if not preference.owner.email:
            raise ValueError("owner has no email address")
        send_mail(
            subject, body, from_email=None, recipient_list=[preference.owner.email]
        )


class SlackChannel(NotificationChannel):
    def send(self, subject: str, body: str, preference) -> None:
        payload = json.dumps({"text": f"*{subject}*\n{body}"}).encode()
        request = urllib.request.Request(
            preference.slack_webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(
            request, timeout=5
        )  # noqa: S310 - webhook URL is owner-configured
