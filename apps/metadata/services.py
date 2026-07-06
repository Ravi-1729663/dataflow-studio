"""Bridges a successful pipeline run to the metadata catalog: dataset registry, schema history
with drift detection, table/column lineage, and the bronze/silver/gold Parquet layers.

Called from pipelines.services.execute_attempt — the same "bridge a Django model to engine output"
role that app already plays for the warehouse loader and the validation scorecard.
"""

import logging

import pandas as pd
from django.db.models import Q

from apps.pipelines.models import Pipeline, PipelineRun
from apps.warehouse.services import get_dataframe as _get_customers_dataframe

from . import medallion
from .models import (
    ColumnAnomaly,
    ColumnMetadata,
    ColumnStats,
    Dataset,
    LineageEdge,
    LineageNode,
    SchemaVersion,
)

logger = logging.getLogger("dataflow.metadata")

# A z-score check needs some history before it means anything; below this many accumulated
# samples (rows, across however many runs it took to reach that) a column is still establishing
# its baseline, not yet eligible to be flagged.
ANOMALY_MIN_BASELINE_SAMPLES = 3
ANOMALY_Z_THRESHOLD = 3.0

# Maps a Dataset name (== a pipeline's config["target"]) to the callable that snapshots its
# current gold-layer state. Extend this as more warehouse targets land. "customers" and
# "customers_scd2" are different targets/loaders (Type 1 vs Type 2) over the same underlying
# table, so they share the same current-rows snapshot.
_GOLD_SNAPSHOT_SOURCES = {
    "customers": _get_customers_dataframe,
    "customers_scd2": _get_customers_dataframe,
}


def register_dataset(pipeline: Pipeline) -> Dataset:
    name = pipeline.config.get("target", pipeline.name)
    dataset, _ = Dataset.objects.get_or_create(name=name)
    return dataset


def _columns_of(df: pd.DataFrame) -> list[dict]:
    return [{"name": column, "dtype": str(df[column].dtype)} for column in df.columns]


def _sync_column_metadata(dataset: Dataset, columns: list[dict]) -> None:
    for column in columns:
        ColumnMetadata.objects.update_or_create(
            dataset=dataset,
            name=column["name"],
            defaults={"dtype": column["dtype"]},
        )


def record_schema(
    dataset: Dataset, run: PipelineRun, raw_df: pd.DataFrame, rename_map: dict
) -> SchemaVersion:
    """Record the bronze/raw schema for this run, flagging drift against the previous version.

    A column that both disappeared and reappeared under the name the pipeline's transform config
    renames it to is recorded as a rename, not an unrelated add/drop pair.
    """
    columns = _columns_of(raw_df)
    latest = dataset.schema_versions.order_by("-version").first()

    if latest is None:
        version = SchemaVersion.objects.create(
            dataset=dataset, run=run, version=1, columns=columns
        )
        _sync_column_metadata(dataset, columns)
        logger.info(
            "schema baseline recorded", extra={"dataset": dataset.name, "version": 1}
        )
        return version

    _sync_column_metadata(dataset, columns)

    latest_names = {c["name"] for c in latest.columns}
    current_names = {c["name"] for c in columns}
    if latest_names == current_names:
        return latest

    removed = latest_names - current_names
    added = current_names - latest_names
    renamed = []
    for old_name, new_name in (rename_map or {}).items():
        if old_name in removed and new_name in added:
            renamed.append({"from": old_name, "to": new_name})
            removed.discard(old_name)
            added.discard(new_name)

    version = SchemaVersion.objects.create(
        dataset=dataset,
        run=run,
        version=latest.version + 1,
        columns=columns,
        added_columns=sorted(added),
        removed_columns=sorted(removed),
        renamed_columns=renamed,
        is_drift=True,
    )
    logger.warning(
        "schema drift detected",
        extra={
            "dataset": dataset.name,
            "version": version.version,
            "added": sorted(added),
            "removed": sorted(removed),
            "renamed": renamed,
        },
    )
    return version


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def detect_anomalies(
    dataset: Dataset, run: PipelineRun, df: pd.DataFrame
) -> list[ColumnAnomaly]:
    """Flags this run's mean for each numeric column as an anomaly if it's more than
    ``ANOMALY_Z_THRESHOLD`` standard deviations from that column's running baseline, then folds
    this run's batch into the baseline regardless (so the baseline keeps adapting even when
    nothing is flagged). The baseline itself (``ColumnStats``) is updated via Welford's parallel
    algorithm — merging a new batch's (count, mean, variance) into a running aggregate — rather
    than storing every run's raw values, so this stays O(columns) in space no matter how many
    runs a dataset has seen.
    """
    anomalies = []
    for column in _numeric_columns(df):
        values = df[column].dropna()
        if values.empty:
            continue

        batch_count = len(values)
        batch_mean = float(values.mean())
        batch_variance = float(values.var(ddof=0)) if batch_count > 1 else 0.0

        stats, _ = ColumnStats.objects.get_or_create(dataset=dataset, column=column)

        if stats.count >= ANOMALY_MIN_BASELINE_SAMPLES and stats.stddev > 0:
            z_score = (batch_mean - stats.mean) / stats.stddev
            if abs(z_score) > ANOMALY_Z_THRESHOLD:
                anomaly = ColumnAnomaly.objects.create(
                    dataset=dataset,
                    run=run,
                    column=column,
                    value=batch_mean,
                    baseline_mean=stats.mean,
                    baseline_stddev=stats.stddev,
                    z_score=z_score,
                )
                anomalies.append(anomaly)
                logger.warning(
                    "statistical anomaly detected",
                    extra={
                        "dataset": dataset.name,
                        "column": column,
                        "value": batch_mean,
                        "baseline_mean": stats.mean,
                        "baseline_stddev": stats.stddev,
                        "z_score": z_score,
                    },
                )

        new_count = stats.count + batch_count
        delta = batch_mean - stats.mean
        new_mean = stats.mean + delta * batch_count / new_count
        new_m2 = (
            stats.m2
            + batch_variance * batch_count
            + delta**2 * stats.count * batch_count / new_count
        )

        stats.count = new_count
        stats.mean = new_mean
        stats.m2 = new_m2
        stats.save(update_fields=["count", "mean", "m2", "updated_at"])

    return anomalies


def sync_lineage(pipeline: Pipeline, dataset: Dataset, rename_map: dict) -> None:
    """Ensure SOURCE -> BRONZE -> SILVER -> GOLD nodes + edges exist for this pipeline."""
    source = pipeline.source
    source_node, _ = LineageNode.objects.get_or_create(
        layer=LineageNode.Layer.SOURCE,
        name=source.name,
        defaults={"data_source": source},
    )
    bronze_node, _ = LineageNode.objects.get_or_create(
        layer=LineageNode.Layer.BRONZE, name=dataset.name, defaults={"dataset": dataset}
    )
    silver_node, _ = LineageNode.objects.get_or_create(
        layer=LineageNode.Layer.SILVER, name=dataset.name, defaults={"dataset": dataset}
    )
    gold_node, _ = LineageNode.objects.get_or_create(
        layer=LineageNode.Layer.GOLD, name=dataset.name, defaults={"dataset": dataset}
    )

    LineageEdge.objects.update_or_create(
        pipeline=pipeline,
        from_node=source_node,
        to_node=bronze_node,
        defaults={"column_mapping": []},
    )
    rename_pairs = [{"from": old, "to": new} for old, new in (rename_map or {}).items()]
    LineageEdge.objects.update_or_create(
        pipeline=pipeline,
        from_node=bronze_node,
        to_node=silver_node,
        defaults={"column_mapping": rename_pairs},
    )
    LineageEdge.objects.update_or_create(
        pipeline=pipeline,
        from_node=silver_node,
        to_node=gold_node,
        defaults={"column_mapping": []},
    )


def get_lineage_graph(dataset: Dataset) -> dict:
    """The full graph feeding a dataset, across every pipeline that contributes to it."""
    edges = list(
        LineageEdge.objects.filter(
            Q(from_node__dataset=dataset) | Q(to_node__dataset=dataset)
        )
        .select_related("from_node", "to_node", "pipeline")
        .distinct()
    )
    layer_order = {layer: index for index, layer in enumerate(LineageNode.Layer.values)}

    nodes_by_key = {}
    for edge in edges:
        nodes_by_key[(edge.from_node.layer, edge.from_node.name)] = edge.from_node
        nodes_by_key[(edge.to_node.layer, edge.to_node.name)] = edge.to_node
    ordered_nodes = sorted(nodes_by_key.values(), key=lambda n: layer_order[n.layer])

    return {
        "dataset": dataset.name,
        "nodes": [{"layer": n.layer, "name": n.name} for n in ordered_nodes],
        "edges": [
            {
                "pipeline": edge.pipeline.name,
                "from": {"layer": edge.from_node.layer, "name": edge.from_node.name},
                "to": {"layer": edge.to_node.layer, "name": edge.to_node.name},
                "column_mapping": edge.column_mapping,
            }
            for edge in sorted(edges, key=lambda e: layer_order[e.from_node.layer])
        ],
    }


def _gold_snapshot(dataset: Dataset) -> pd.DataFrame | None:
    source = _GOLD_SNAPSHOT_SOURCES.get(dataset.name)
    return source() if source else None


def record_ingest(
    pipeline: Pipeline,
    run: PipelineRun,
    raw_df: pd.DataFrame,
    transformed_df: pd.DataFrame,
) -> Dataset:
    """Catalog + lineage + medallion bookkeeping for one successful run. Only called on success —
    a run a blocking validation rule stopped never reached a state worth cataloging."""
    dataset = register_dataset(pipeline)
    rename_map = pipeline.config.get("transform", {}).get("rename", {})

    record_schema(dataset, run, raw_df, rename_map)
    detect_anomalies(dataset, run, raw_df)
    sync_lineage(pipeline, dataset, rename_map)

    partition_date = (run.started_at or run.created_at).date()
    medallion.write_layer("BRONZE", dataset.name, raw_df, str(run.id), partition_date)
    medallion.write_layer(
        "SILVER", dataset.name, transformed_df, str(run.id), partition_date
    )
    gold_df = _gold_snapshot(dataset)
    if gold_df is not None:
        medallion.write_layer(
            "GOLD", dataset.name, gold_df, str(run.id), partition_date
        )

    return dataset
