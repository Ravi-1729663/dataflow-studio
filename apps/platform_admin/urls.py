from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import PlatformConfigViewSet, SystemHealthView, UserAdminViewSet

router = DefaultRouter()
router.register("users", UserAdminViewSet, basename="admin-user")
router.register("config", PlatformConfigViewSet, basename="admin-config")

urlpatterns = router.urls + [
    path("health/", SystemHealthView.as_view(), name="admin-health"),
]
