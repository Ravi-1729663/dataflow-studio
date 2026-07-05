from rest_framework.routers import DefaultRouter

from .views import QualityScorecardViewSet

router = DefaultRouter()
router.register("scorecards", QualityScorecardViewSet, basename="scorecard")

urlpatterns = router.urls
