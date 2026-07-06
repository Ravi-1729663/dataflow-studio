import pytest
from django.contrib.auth import get_user_model
from prometheus_client import REGISTRY
from rest_framework.test import APIClient

from apps.datasources.models import DataSource
from apps.pipelines.models import Pipeline, PipelineRun
from apps.pipelines.services import execute_pipeline
from apps.workspaces.services import create_workspace

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="engineer", password="pw12345678")


@pytest.fixture
def pipeline(user, tmp_path, settings):
    settings.BASE_DIR = tmp_path
    (tmp_path / "customers.csv").write_text("customer_id,email\n1,a@x.com\n2,b@x.com\n")
    workspace = create_workspace(user, "Engineer Workspace")
    source = DataSource.objects.create(
        name="CSV",
        source_type=DataSource.SourceType.FILE,
        config={"path": "customers.csv"},
        owner=user,
        workspace=workspace,
    )
    return Pipeline.objects.create(
        name="Ingest",
        source=source,
        owner=user,
        config={"validation": {"rules": []}, "transform": {}, "target": "customers"},
    )


@pytest.mark.django_db
def test_dashboard_api_reports_aggregate_stats(pipeline, user):
    execute_pipeline(pipeline)
    PipelineRun.objects.create(
        pipeline=pipeline, status=PipelineRun.Status.FAILED, error="boom"
    )

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get("/api/v1/monitoring/dashboard/")

    assert response.status_code == 200
    data = response.data
    assert data["total_runs"] == 2
    assert data["succeeded"] == 1
    assert data["failed"] == 1
    assert data["success_rate_percent"] == 50.0
    assert data["avg_duration_seconds"] is not None
    assert len(data["failed_jobs"]) == 1
    assert data["failed_jobs"][0]["error"] == "boom"


@pytest.mark.django_db
def test_dashboard_scoped_to_owner(pipeline, user):
    other = User.objects.create_user(username="other", password="pw12345678")
    execute_pipeline(pipeline)

    client = APIClient()
    client.force_authenticate(user=other)
    response = client.get("/api/v1/monitoring/dashboard/")

    assert response.status_code == 200
    assert response.data["total_runs"] == 0


@pytest.mark.django_db
def test_metrics_endpoint_is_public_and_exposes_pipeline_metrics(pipeline):
    execute_pipeline(pipeline)

    client = APIClient()
    response = client.get("/metrics")

    assert response.status_code == 200
    body = response.content.decode()
    assert "dataflow_pipeline_runs_total" in body
    assert "dataflow_pipeline_run_duration_seconds" in body


@pytest.mark.django_db
def test_execute_pipeline_increments_prometheus_counters(pipeline):
    before = (
        REGISTRY.get_sample_value(
            "dataflow_pipeline_runs_total", {"status": "SUCCEEDED"}
        )
        or 0
    )
    before_rows = (
        REGISTRY.get_sample_value("dataflow_pipeline_rows_processed_total") or 0
    )

    execute_pipeline(pipeline)

    after = REGISTRY.get_sample_value(
        "dataflow_pipeline_runs_total", {"status": "SUCCEEDED"}
    )
    after_rows = REGISTRY.get_sample_value("dataflow_pipeline_rows_processed_total")
    assert after == before + 1
    assert after_rows == before_rows + 2


@pytest.mark.django_db
def test_failed_run_increments_failure_counter(pipeline):
    pipeline.config["validation"] = {
        "rules": [{"type": "required_columns", "columns": ["does_not_exist"]}]
    }
    pipeline.save()
    before = (
        REGISTRY.get_sample_value("dataflow_pipeline_runs_total", {"status": "FAILED"})
        or 0
    )

    execute_pipeline(pipeline)

    after = REGISTRY.get_sample_value(
        "dataflow_pipeline_runs_total", {"status": "FAILED"}
    )
    assert after == before + 1
