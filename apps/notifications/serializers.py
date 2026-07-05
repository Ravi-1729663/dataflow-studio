from rest_framework import serializers

from .models import NotificationLog, NotificationPreference


class NotificationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationLog
        fields = (
            "id",
            "run",
            "event",
            "channel",
            "recipient",
            "success",
            "error",
            "created_at",
        )
        read_only_fields = fields


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = (
            "id",
            "email_enabled",
            "slack_enabled",
            "slack_webhook_url",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
