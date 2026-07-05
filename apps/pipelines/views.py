import logging

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsEngineerOrAdminOrReadOnly

from .models import Pipeline, PipelineRun
from .serializers import PipelineRunSerializer, PipelineSerializer
from .tasks import run_pipeline_task

logger = logging.getLogger("dataflow.pipelines")


class PipelineViewSet(viewsets.ModelViewSet):
    serializer_class = PipelineSerializer
    permission_classes = [IsEngineerOrAdminOrReadOnly]
    filterset_fields = ["is_active", "source"]

    def get_queryset(self):
        return Pipeline.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        pipeline = serializer.save(owner=self.request.user)
        logger.info("pipeline created", extra={"pipeline_id": pipeline.id})

    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        pipeline = self.get_object()
        run_id = run_pipeline_task(str(pipeline.id))
        run = PipelineRun.objects.get(pk=run_id)
        return Response(PipelineRunSerializer(run).data, status=202)


class PipelineRunViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PipelineRunSerializer
    filterset_fields = ["status", "pipeline"]

    def get_queryset(self):
        return PipelineRun.objects.filter(pipeline__owner=self.request.user)
