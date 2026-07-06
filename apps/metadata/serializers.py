from rest_framework import serializers

from .models import ColumnAnomaly, ColumnMetadata, Dataset, SchemaVersion


class DatasetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dataset
        fields = ("id", "name", "description", "created_at", "updated_at")
        read_only_fields = fields


class ColumnMetadataSerializer(serializers.ModelSerializer):
    dataset = serializers.SlugRelatedField(slug_field="name", read_only=True)

    class Meta:
        model = ColumnMetadata
        fields = (
            "id",
            "dataset",
            "name",
            "dtype",
            "description",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class SchemaVersionSerializer(serializers.ModelSerializer):
    dataset = serializers.SlugRelatedField(slug_field="name", read_only=True)

    class Meta:
        model = SchemaVersion
        fields = (
            "id",
            "dataset",
            "run",
            "version",
            "columns",
            "added_columns",
            "removed_columns",
            "renamed_columns",
            "is_drift",
            "created_at",
        )
        read_only_fields = fields


class ColumnAnomalySerializer(serializers.ModelSerializer):
    dataset = serializers.SlugRelatedField(slug_field="name", read_only=True)

    class Meta:
        model = ColumnAnomaly
        fields = (
            "id",
            "dataset",
            "run",
            "column",
            "value",
            "baseline_mean",
            "baseline_stddev",
            "z_score",
            "created_at",
        )
        read_only_fields = fields
