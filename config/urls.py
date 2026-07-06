from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.views import LoginView

# Everything except health/schema/docs/metrics/admin lives under /api/v1 (v0.7 versioning) —
# those four are infrastructure surfaces, not versioned business API.
v1_patterns = [
    path("auth/", include("apps.accounts.urls")),
    path("auth/token/", LoginView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("workspaces/", include("apps.workspaces.urls")),
    path("audit/", include("apps.audit.urls")),
    path("admin/", include("apps.platform_admin.urls")),
    path("datasources/", include("apps.datasources.urls")),
    path("pipelines/", include("apps.pipelines.urls")),
    path("scheduler/", include("apps.scheduler.urls")),
    path("validation/", include("apps.validation.urls")),
    path("metadata/", include("apps.metadata.urls")),
    path("monitoring/", include("apps.monitoring.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("warehouse/", include("apps.warehouse.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("django_prometheus.urls")),  # /metrics
    path("api/health/", include("apps.common.urls")),
    path("api/v1/", include(v1_patterns)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]
