import pytest
from django.contrib.auth import get_user_model
from django_celery_beat.models import PeriodicTask
from rest_framework.test import APIClient

from apps.datasources.models import DataSource
from apps.etl.exceptions import EtlError
from apps.pipelines.models import Pipeline, PipelineRun
from apps.pipelines.services import execute_pipeline
from apps.pipelines.tasks import run_pipeline_task

User = get_user_model()


def _periodic_task_name(pipeline: Pipeline) -> str:
    return f"pipeline:{pipeline.id}"


@pytest.fixture
def customers_csv(tmp_path, settings):
    path = tmp_path / "customers.csv"
    path.write_text(
        "customer_id,first_name,last_name,email,signup_date,country\n"
        "1,Ada,Lovelace,ada@example.com,2024-01-01,UK\n"
        "2,Grace,Hopper,grace@example.com,2024-02-01,US\n"
    )
    settings.BASE_DIR = tmp_path
    return "customers.csv"


@pytest.fixture
def pipeline(db, customers_csv):
    user = User.objects.create_user(username="engineer", password="pw12345678")
    source = DataSource.objects.create(
        name="Demo CSV",
        source_type=DataSource.SourceType.FILE,
        config={"path": customers_csv},
        owner=user,
    )
    return Pipeline.objects.create(
        name="Demo Ingest",
        source=source,
        owner=user,
        config={
            "validation": {
                "rules": [
                    {"type": "required_columns", "columns": ["email"]},
                    {"type": "not_null", "columns": ["email"]},
                    {"type": "unique", "columns": ["email"]},
                ]
            },
            "transform": {},
            "target": "customers",
        },
    )


@pytest.mark.django_db
def test_saving_pipeline_with_schedule_creates_periodic_task(pipeline):
    pipeline.schedule = "*/2 * * * *"
    pipeline.save()

    task = PeriodicTask.objects.get(name=_periodic_task_name(pipeline))
    assert task.enabled is True
    assert task.task == "pipelines.run_pipeline_task"
    assert task.crontab.minute == "*/2"


@pytest.mark.django_db
def test_pause_disables_periodic_task_resume_reenables_it(pipeline):
    pipeline.schedule = "*/2 * * * *"
    pipeline.save()

    client = APIClient()
    client.force_authenticate(user=pipeline.owner)

    client.post(f"/api/pipelines/{pipeline.id}/pause/")
    task = PeriodicTask.objects.get(name=_periodic_task_name(pipeline))
    assert task.enabled is False

    client.post(f"/api/pipelines/{pipeline.id}/resume/")
    task.refresh_from_db()
    assert task.enabled is True


@pytest.mark.django_db
def test_clearing_schedule_removes_periodic_task(pipeline):
    pipeline.schedule = "*/2 * * * *"
    pipeline.save()
    assert PeriodicTask.objects.filter(name=_periodic_task_name(pipeline)).exists()

    pipeline.schedule = ""
    pipeline.save()
    assert not PeriodicTask.objects.filter(name=_periodic_task_name(pipeline)).exists()


@pytest.mark.django_db
def test_invalid_cron_expression_rejected_on_create(pipeline):
    client = APIClient()
    client.force_authenticate(user=pipeline.owner)

    response = client.post(
        "/api/pipelines/",
        {
            "name": "Bad Cron",
            "source": str(pipeline.source_id),
            "schedule": "not a cron",
            "config": {},
        },
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_periodic_task_fires_and_produces_a_successful_run(pipeline):
    """Simulates what celery beat does: invoke the task by name/kwargs on schedule."""
    pipeline.schedule = "*/2 * * * *"
    pipeline.save()
    task = PeriodicTask.objects.get(name=_periodic_task_name(pipeline))

    import json

    result = run_pipeline_task.apply(kwargs=json.loads(task.kwargs))
    run = PipelineRun.objects.get(pk=result.get())
    assert run.status == PipelineRun.Status.SUCCEEDED


@pytest.mark.django_db
def test_queue_view_lists_only_inflight_runs(pipeline):
    PipelineRun.objects.create(pipeline=pipeline, status=PipelineRun.Status.SUCCEEDED)
    inflight = PipelineRun.objects.create(
        pipeline=pipeline, status=PipelineRun.Status.RETRYING
    )

    client = APIClient()
    client.force_authenticate(user=pipeline.owner)
    response = client.get("/api/scheduler/queue/")

    assert response.status_code == 200
    ids = [row["id"] for row in response.data]
    assert ids == [str(inflight.id)]


@pytest.mark.django_db
def test_retry_failed_run_enqueues_a_new_run(pipeline):
    failed_run = execute_pipeline(pipeline)
    pipeline.config["validation"] = {
        "rules": [{"type": "required_columns", "columns": ["does_not_exist"]}]
    }
    pipeline.save()
    failed_run = execute_pipeline(pipeline)
    assert failed_run.status == PipelineRun.Status.FAILED

    pipeline.config["validation"] = {}
    pipeline.save()

    client = APIClient()
    client.force_authenticate(user=pipeline.owner)
    response = client.post(f"/api/scheduler/runs/{failed_run.id}/retry/")

    assert response.status_code == 202
    assert response.data["id"] != str(failed_run.id)
    assert response.data["status"] == "SUCCEEDED"


@pytest.mark.django_db
def test_retry_rejects_non_failed_run(pipeline):
    run = execute_pipeline(pipeline)
    assert run.status == PipelineRun.Status.SUCCEEDED

    client = APIClient()
    client.force_authenticate(user=pipeline.owner)
    response = client.post(f"/api/scheduler/runs/{run.id}/retry/")
    assert response.status_code == 400


@pytest.mark.django_db
def test_dead_letter_list_shows_exhausted_run(pipeline, monkeypatch):
    def always_fails(**kwargs):
        raise EtlError("boom")

    monkeypatch.setattr("apps.pipelines.services.engine.run", always_fails)
    result = run_pipeline_task.apply(kwargs={"pipeline_id": str(pipeline.id)})
    run_id = result.get()

    client = APIClient()
    client.force_authenticate(user=pipeline.owner)
    response = client.get("/api/scheduler/dead-letter/")

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["run"]["id"] == run_id
