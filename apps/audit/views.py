from rest_framework import generics

from apps.accounts.permissions import IsAdmin

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogListView(generics.ListAPIView):
    """Platform-admin-only: the audit trail is a global, cross-workspace surface (consistent
    with ``User.role == ADMIN`` being a platform-wide role, not a per-workspace one)."""

    serializer_class = AuditLogSerializer
    permission_classes = [IsAdmin]
    filterset_fields = ["action", "workspace", "actor"]
    queryset = AuditLog.objects.select_related("actor", "workspace").all()
