import logging

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.common.logging import CorrelationIdFilter
from apps.datasources.models import DataSource
from apps.etl import engine
from apps.etl.exceptions import EtlError
from apps.warehouse.models import Customer
from apps.workspaces.services import create_workspace

from .models import DeadLetterRecord, Pipeline, PipelineRun, PipelineWatermark
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
    workspace = create_workspace(user, "Engineer Workspace")
    source = DataSource.objects.create(
        name="Demo CSV",
        source_type=DataSource.SourceType.FILE,
        config={"path": customers_csv},
        owner=user,
        workspace=workspace,
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
def test_execute_pipeline_end_to_end_loads_warehouse(pipeline):
    run = execute_pipeline(pipeline)

    assert run.status == PipelineRun.Status.SUCCEEDED
    assert run.metrics["rows_extracted"] == 2
    assert run.metrics["created"] == 2
    assert Customer.objects.count() == 2
    assert Customer.objects.filter(email="ada@example.com").exists()
    assert run.scorecard.overall_score == 100.0
    assert run.scorecard.passed is True


@pytest.mark.django_db
def test_execute_pipeline_records_failure_on_validation_error(pipeline):
    pipeline.config["validation"] = {
        "rules": [{"type": "required_columns", "columns": ["does_not_exist"]}]
    }
    pipeline.save()

    run = execute_pipeline(pipeline)

    assert run.status == PipelineRun.Status.FAILED
    assert "does_not_exist" in run.error
    assert Customer.objects.count() == 0
    assert run.scorecard.passed is False


@pytest.mark.django_db
def test_run_pipeline_via_api(pipeline):
    client = APIClient()
    client.force_authenticate(user=pipeline.owner)

    response = client.post(f"/api/v1/pipelines/{pipeline.id}/run/")
    assert response.status_code == 202
    assert response.data["status"] == "SUCCEEDED"

    response = client.get("/api/v1/pipelines/runs/")
    assert response.status_code == 200
    assert response.data["count"] == 1


@pytest.mark.django_db
def test_run_with_idempotency_key_is_not_triggered_twice(pipeline):
    client = APIClient()
    client.force_authenticate(user=pipeline.owner)

    first = client.post(
        f"/api/v1/pipelines/{pipeline.id}/run/", HTTP_IDEMPOTENCY_KEY="retry-abc123"
    )
    second = client.post(
        f"/api/v1/pipelines/{pipeline.id}/run/", HTTP_IDEMPOTENCY_KEY="retry-abc123"
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.data["id"] == second.data["id"]  # replayed, not a second run
    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 1


@pytest.mark.django_db
def test_run_without_idempotency_key_triggers_every_time(pipeline):
    client = APIClient()
    client.force_authenticate(user=pipeline.owner)

    client.post(f"/api/v1/pipelines/{pipeline.id}/run/")
    client.post(f"/api/v1/pipelines/{pipeline.id}/run/")

    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 2


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

    response = client.post(f"/api/v1/pipelines/{pipeline.id}/pause/")
    assert response.status_code == 200
    assert response.data["is_active"] is False
    pipeline.refresh_from_db()
    assert pipeline.is_active is False

    response = client.post(f"/api/v1/pipelines/{pipeline.id}/resume/")
    assert response.status_code == 200
    assert response.data["is_active"] is True


@pytest.mark.django_db
def test_clone_creates_inactive_copy(pipeline):
    client = APIClient()
    client.force_authenticate(user=pipeline.owner)

    response = client.post(f"/api/v1/pipelines/{pipeline.id}/clone/")
    assert response.status_code == 201
    assert response.data["is_active"] is False
    assert response.data["id"] != str(pipeline.id)
    assert Pipeline.objects.count() == 2


@pytest.mark.django_db
def test_run_id_correlates_logs_from_an_unrelated_app(pipeline):
    """apps.warehouse.services logs "customers upserted" with no run_id of its own — the
    correlation id filter should tag it anyway, purely from execution context. Uses a plain
    in-process collector handler (with the real filter attached) rather than capturing stderr,
    since stream buffering makes fd-level capture timing-sensitive."""
    records = []

    class _Collector(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Collector()
    handler.addFilter(CorrelationIdFilter())
    warehouse_logger = logging.getLogger("dataflow.warehouse")
    warehouse_logger.addHandler(handler)
    try:
        run = execute_pipeline(pipeline)
    finally:
        warehouse_logger.removeHandler(handler)

    assert records
    assert all(getattr(record, "run_id", None) == str(run.id) for record in records)


@pytest.mark.django_db
def test_failed_run_traceback_pinpoints_the_failing_step(pipeline):
    pipeline.config["validation"] = {
        "rules": [{"type": "required_columns", "columns": ["does_not_exist"]}]
    }
    pipeline.save()

    run = execute_pipeline(pipeline)

    assert run.status == PipelineRun.Status.FAILED
    assert "apps/etl/validate.py" in run.traceback.replace("\\", "/")
    assert "ValidationFailed" in run.traceback


# ---- incremental / watermark ------------------------------------------------------------------


@pytest.mark.django_db
def test_incremental_pipeline_second_run_only_loads_the_delta(tmp_path, settings):
    settings.BASE_DIR = tmp_path
    csv_path = tmp_path / "customers.csv"
    csv_path.write_text(
        "customer_id,email,updated_at\n"
        "1,ada@example.com,2024-01-01\n"
        "2,grace@example.com,2024-01-02\n"
    )
    user = User.objects.create_user(
        username="incremental-engineer", password="pw12345678"
    )
    workspace = create_workspace(user, "Incremental Workspace")
    source = DataSource.objects.create(
        name="Incremental CSV",
        source_type=DataSource.SourceType.FILE,
        config={"path": "customers.csv"},
        owner=user,
        workspace=workspace,
    )
    pipeline_obj = Pipeline.objects.create(
        name="Incremental Ingest",
        source=source,
        owner=user,
        config={
            "validation": {
                "rules": [{"type": "required_columns", "columns": ["email"]}]
            },
            "transform": {},
            "target": "customers",
            "incremental": {"column": "updated_at"},
        },
    )

    first_run = execute_pipeline(pipeline_obj)
    assert first_run.status == PipelineRun.Status.SUCCEEDED
    assert first_run.metrics["rows_extracted"] == 2
    assert first_run.metrics["rows_loaded"] == 2
    assert Customer.objects.count() == 2
    watermark = PipelineWatermark.objects.get(pipeline=pipeline_obj)
    assert watermark.value == "2024-01-02"

    # The source gains a new row (a real-world "delta") since the last run.
    csv_path.write_text(
        "customer_id,email,updated_at\n"
        "1,ada@example.com,2024-01-01\n"
        "2,grace@example.com,2024-01-02\n"
        "3,kay@example.com,2024-01-03\n"
    )

    second_run = execute_pipeline(pipeline_obj)
    assert second_run.status == PipelineRun.Status.SUCCEEDED
    assert second_run.metrics["rows_extracted"] == 3  # raw pull from the source
    assert second_run.metrics["rows_loaded"] == 1  # only the new row
    assert second_run.metrics["created"] == 1
    assert Customer.objects.count() == 3
    watermark.refresh_from_db()
    assert watermark.value == "2024-01-03"


@pytest.mark.django_db
def test_pipeline_without_incremental_config_never_creates_a_watermark(pipeline):
    execute_pipeline(pipeline)
    assert not PipelineWatermark.objects.filter(pipeline=pipeline).exists()


# ---- SCD Type 2 ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_scd2_target_pipeline_keeps_history_across_runs(tmp_path, settings):
    settings.BASE_DIR = tmp_path
    csv_path = tmp_path / "customers.csv"
    csv_path.write_text("customer_id,email,country\n1,ada@example.com,UK\n")
    user = User.objects.create_user(username="scd2-engineer", password="pw12345678")
    workspace = create_workspace(user, "SCD2 Workspace")
    source = DataSource.objects.create(
        name="SCD2 CSV",
        source_type=DataSource.SourceType.FILE,
        config={"path": "customers.csv"},
        owner=user,
        workspace=workspace,
    )
    pipeline_obj = Pipeline.objects.create(
        name="SCD2 Ingest",
        source=source,
        owner=user,
        config={
            "validation": {
                "rules": [{"type": "required_columns", "columns": ["email"]}]
            },
            "transform": {},
            "target": "customers_scd2",
        },
    )

    first_run = execute_pipeline(pipeline_obj)
    assert first_run.status == PipelineRun.Status.SUCCEEDED
    assert Customer.objects.filter(external_id="1").count() == 1

    csv_path.write_text("customer_id,email,country\n1,ada@example.com,US\n")
    second_run = execute_pipeline(pipeline_obj)

    assert second_run.status == PipelineRun.Status.SUCCEEDED
    versions = list(Customer.objects.filter(external_id="1").order_by("valid_from"))
    assert len(versions) == 2
    old, new = versions
    assert old.is_current is False
    assert old.valid_to is not None
    assert old.country == "UK"
    assert new.is_current is True
    assert new.valid_to is None
    assert new.country == "US"
