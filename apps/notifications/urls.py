from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import NotificationLogViewSet, NotificationPreferenceView

router = DefaultRouter()
router.register("logs", NotificationLogViewSet, basename="notification-log")

urlpatterns = [
    path(
        "preference/",
        NotificationPreferenceView.as_view(),
        name="notification-preference",
    ),
] + router.urls
