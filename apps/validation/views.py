from rest_framework import viewsets

from .models import QualityScorecard
from .serializers import QualityScorecardSerializer


class QualityScorecardViewSet(viewsets.ReadOnlyModelViewSet):
    """History + trend of per-run quality scorecards, oldest first for easy charting."""

    serializer_class = QualityScorecardSerializer
    filterset_fields = ["run__pipeline", "passed"]

    def get_queryset(self):
        return (
            QualityScorecard.objects.filter(run__pipeline__owner=self.request.user)
            .select_related("run", "run__pipeline")
            .order_by("created_at")
        )
