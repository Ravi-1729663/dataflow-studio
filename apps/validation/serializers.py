from rest_framework import serializers

from .models import QualityScorecard


class QualityScorecardSerializer(serializers.ModelSerializer):
    pipeline = serializers.SerializerMethodField()
    score_delta = serializers.SerializerMethodField()

    class Meta:
        model = QualityScorecard
        fields = (
            "id",
            "run",
            "pipeline",
            "completeness",
            "consistency",
            "accuracy",
            "overall_score",
            "passed",
            "checks",
            "score_delta",
            "created_at",
        )
        read_only_fields = fields

    def get_pipeline(self, obj: QualityScorecard):
        return obj.run.pipeline_id

    def get_score_delta(self, obj: QualityScorecard):
        previous = (
            QualityScorecard.objects.filter(
                run__pipeline=obj.run.pipeline_id, created_at__lt=obj.created_at
            )
            .order_by("-created_at")
            .first()
        )
        return (
            round(obj.overall_score - previous.overall_score, 2) if previous else None
        )
