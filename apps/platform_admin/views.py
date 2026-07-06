import logging

from rest_framework import viewsets

from apps.accounts.models import User
from apps.accounts.permissions import IsAdmin
from apps.audit.services import record as audit_record
from apps.common.views import HealthView

from .models import PlatformConfig
from .serializers import PlatformConfigSerializer, UserAdminSerializer

logger = logging.getLogger("dataflow.platform_admin")


class UserAdminViewSet(viewsets.ModelViewSet):
    """Admin-only user/role management. No create (registration is self-service via
    apps.accounts) or delete (deactivate via ``is_active`` instead, to preserve FK history on
    everything the user owns/authored) — only list, retrieve, and update role/is_active.
    """

    serializer_class = UserAdminSerializer
    permission_classes = [IsAdmin]
    queryset = User.objects.all().order_by("username")
    http_method_names = ["get", "patch", "head", "options"]

    def perform_update(self, serializer):
        user = serializer.save()
        audit_record(
            self.request.user,
            "user.updated",
            target=user.username,
            metadata={"role": user.role, "is_active": user.is_active},
        )


class PlatformConfigViewSet(viewsets.ModelViewSet):
    serializer_class = PlatformConfigSerializer
    permission_classes = [IsAdmin]
    queryset = PlatformConfig.objects.all()

    def perform_create(self, serializer):
        config = serializer.save()
        audit_record(self.request.user, "platform_config.created", target=config.key)

    def perform_update(self, serializer):
        config = serializer.save()
        audit_record(self.request.user, "platform_config.updated", target=config.key)

    def perform_destroy(self, instance):
        audit_record(self.request.user, "platform_config.deleted", target=instance.key)
        instance.delete()


class SystemHealthView(HealthView):
    """Admin-only extended health view: everything the public ``/api/health/`` probe reports,
    plus platform-wide counts useful for an at-a-glance ops view."""

    permission_classes = [IsAdmin]

    def get(self, request):
        from apps.pipelines.models import Pipeline, PipelineRun
        from apps.workspaces.models import Workspace

        response = super().get(request)
        response.data["counts"] = {
            "workspaces": Workspace.objects.count(),
            "users": User.objects.count(),
            "pipelines": Pipeline.objects.count(),
            "pipeline_runs": PipelineRun.objects.count(),
        }
        return response
