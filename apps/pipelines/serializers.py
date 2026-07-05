from rest_framework import serializers

from .models import Pipeline, PipelineRun


class PipelineRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = PipelineRun
        fields = (
            "id",
            "pipeline",
            "status",
            "started_at",
            "finished_at",
            "metrics",
            "logs",
            "error",
            "created_at",
        )
        read_only_fields = fields


class PipelineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pipeline
        fields = (
            "id",
            "name",
            "source",
            "config",
            "schedule",
            "owner",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "owner", "created_at", "updated_at")
