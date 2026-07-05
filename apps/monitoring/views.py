from rest_framework.response import Response
from rest_framework.views import APIView

from . import services


class DashboardView(APIView):
    """Success rate, failed jobs, and runtime metrics for the requesting user's pipelines."""

    def get(self, request):
        return Response(services.get_dashboard(request.user))
