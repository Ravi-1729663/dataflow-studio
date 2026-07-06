from rest_framework import serializers

from .models import Workspace, WorkspaceMembership


class WorkspaceMembershipSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = WorkspaceMembership
        fields = ("id", "user", "username", "role", "created_at")
        read_only_fields = ("id", "username", "created_at")


class WorkspaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workspace
        fields = ("id", "name", "slug", "created_at", "updated_at")
        read_only_fields = ("id", "slug", "created_at", "updated_at")
