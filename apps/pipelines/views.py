import logging

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsEngineerOrAdminOrReadOnly
from apps.audit.services import record as audit_record
from apps.common.idempotency import idempotent
from apps.monitoring.tracing import inject_context

from . import services
from .models import Pipeline, PipelineRun
from .serializers import PipelineRunSerializer, PipelineSerializer
from .tasks import run_pipeline_task

logger = logging.getLogger("dataflow.pipelines")


class PipelineViewSet(viewsets.ModelViewSet):
    serializer_class = PipelineSerializer
    permission_classes = [IsEngineerOrAdminOrReadOnly]
    filterset_fields = ["is_active", "source"]

    def get_queryset(self):
        return Pipeline.objects.filter(
            workspace__memberships__user=self.request.user
        ).distinct()

    def perform_create(self, serializer):
        pipeline = serializer.save(owner=self.request.user)
        logger.info("pipeline created", extra={"pipeline_id": pipeline.id})
        audit_record(
            self.request.user,
            "pipeline.created",
            workspace=pipeline.workspace,
            target=pipeline.name,
        )

    @action(detail=True, methods=["post"])
    @idempotent("pipeline.run")
    def run(self, request, pk=None):
        """Enqueue the pipeline for async execution. Returns immediately with the new run's id —
        does not wait for the Celery task to finish (except in eager/local-dev mode, where it
        already has by the time .delay() returns)."""
        pipeline = self.get_object()
        run = services.start_run(pipeline)
        run_pipeline_task.delay(
            pipeline_id=str(pipeline.id),
            run_id=str(run.id),
            trace_context=inject_context(),
        )
        run.refresh_from_db()
        audit_record(
            request.user,
            "pipeline.run",
            workspace=pipeline.workspace,
            target=pipeline.name,
        )
        return Response(PipelineRunSerializer(run).data, status=202)

    @action(detail=True, methods=["post"])
    def clone(self, request, pk=None):
        pipeline = self.get_object()
        clone = Pipeline.objects.create(
            name=f"{pipeline.name} (copy)",
            source=pipeline.source,
            config=pipeline.config,
            schedule=pipeline.schedule,
            owner=request.user,
            is_active=False,
        )
        logger.info(
            "pipeline cloned",
            extra={"source_pipeline_id": pipeline.id, "clone_id": clone.id},
        )
        audit_record(
            request.user,
            "pipeline.cloned",
            workspace=clone.workspace,
            target=clone.name,
        )
        return Response(PipelineSerializer(clone).data, status=201)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        pipeline = self.get_object()
        pipeline.is_active = False
        pipeline.save(update_fields=["is_active", "updated_at"])
        audit_record(
            request.user,
            "pipeline.paused",
            workspace=pipeline.workspace,
            target=pipeline.name,
        )
        return Response(PipelineSerializer(pipeline).data)

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        pipeline = self.get_object()
        pipeline.is_active = True
        pipeline.save(update_fields=["is_active", "updated_at"])
        audit_record(
            request.user,
            "pipeline.resumed",
            workspace=pipeline.workspace,
            target=pipeline.name,
        )
        return Response(PipelineSerializer(pipeline).data)


class PipelineRunViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PipelineRunSerializer
    filterset_fields = ["status", "pipeline"]

    def get_queryset(self):
        return PipelineRun.objects.filter(
            pipeline__workspace__memberships__user=self.request.user
        ).distinct()
