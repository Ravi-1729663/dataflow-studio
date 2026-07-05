import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.datasources.models import DataSource
from apps.pipelines.models import Pipeline, PipelineRun
from apps.pipelines.services import execute_pipeline
from apps.warehouse.models import Customer

from .models import QualityScorecard

User = get_user_model()


@pytest.fixture
def csv_factory(tmp_path, settings):
    settings.BASE_DIR = tmp_path

    def _write(name: str, content: str) -> str:
        (tmp_path / name).write_text(content)
        return name

    return _write


@pytest.fixture
def user(db):
    return User.objects.create_user(username="engineer", password="pw12345678")


def _make_pipeline(user, path: str, rules: list) -> Pipeline:
    source = DataSource.objects.create(
        name="CSV",
        source_type=DataSource.SourceType.FILE,
        config={"path": path},
        owner=user,
    )
    return Pipeline.objects.create(
        name="Ingest",
        source=source,
        owner=user,
        config={
            "validation": {"rules": rules},
            "transform": {},
            "target": "customers",
        },
    )


CLEAN_CSV = (
    "customer_id,first_name,email\n1,Ada,ada@example.com\n2,Grace,grace@example.com\n"
)
# Duplicate row (id=2 twice, identical content) — lowers consistency without touching load-time
# uniqueness constraints (upsert on customer_id just updates the same row twice).
DIRTY_CSV = "customer_id,first_name,email\n1,Ada,ada@example.com\n2,Grace,grace@example.com\n2,Grace,grace@example.com\n"
# A genuinely missing value, used only for the blocking-failure test — validation runs before
# load, so the null email never reaches the warehouse's unique-email constraint.
NULL_EMAIL_CSV = "customer_id,first_name,email\n1,Ada,ada@example.com\n2,Grace,\n"

WARNING_RULES = [
    {"type": "required_columns", "columns": ["email"]},
    {"type": "unique", "columns": ["customer_id"], "severity": "warning"},
    {"type": "no_duplicate_rows", "severity": "warning"},
]
BLOCKING_RULES = [
    {"type": "required_columns", "columns": ["email"]},
    {"type": "not_null", "columns": ["email"]},
]


@pytest.mark.django_db
def test_dirty_data_produces_a_scorecard_with_a_numeric_score(csv_factory, user):
    path = csv_factory("dirty.csv", DIRTY_CSV)
    pipeline = _make_pipeline(user, path, WARNING_RULES)

    run = execute_pipeline(pipeline)

    assert run.status == PipelineRun.Status.SUCCEEDED
    scorecard = QualityScorecard.objects.get(run=run)
    assert isinstance(scorecard.overall_score, float)
    assert scorecard.overall_score < 100.0
    assert scorecard.consistency < 100.0  # the duplicate row shows up here
    assert scorecard.passed is True  # only warnings were configured, nothing blocking
    assert Customer.objects.count() == 2  # dirty rows still loaded — no blocking rule


@pytest.mark.django_db
def test_clean_data_scores_100(csv_factory, user):
    path = csv_factory("clean.csv", CLEAN_CSV)
    pipeline = _make_pipeline(user, path, BLOCKING_RULES)

    run = execute_pipeline(pipeline)

    scorecard = QualityScorecard.objects.get(run=run)
    assert scorecard.overall_score == 100.0
    assert scorecard.passed is True


@pytest.mark.django_db
def test_blocking_failure_stops_the_load_and_still_produces_a_scorecard(
    csv_factory, user
):
    path = csv_factory("null_email.csv", NULL_EMAIL_CSV)
    pipeline = _make_pipeline(user, path, BLOCKING_RULES)

    run = execute_pipeline(pipeline)

    assert run.status == PipelineRun.Status.FAILED
    assert Customer.objects.count() == 0
    scorecard = QualityScorecard.objects.get(run=run)
    assert scorecard.passed is False
    assert scorecard.overall_score < 100.0


@pytest.mark.django_db
def test_scorecard_history_and_trend_queryable_via_api(csv_factory, user):
    dirty_path = csv_factory("dirty.csv", DIRTY_CSV)
    clean_path = csv_factory("clean.csv", CLEAN_CSV)
    pipeline = _make_pipeline(user, dirty_path, WARNING_RULES)

    first_run = execute_pipeline(pipeline)  # dirty -> lower score

    pipeline.source.config = {"path": clean_path}
    pipeline.source.save()
    second_run = execute_pipeline(pipeline)  # clean -> 100

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get(
        "/api/validation/scorecards/", {"run__pipeline": str(pipeline.id)}
    )

    assert response.status_code == 200
    results = response.data["results"]
    assert [r["run"] for r in results] == [first_run.id, second_run.id]
    assert results[0]["score_delta"] is None
    assert results[1]["score_delta"] == round(
        results[1]["overall_score"] - results[0]["overall_score"], 2
    )
    assert results[1]["overall_score"] == 100.0


@pytest.mark.django_db
def test_scorecards_scoped_to_owner(csv_factory, user):
    other = User.objects.create_user(username="other", password="pw12345678")
    path = csv_factory("clean.csv", CLEAN_CSV)
    mine = _make_pipeline(user, path, BLOCKING_RULES)
    theirs = _make_pipeline(other, path, BLOCKING_RULES)
    execute_pipeline(mine)
    execute_pipeline(theirs)

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get("/api/validation/scorecards/")

    assert response.status_code == 200
    assert response.data["count"] == 1
