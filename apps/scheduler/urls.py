from django.urls import path

from .views import DeadLetterListView, QueueView, RetryFailedRunView

urlpatterns = [
    path("queue/", QueueView.as_view(), name="scheduler-queue"),
    path("dead-letter/", DeadLetterListView.as_view(), name="scheduler-dead-letter"),
    path(
        "runs/<uuid:run_id>/retry/",
        RetryFailedRunView.as_view(),
        name="scheduler-retry-run",
    ),
]
