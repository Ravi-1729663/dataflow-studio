import logging

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsEngineerOrAdminOrReadOnly
from apps.audit.services import record as audit_record
from apps.common.exceptions import ConnectorError

from . import services
from .models import DataSource
from .serializers import DataSourceSerializer

logger = logging.getLogger("dataflow.datasources")


class DataSourceViewSet(viewsets.ModelViewSet):
    serializer_class = DataSourceSerializer
    permission_classes = [IsEngineerOrAdminOrReadOnly]
    filterset_fields = ["source_type", "is_active", "workspace"]

    def get_queryset(self):
        return DataSource.objects.filter(
            workspace__memberships__user=self.request.user
        ).distinct()

    def perform_create(self, serializer):
        data_source = serializer.save(owner=self.request.user)
        logger.info("datasource created", extra={"data_source_id": data_source.id})
        audit_record(
            self.request.user,
            "datasource.created",
            workspace=data_source.workspace,
            target=data_source.name,
        )

    def perform_update(self, serializer):
        data_source = serializer.save()
        audit_record(
            self.request.user,
            "datasource.updated",
            workspace=data_source.workspace,
            target=data_source.name,
        )

    def perform_destroy(self, instance):
        audit_record(
            self.request.user,
            "datasource.deleted",
            workspace=instance.workspace,
            target=instance.name,
        )
        instance.delete()

    @action(detail=True, methods=["post"], url_path="test-connection")
    def test_connection(self, request, pk=None):
        data_source = self.get_object()
        try:
            services.test_connection(data_source)
        except ConnectorError as exc:
            return Response({"ok": False, "error": str(exc)}, status=400)
        return Response({"ok": True})
