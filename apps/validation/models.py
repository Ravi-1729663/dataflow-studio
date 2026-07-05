from django.db import models

from apps.common.models import BaseModel
from apps.pipelines.models import PipelineRun


class QualityScorecard(BaseModel):
    """Per-run data-quality scorecard, computed by the etl engine's rule library
    (apps.etl.validate) and persisted here for history/trend queries."""

    run = models.OneToOneField(
        PipelineRun, on_delete=models.CASCADE, related_name="scorecard"
    )
    completeness = models.FloatField()
    consistency = models.FloatField()
    accuracy = models.FloatField()
    overall_score = models.FloatField()
    passed = models.BooleanField()
    checks = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Scorecard for run {self.run_id}: {self.overall_score}"
