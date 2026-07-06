from rest_framework import serializers

from apps.accounts.models import User

from .models import PlatformConfig


class UserAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "role", "is_active", "date_joined")
        read_only_fields = ("id", "username", "email", "date_joined")


class PlatformConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformConfig
        fields = ("id", "key", "value", "description", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")
