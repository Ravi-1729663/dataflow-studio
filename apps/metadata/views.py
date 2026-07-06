from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from . import medallion, services
from .models import ColumnAnomaly, ColumnMetadata, Dataset, SchemaVersion
from .serializers import (
    ColumnAnomalySerializer,
    ColumnMetadataSerializer,
    DatasetSerializer,
    SchemaVersionSerializer,
)

MEDALLION_LAYERS = ("BRONZE", "SILVER", "GOLD")


class DatasetViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Dataset.objects.all()
    serializer_class = DatasetSerializer
    lookup_field = "name"


class SchemaVersionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SchemaVersionSerializer
    filterset_fields = ["dataset__name", "is_drift"]
    queryset = SchemaVersion.objects.select_related("dataset").order_by("-created_at")


class ColumnMetadataViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ColumnMetadataSerializer
    filterset_fields = ["dataset__name"]
    queryset = ColumnMetadata.objects.select_related("dataset").all()


class ColumnAnomalyViewSet(viewsets.ReadOnlyModelViewSet):
    """Statistical outliers flagged by ``services.detect_anomalies`` — a z-score check against
    each column's running baseline, recorded on every ingest."""

    serializer_class = ColumnAnomalySerializer
    filterset_fields = ["dataset__name", "column"]
    queryset = ColumnAnomaly.objects.select_related("dataset").all()


class LineageGraphView(APIView):
    """The full source -> bronze -> silver -> gold graph for a dataset, resolvable by the
    warehouse table name it backs (e.g. "customers")."""

    def get(self, request, dataset_name):
        dataset = get_object_or_404(Dataset, name=dataset_name)
        return Response(services.get_lineage_graph(dataset))


class MedallionQueryView(APIView):
    """Query a dataset's bronze/silver/gold Parquet layer via DuckDB."""

    def get(self, request, dataset_name, layer):
        layer = layer.upper()
        if layer not in MEDALLION_LAYERS:
            return Response(
                {"error": f"layer must be one of {MEDALLION_LAYERS}"}, status=400
            )
        dataset = get_object_or_404(Dataset, name=dataset_name)
        limit = int(request.query_params.get("limit", 100))
        rows = medallion.query_layer(layer, dataset.name, limit=limit)
        return Response(
            {
                "dataset": dataset.name,
                "layer": layer,
                "row_count": len(rows),
                "rows": rows,
            }
        )
