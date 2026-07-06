from rest_framework import viewsets

from .models import Customer
from .serializers import CustomerSerializer


class CustomerViewSet(viewsets.ReadOnlyModelViewSet):
    """The served gold layer: read-only, filtered, paginated. This is what analysts/dashboards read."""

    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    filterset_fields = ["country", "external_id", "is_current"]
