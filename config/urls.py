from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("django_prometheus.urls")),  # /metrics
    path("api/health/", include("apps.common.urls")),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/datasources/", include("apps.datasources.urls")),
    path("api/pipelines/", include("apps.pipelines.urls")),
    path("api/scheduler/", include("apps.scheduler.urls")),
    path("api/validation/", include("apps.validation.urls")),
    path("api/metadata/", include("apps.metadata.urls")),
    path("api/monitoring/", include("apps.monitoring.urls")),
    path("api/notifications/", include("apps.notifications.urls")),
    path("api/warehouse/", include("apps.warehouse.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]
