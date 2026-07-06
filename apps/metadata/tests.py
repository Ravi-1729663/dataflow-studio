import pandas as pd
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.datasources.models import DataSource
from apps.pipelines.models import Pipeline, PipelineRun
from apps.pipelines.services import execute_pipeline
from apps.warehouse.models import Customer

from . import medallion, services
from .models import ColumnMetadata, Dataset, LineageEdge, LineageNode, SchemaVersion

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="engineer", password="pw12345678")


def _make_pipeline(user, path: str, rename: dict | None = None) -> Pipeline:
    source = DataSource.objects.create(
        name=f"CSV ({path})",
        source_type=DataSource.SourceType.FILE,
        config={"path": path},
        owner=user,
    )
    return Pipeline.objects.create(
        name="Ingest",
        source=source,
        owner=user,
        config={
            "validation": {
                "rules": [{"type": "required_columns", "columns": ["email"]}]
            },
            "transform": {"rename": rename or {}},
            "target": "customers",
        },
    )


@pytest.fixture
def pipeline(db, user):
    return _make_pipeline(user, "unused.csv")


# ---- register_dataset ------------------------------------------------------------------------


@pytest.mark.django_db
def test_register_dataset_is_shared_across_pipelines_with_the_same_target(user):
    pipeline_a = _make_pipeline(user, "a.csv")
    pipeline_b = _make_pipeline(user, "b.csv")

    dataset_a = services.register_dataset(pipeline_a)
    dataset_b = services.register_dataset(pipeline_b)

    assert dataset_a.id == dataset_b.id
    assert dataset_a.name == "customers"


# ---- record_schema / drift detection ----------------------------------------------------------


@pytest.mark.django_db
def test_record_schema_creates_baseline_version(pipeline):
    dataset = services.register_dataset(pipeline)
    df = pd.DataFrame({"customer_id": [1, 2], "email": ["a@x.com", "b@x.com"]})

    version = services.record_schema(dataset, run=None, raw_df=df, rename_map={})

    assert version.version == 1
    assert version.is_drift is False
    assert {c["name"] for c in version.columns} == {"customer_id", "email"}
    assert ColumnMetadata.objects.filter(dataset=dataset).count() == 2


@pytest.mark.django_db
def test_record_schema_unchanged_columns_do_not_create_a_new_version(pipeline):
    dataset = services.register_dataset(pipeline)
    df = pd.DataFrame({"customer_id": [1], "email": ["a@x.com"]})
    services.record_schema(dataset, run=None, raw_df=df, rename_map={})

    same_shape_df = pd.DataFrame({"customer_id": [3], "email": ["c@x.com"]})
    version = services.record_schema(
        dataset, run=None, raw_df=same_shape_df, rename_map={}
    )

    assert version.version == 1
    assert SchemaVersion.objects.filter(dataset=dataset).count() == 1


@pytest.mark.django_db
def test_record_schema_detects_an_added_column(pipeline):
    dataset = services.register_dataset(pipeline)
    services.record_schema(
        dataset,
        run=None,
        raw_df=pd.DataFrame({"customer_id": [1], "email": ["a@x.com"]}),
        rename_map={},
    )

    with_country = pd.DataFrame(
        {"customer_id": [1], "email": ["a@x.com"], "country": ["UK"]}
    )
    version = services.record_schema(
        dataset, run=None, raw_df=with_country, rename_map={}
    )

    assert version.version == 2
    assert version.is_drift is True
    assert version.added_columns == ["country"]
    assert version.removed_columns == []
    assert version.renamed_columns == []


@pytest.mark.django_db
def test_record_schema_detects_a_rename_using_the_transform_rename_map(pipeline):
    dataset = services.register_dataset(pipeline)
    services.record_schema(
        dataset,
        run=None,
        raw_df=pd.DataFrame({"cust_id": [1], "email": ["a@x.com"]}),
        rename_map={},
    )

    renamed_df = pd.DataFrame({"customer_id": [1], "email": ["a@x.com"]})
    version = services.record_schema(
        dataset, run=None, raw_df=renamed_df, rename_map={"cust_id": "customer_id"}
    )

    assert version.is_drift is True
    assert version.renamed_columns == [{"from": "cust_id", "to": "customer_id"}]
    assert version.added_columns == []
    assert version.removed_columns == []


# ---- lineage ------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_sync_lineage_creates_the_full_source_to_gold_graph(pipeline):
    dataset = services.register_dataset(pipeline)

    services.sync_lineage(pipeline, dataset, rename_map={"cust_id": "customer_id"})

    assert LineageNode.objects.count() == 4
    assert LineageEdge.objects.filter(pipeline=pipeline).count() == 3
    bronze_to_silver = LineageEdge.objects.get(
        from_node__layer=LineageNode.Layer.BRONZE,
        to_node__layer=LineageNode.Layer.SILVER,
    )
    assert bronze_to_silver.column_mapping == [{"from": "cust_id", "to": "customer_id"}]


@pytest.mark.django_db
def test_get_lineage_graph_is_resolvable_and_ordered(pipeline):
    dataset = services.register_dataset(pipeline)
    services.sync_lineage(pipeline, dataset, rename_map={})

    graph = services.get_lineage_graph(dataset)

    assert graph["dataset"] == "customers"
    assert [n["layer"] for n in graph["nodes"]] == [
        "SOURCE",
        "BRONZE",
        "SILVER",
        "GOLD",
    ]
    assert len(graph["edges"]) == 3
    assert graph["edges"][0]["from"]["layer"] == "SOURCE"
    assert graph["edges"][-1]["to"]["layer"] == "GOLD"


@pytest.mark.django_db
def test_lineage_graph_merges_multiple_pipelines_feeding_the_same_dataset(user):
    pipeline_a = _make_pipeline(user, "a.csv")
    pipeline_b = _make_pipeline(user, "b.csv")
    dataset = services.register_dataset(pipeline_a)
    services.register_dataset(pipeline_b)  # same "customers" target -> same dataset

    services.sync_lineage(pipeline_a, dataset, rename_map={})
    services.sync_lineage(pipeline_b, dataset, rename_map={})

    graph = services.get_lineage_graph(dataset)
    source_nodes = [n for n in graph["nodes"] if n["layer"] == "SOURCE"]
    assert len(source_nodes) == 2  # two distinct sources, one shared bronze/silver/gold


# ---- medallion Parquet + DuckDB ------------------------------------------------------------------


@pytest.mark.django_db
def test_medallion_write_and_query_round_trip(settings, tmp_path):
    settings.BASE_DIR = tmp_path
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})

    medallion.write_layer("BRONZE", "widgets", df, run_id="run-1")
    rows = medallion.query_layer("BRONZE", "widgets")

    assert len(rows) == 2
    assert {r["a"] for r in rows} == {1, 2}


@pytest.mark.django_db
def test_medallion_query_returns_empty_list_when_no_files_written(settings, tmp_path):
    settings.BASE_DIR = tmp_path
    assert medallion.query_layer("GOLD", "does-not-exist") == []


@pytest.mark.django_db
def test_medallion_gold_query_only_reads_the_latest_snapshot(settings, tmp_path):
    settings.BASE_DIR = tmp_path
    medallion.write_layer("GOLD", "widgets", pd.DataFrame({"a": [1]}), run_id="run-1")
    medallion.write_layer("GOLD", "widgets", pd.DataFrame({"a": [2]}), run_id="run-2")

    rows = medallion.query_layer("GOLD", "widgets")

    assert len(rows) == 1
    assert rows[0]["a"] == 2


# ---- end-to-end via a real pipeline run --------------------------------------------------------


@pytest.mark.django_db
def test_end_to_end_run_populates_catalog_lineage_and_medallion_layers(
    tmp_path, settings, user
):
    settings.BASE_DIR = tmp_path
    (tmp_path / "customers.csv").write_text(
        "customer_id,first_name,email,country\n"
        "1,Ada,ada@example.com,UK\n"
        "2,Grace,grace@example.com,US\n"
    )
    pipeline = _make_pipeline(user, "customers.csv")

    run = execute_pipeline(pipeline)

    assert run.status == PipelineRun.Status.SUCCEEDED
    dataset = Dataset.objects.get(name="customers")
    assert dataset.schema_versions.count() == 1
    assert LineageEdge.objects.filter(pipeline=pipeline).count() == 3

    gold_rows = medallion.query_layer("GOLD", "customers")
    assert {r["email"] for r in gold_rows} == set(
        Customer.objects.values_list("email", flat=True)
    )

    bronze_rows = medallion.query_layer("BRONZE", "customers")
    assert len(bronze_rows) == 2


@pytest.mark.django_db
def test_schema_drift_flagged_across_two_runs_with_a_source_schema_change(
    tmp_path, settings, user
):
    settings.BASE_DIR = tmp_path
    (tmp_path / "customers.csv").write_text(
        "customer_id,first_name,email\n1,Ada,ada@example.com\n"
    )
    pipeline = _make_pipeline(user, "customers.csv")
    execute_pipeline(pipeline)

    (tmp_path / "customers.csv").write_text(
        "customer_id,first_name,email,country\n1,Ada,ada@example.com,UK\n"
    )
    execute_pipeline(pipeline)

    dataset = Dataset.objects.get(name="customers")
    versions = list(dataset.schema_versions.order_by("version"))
    assert len(versions) == 2
    assert versions[0].is_drift is False
    assert versions[1].is_drift is True
    assert versions[1].added_columns == ["country"]


# ---- API ------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_lineage_api_returns_the_graph_for_any_warehouse_table(
    tmp_path, settings, user
):
    settings.BASE_DIR = tmp_path
    (tmp_path / "customers.csv").write_text("customer_id,email\n1,a@x.com\n")
    pipeline = _make_pipeline(user, "customers.csv")
    execute_pipeline(pipeline)

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get("/api/v1/metadata/datasets/customers/lineage/")

    assert response.status_code == 200
    assert response.data["dataset"] == "customers"
    assert len(response.data["nodes"]) == 4


@pytest.mark.django_db
def test_medallion_api_returns_rows_and_rejects_unknown_layer(tmp_path, settings, user):
    settings.BASE_DIR = tmp_path
    (tmp_path / "customers.csv").write_text("customer_id,email\n1,a@x.com\n")
    pipeline = _make_pipeline(user, "customers.csv")
    execute_pipeline(pipeline)

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/api/v1/metadata/datasets/customers/medallion/gold/")
    assert response.status_code == 200
    assert response.data["row_count"] == 1

    response = client.get("/api/v1/metadata/datasets/customers/medallion/platinum/")
    assert response.status_code == 400


@pytest.mark.django_db
def test_schema_versions_api_lists_history(tmp_path, settings, user):
    settings.BASE_DIR = tmp_path
    (tmp_path / "customers.csv").write_text("customer_id,email\n1,a@x.com\n")
    pipeline = _make_pipeline(user, "customers.csv")
    execute_pipeline(pipeline)

    (tmp_path / "customers.csv").write_text("customer_id,email,country\n1,a@x.com,UK\n")
    execute_pipeline(pipeline)

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get(
        "/api/v1/metadata/schema-versions/", {"dataset__name": "customers"}
    )

    assert response.status_code == 200
    assert response.data["count"] == 2
    assert any(row["is_drift"] for row in response.data["results"])
