import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.datasources.models import DataSource
from apps.warehouse.models import Customer

from .models import Pipeline, PipelineRun
from .services import execute_pipeline

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
