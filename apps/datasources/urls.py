from rest_framework.routers import DefaultRouter

from .views import DataSourceViewSet

router = DefaultRouter()
router.register("", DataSourceViewSet, basename="datasource")

urlpatterns = router.urls
