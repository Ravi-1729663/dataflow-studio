from rest_framework import generics, viewsets

from . import services
from .models import NotificationLog
from .serializers import NotificationLogSerializer, NotificationPreferenceSerializer


class NotificationLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationLogSerializer
    filterset_fields = ["event", "channel", "success", "run__pipeline"]

    def get_queryset(self):
        return NotificationLog.objects.filter(
            run__pipeline__owner=self.request.user
        ).select_related("run", "run__pipeline")


class NotificationPreferenceView(generics.RetrieveUpdateAPIView):
    """The requesting user's own notification preference (created on first access)."""

    serializer_class = NotificationPreferenceSerializer

    def get_object(self):
        return services.get_or_create_preference(self.request.user)
