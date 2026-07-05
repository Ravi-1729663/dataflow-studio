from rest_framework.routers import DefaultRouter

from .views import PipelineRunViewSet, PipelineViewSet

router = DefaultRouter()
router.register("runs", PipelineRunViewSet, basename="pipelinerun")
router.register("", PipelineViewSet, basename="pipeline")

urlpatterns = router.urls
