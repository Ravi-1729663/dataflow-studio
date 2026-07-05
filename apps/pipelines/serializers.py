from rest_framework import serializers

from .models import DeadLetterRecord, Pipeline, PipelineRun


class PipelineRunSerializer(serializers.ModelSerializer):
    is_dead_lettered = serializers.SerializerMethodField()

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
            "traceback",
            "retry_count",
            "is_dead_lettered",
            "created_at",
        )
        read_only_fields = fields

    def get_is_dead_lettered(self, obj) -> bool:
        return hasattr(obj, "dead_letter")


class DeadLetterRecordSerializer(serializers.ModelSerializer):
    run = PipelineRunSerializer(read_only=True)

    class Meta:
        model = DeadLetterRecord
        fields = ("id", "run", "error", "traceback", "created_at")
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

    def validate_schedule(self, value: str) -> str:
        if not value:
            return value
        if len(value.split()) != 5:
            raise serializers.ValidationError(
                "schedule must be a 5-field cron expression, e.g. '*/2 * * * *'"
            )
        return value
