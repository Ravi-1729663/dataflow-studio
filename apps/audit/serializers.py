from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor = serializers.CharField(source="actor.username", default=None, read_only=True)
    workspace = serializers.CharField(
        source="workspace.name", default=None, read_only=True
    )

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "actor",
            "workspace",
            "action",
            "target",
            "metadata",
            "created_at",
        )
        read_only_fields = fields
