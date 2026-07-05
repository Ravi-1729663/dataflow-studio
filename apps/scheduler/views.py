import logging

from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsEngineerOrAdminOrReadOnly
from apps.monitoring.tracing import inject_context
from apps.pipelines import services as pipeline_services
from apps.pipelines.models import DeadLetterRecord, PipelineRun
from apps.pipelines.serializers import DeadLetterRecordSerializer, PipelineRunSerializer
from apps.pipelines.tasks import run_pipeline_task

logger = logging.getLogger("dataflow.scheduler")


class QueueView(APIView):
    """In-flight runs (PENDING/RUNNING/RETRYING) for the requesting user's pipelines."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        runs = (
            PipelineRun.objects.filter(
                pipeline__owner=request.user,
                status__in=[
                    PipelineRun.Status.PENDING,
                    PipelineRun.Status.RUNNING,
                    PipelineRun.Status.RETRYING,
                ],
            )
            .select_related("pipeline")
            .order_by("-created_at")
        )
        return Response(PipelineRunSerializer(runs, many=True).data)


class RetryFailedRunView(APIView):
    """Re-enqueue a FAILED run's pipeline as a brand-new run. Idempotent loads make this safe."""

    permission_classes = [IsEngineerOrAdminOrReadOnly]

    def post(self, request, run_id):
        run = get_object_or_404(PipelineRun, pk=run_id, pipeline__owner=request.user)
        if run.status != PipelineRun.Status.FAILED:
            return Response({"error": "only FAILED runs can be retried"}, status=400)

        new_run = pipeline_services.start_run(run.pipeline)
        run_pipeline_task.delay(
            pipeline_id=str(run.pipeline_id),
            run_id=str(new_run.id),
            trace_context=inject_context(),
        )
        new_run.refresh_from_db()
        logger.info(
            "failed run retried",
            extra={"original_run_id": run.id, "new_run_id": new_run.id},
        )
        return Response(PipelineRunSerializer(new_run).data, status=202)


class DeadLetterListView(generics.ListAPIView):
    """Runs that exhausted every automatic retry — needs a human to look at them."""

    serializer_class = DeadLetterRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return DeadLetterRecord.objects.filter(
            run__pipeline__owner=self.request.user
        ).select_related("run", "run__pipeline")
