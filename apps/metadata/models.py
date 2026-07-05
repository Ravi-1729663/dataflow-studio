from django.db import models

from apps.common.models import BaseModel
from apps.datasources.models import DataSource
from apps.pipelines.models import Pipeline, PipelineRun


class Dataset(BaseModel):
    """A logical target dataset in the warehouse/gold layer, e.g. "customers".

    Shared across every pipeline that targets it, just like the warehouse table it describes
    isn't owner-scoped — the catalog entry for a shared table is itself shared.
    """

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class SchemaVersion(BaseModel):
    """A point-in-time snapshot of a dataset's raw (bronze/source) schema, recorded on ingest."""

    dataset = models.ForeignKey(
        Dataset, on_delete=models.CASCADE, related_name="schema_versions"
    )
    run = models.ForeignKey(
        PipelineRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schema_versions",
    )
    version = models.PositiveIntegerField()
    columns = models.JSONField()
    added_columns = models.JSONField(default=list, blank=True)
    removed_columns = models.JSONField(default=list, blank=True)
    renamed_columns = models.JSONField(default=list, blank=True)
    is_drift = models.BooleanField(default=False)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["dataset", "version"], name="unique_dataset_schema_version"
            )
        ]

    def __str__(self) -> str:
        return f"{self.dataset.name} v{self.version}"


class ColumnMetadata(BaseModel):
    """The current column catalog for a dataset. ``created_at``/``updated_at`` double as
    first-seen/last-seen timestamps, so no separate fields are needed for that."""

    dataset = models.ForeignKey(
        Dataset, on_delete=models.CASCADE, related_name="columns_meta"
    )
    name = models.CharField(max_length=200)
    dtype = models.CharField(max_length=50)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["dataset", "name"], name="unique_dataset_column"
            )
        ]

    def __str__(self) -> str:
        return f"{self.dataset.name}.{self.name}"


class LineageNode(BaseModel):
    class Layer(models.TextChoices):
        SOURCE = "SOURCE", "Source"
        BRONZE = "BRONZE", "Bronze"
        SILVER = "SILVER", "Silver"
        GOLD = "GOLD", "Gold"

    layer = models.CharField(max_length=16, choices=Layer.choices)
    name = models.CharField(max_length=200)
    dataset = models.ForeignKey(
        Dataset,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="lineage_nodes",
    )
    data_source = models.ForeignKey(
        DataSource,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="lineage_nodes",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["layer", "name"], name="unique_lineage_node"
            )
        ]

    def __str__(self) -> str:
        return f"{self.layer}:{self.name}"


class LineageEdge(BaseModel):
    """One hop in a dataset's lineage graph, e.g. BRONZE:customers -> SILVER:customers.

    Scoped per-pipeline (not just per node pair) since more than one pipeline can feed the same
    shared bronze/silver/gold nodes — each keeps its own column mapping for provenance.
    """

    pipeline = models.ForeignKey(
        Pipeline, on_delete=models.CASCADE, related_name="lineage_edges"
    )
    from_node = models.ForeignKey(
        LineageNode, on_delete=models.CASCADE, related_name="outgoing_edges"
    )
    to_node = models.ForeignKey(
        LineageNode, on_delete=models.CASCADE, related_name="incoming_edges"
    )
    column_mapping = models.JSONField(default=list, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["pipeline", "from_node", "to_node"],
                name="unique_pipeline_lineage_edge",
            )
        ]

    def __str__(self) -> str:
        return f"{self.from_node} -> {self.to_node}"
