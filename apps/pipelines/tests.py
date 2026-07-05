import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.datasources.models import DataSource
from apps.etl import engine
from apps.etl.exceptions import EtlError
from apps.warehouse.models import Customer

from .models import DeadLetterRecord, Pipeline, PipelineRun
from .services import execute_pipeline
from .tasks import run_pipeline_task

User = get_user_model()


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
                "required_columns": ["email"],
                "not_null": ["email"],
                "unique": ["email"],
            },
            "transform": {},
            "target": "customers",
        },
    )


@pytest.mark.django_db
def test_execute_pipeline_end_to_end_loads_warehouse(pipeline):
    run = execute_pipeline(pipeline)

    assert run.status == PipelineRun.Status.SUCCEEDED
    assert run.metrics["rows_extracted"] == 2
    assert run.metrics["created"] == 2
    assert Customer.objects.count() == 2
    assert Customer.objects.filter(email="ada@example.com").exists()


@pytest.mark.django_db
def test_execute_pipeline_records_failure_on_validation_error(pipeline):
    pipeline.config["validation"] = {"required_columns": ["does_not_exist"]}
    pipeline.save()

    run = execute_pipeline(pipeline)

    assert run.status == PipelineRun.Status.FAILED
    assert "does_not_exist" in run.error
    assert Customer.objects.count() == 0


@pytest.mark.django_db
def test_run_pipeline_via_api(pipeline):
    client = APIClient()
    client.force_authenticate(user=pipeline.owner)

    response = client.post(f"/api/pipelines/{pipeline.id}/run/")
    assert response.status_code == 202
    assert response.data["status"] == "SUCCEEDED"

    response = client.get("/api/pipelines/runs/")
    assert response.status_code == 200
    assert response.data["count"] == 1


@pytest.mark.django_db
def test_rerunning_a_pipeline_does_not_double_load(pipeline):
    execute_pipeline(pipeline)
    execute_pipeline(pipeline)

    assert Customer.objects.count() == 2
    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 2


@pytest.mark.django_db
def test_run_pipeline_task_retries_then_succeeds(pipeline, monkeypatch):
    calls = {"n": 0}
    real_run = engine.run

    def flaky_run(**kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise EtlError("transient failure")
        return real_run(**kwargs)

    monkeypatch.setattr("apps.pipelines.services.engine.run", flaky_run)

    result = run_pipeline_task.apply(kwargs={"pipeline_id": str(pipeline.id)})
    run = PipelineRun.objects.get(pk=result.get())

    assert calls["n"] == 3
    assert run.status == PipelineRun.Status.SUCCEEDED
    assert run.retry_count == 2
    assert not hasattr(run, "dead_letter")
    assert Customer.objects.count() == 2


@pytest.mark.django_db
def test_run_pipeline_task_exhausts_retries_and_dead_letters(pipeline, monkeypatch):
    def always_fails(**kwargs):
        raise EtlError("permanently broken")

    monkeypatch.setattr("apps.pipelines.services.engine.run", always_fails)

    result = run_pipeline_task.apply(kwargs={"pipeline_id": str(pipeline.id)})
    run = PipelineRun.objects.get(pk=result.get())

    assert run.status == PipelineRun.Status.FAILED
    assert run.retry_count == 3
    assert "permanently broken" in run.error
    assert run.traceback
    dead_letter = DeadLetterRecord.objects.get(run=run)
    assert dead_letter.error == run.error
    assert Customer.objects.count() == 0


@pytest.mark.django_db
def test_pause_and_resume_toggle_is_active(pipeline):
    client = APIClient()
    client.force_authenticate(user=pipeline.owner)

    response = client.post(f"/api/pipelines/{pipeline.id}/pause/")
    assert response.status_code == 200
    assert response.data["is_active"] is False
    pipeline.refresh_from_db()
    assert pipeline.is_active is False

    response = client.post(f"/api/pipelines/{pipeline.id}/resume/")
    assert response.status_code == 200
    assert response.data["is_active"] is True


@pytest.mark.django_db
def test_clone_creates_inactive_copy(pipeline):
    client = APIClient()
    client.force_authenticate(user=pipeline.owner)

    response = client.post(f"/api/pipelines/{pipeline.id}/clone/")
    assert response.status_code == 201
    assert response.data["is_active"] is False
    assert response.data["id"] != str(pipeline.id)
    assert Pipeline.objects.count() == 2
