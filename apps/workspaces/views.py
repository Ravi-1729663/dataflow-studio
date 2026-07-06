import logging

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.audit.services import record as audit_record

from . import services
from .models import Workspace, WorkspaceMembership
from .serializers import WorkspaceMembershipSerializer, WorkspaceSerializer

logger = logging.getLogger("dataflow.workspaces")
User = get_user_model()


class WorkspaceViewSet(viewsets.ModelViewSet):
    """A user can only see/act on workspaces they belong to — this queryset *is* the isolation
    boundary every other workspace-scoped app builds on."""

    serializer_class = WorkspaceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Workspace.objects.filter(memberships__user=self.request.user).distinct()

    def perform_create(self, serializer):
        workspace = services.create_workspace(
            self.request.user, serializer.validated_data["name"]
        )
        serializer.instance = workspace
        audit_record(
            self.request.user,
            "workspace.created",
            workspace=workspace,
            target=workspace.name,
        )

    def perform_destroy(self, instance):
        # workspace=instance, not None: the FK is SET_NULL on delete, so this row survives with
        # workspace cleared once instance.delete() cascades — the record just names it in target.
        audit_record(
            self.request.user,
            "workspace.deleted",
            workspace=instance,
            target=instance.name,
        )
        instance.delete()

    @action(detail=True, methods=["get", "post"])
    def members(self, request, pk=None):
        workspace = self.get_object()
        if request.method == "GET":
            memberships = workspace.memberships.select_related("user")
            return Response(WorkspaceMembershipSerializer(memberships, many=True).data)

        if not services.is_owner(workspace, request.user):
            return Response(
                {"error": "only the workspace owner can add members"}, status=403
            )
        username = request.data.get("username")
        target_user = get_object_or_404(User, username=username)
        role = request.data.get("role", WorkspaceMembership.Role.MEMBER)
        membership = services.add_member(workspace, target_user, role)
        audit_record(
            request.user,
            "workspace.member_added",
            workspace=workspace,
            target=target_user.username,
        )
        logger.info(
            "workspace member added",
            extra={
                "workspace_id": workspace.id,
                "user_id": target_user.id,
                "role": role,
            },
        )
        return Response(WorkspaceMembershipSerializer(membership).data, status=201)

    @action(detail=True, methods=["delete"], url_path="members/(?P<user_id>[^/.]+)")
    def remove_member(self, request, pk=None, user_id=None):
        workspace = self.get_object()
        if not services.is_owner(workspace, request.user):
            return Response(
                {"error": "only the workspace owner can remove members"}, status=403
            )
        target_user = get_object_or_404(User, pk=user_id)
        services.remove_member(workspace, target_user)
        audit_record(
            request.user,
            "workspace.member_removed",
            workspace=workspace,
            target=target_user.username,
        )
        return Response(status=204)
