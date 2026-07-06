from rest_framework import serializers

from apps.datasources.models import DataSource

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
            "workspace",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "owner", "workspace", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Without this, DRF's default PrimaryKeyRelatedField queryset for `source` is *every*
        # DataSource in the system — a user could reference another workspace's source by UUID
        # and have their pipeline silently read across the tenant boundary. Scoping it here is
        # the actual enforcement; DataSourceViewSet's own scoping only stops *listing* others'
        # sources, not referencing one you already know the id of.
        request = self.context.get("request")
        if request is not None:
            self.fields["source"].queryset = DataSource.objects.filter(
                workspace__memberships__user=request.user
            ).distinct()

    def validate_schedule(self, value: str) -> str:
        if not value:
            return value
        if len(value.split()) != 5:
            raise serializers.ValidationError(
                "schedule must be a 5-field cron expression, e.g. '*/2 * * * *'"
            )
        return value
