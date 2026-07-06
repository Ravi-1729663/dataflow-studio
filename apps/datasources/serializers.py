from rest_framework import serializers

from apps.workspaces.services import is_member

from .models import DataSource


class DataSourceSerializer(serializers.ModelSerializer):
    # EncryptedJSONField is a TextField under the hood (the column stores opaque ciphertext, not
    # JSON — see apps.common.fields), so DRF's auto-generated field would otherwise be a plain
    # CharField that rejects a dict payload with "Not a valid string."
    config = serializers.JSONField(default=dict)

    class Meta:
        model = DataSource
        fields = (
            "id",
            "name",
            "source_type",
            "config",
            "owner",
            "workspace",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "owner", "created_at", "updated_at")
        extra_kwargs = {"workspace": {"required": True}}

    def validate_workspace(self, workspace):
        request = self.context["request"]
        if not is_member(workspace, request.user):
            raise serializers.ValidationError("you are not a member of this workspace")
        return workspace
