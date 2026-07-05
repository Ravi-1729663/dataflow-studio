from django.conf import settings
from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


def _is_healthy(check: str) -> bool:
    return check == "ok" or check.startswith("skipped")


class HealthView(APIView):
    """Unauthenticated liveness/readiness probe. Checks the database and, when async execution
    is actually in play, the Celery broker — skipped under CELERY_TASK_ALWAYS_EAGER=1 (this
    project's zero-setup local-dev default), since no broker is needed there at all."""

    permission_classes = [AllowAny]

    def get(self, request):
        checks = {"database": self._check_database(), "broker": self._check_broker()}
        healthy = all(_is_healthy(v) for v in checks.values())
        return Response(
            {"status": "ok" if healthy else "degraded", "checks": checks},
            status=200 if healthy else 503,
        )

    def _check_database(self) -> str:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            return "ok"
        except (
            Exception
        ) as exc:  # noqa: BLE001 - reported as a health check result, not raised
            return f"error: {exc}"

    def _check_broker(self) -> str:
        if settings.CELERY_TASK_ALWAYS_EAGER:
            return "skipped (eager mode)"
        try:
            from config.celery import app as celery_app

            connection_ = celery_app.connection()
            connection_.ensure_connection(max_retries=1, timeout=2)
            connection_.close()
            return "ok"
        except (
            Exception
        ) as exc:  # noqa: BLE001 - reported as a health check result, not raised
            return f"error: {exc}"
