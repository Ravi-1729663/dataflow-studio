from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ColumnMetadataViewSet,
    DatasetViewSet,
    LineageGraphView,
    MedallionQueryView,
    SchemaVersionViewSet,
)

router = DefaultRouter()
router.register("datasets", DatasetViewSet, basename="dataset")
router.register("schema-versions", SchemaVersionViewSet, basename="schema-version")
router.register("columns", ColumnMetadataViewSet, basename="column-metadata")

urlpatterns = [
    path(
        "datasets/<str:dataset_name>/lineage/",
        LineageGraphView.as_view(),
        name="dataset-lineage",
    ),
    path(
        "datasets/<str:dataset_name>/medallion/<str:layer>/",
        MedallionQueryView.as_view(),
        name="dataset-medallion",
    ),
] + router.urls
