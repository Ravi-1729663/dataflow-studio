"""Seeds a demo user, datasource, and pipeline, then runs it end-to-end against sample_data/customers.csv."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.datasources.models import DataSource
from apps.pipelines.models import Pipeline, PipelineRun
from apps.pipelines.services import execute_pipeline
from apps.workspaces import services as workspace_services
from apps.workspaces.models import Workspace

User = get_user_model()


class Command(BaseCommand):
    help = "Seed a demo user + workspace + datasource + pipeline and run it end-to-end."

    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(
            username="demo",
            defaults={"email": "demo@dataflowstudio.local", "role": User.Role.ENGINEER},
        )
        if created:
            user.set_password("demo-pass-123")
            user.save()
        self.stdout.write(
            self.style.SUCCESS(f"user: {user.username} (created={created})")
        )

        workspace = Workspace.objects.filter(memberships__user=user).first()
        if workspace is None:
            workspace = workspace_services.create_workspace(user, "Demo Workspace")
        self.stdout.write(self.style.SUCCESS(f"workspace: {workspace.name}"))

        source, _ = DataSource.objects.get_or_create(
            name="Demo Customers CSV",
            owner=user,
            defaults={
                "source_type": DataSource.SourceType.FILE,
                "config": {"path": "sample_data/customers.csv"},
                "workspace": workspace,
            },
        )
        self.stdout.write(self.style.SUCCESS(f"datasource: {source.name}"))

        pipeline, _ = Pipeline.objects.get_or_create(
            name="Demo Customer Ingest",
            owner=user,
            defaults={
                "source": source,
                "schedule": "*/2 * * * *",
                "config": {
                    "validation": {
                        "rules": [
                            {
                                "type": "required_columns",
                                "columns": ["customer_id", "email"],
                            },
                            {"type": "not_null", "columns": ["email"]},
                            {"type": "unique", "columns": ["email"]},
                            {"type": "no_duplicate_rows", "severity": "warning"},
                            {
                                "type": "allowed_values",
                                "column": "country",
                                "values": ["US", "UK"],
                                "severity": "warning",
                            },
                        ]
                    },
                    "transform": {},
                    "target": "customers",
                },
            },
        )
        self.stdout.write(
            self.style.SUCCESS(f"pipeline: {pipeline.name} (cron: {pipeline.schedule})")
        )

        run = execute_pipeline(pipeline)
        if run.status == PipelineRun.Status.SUCCEEDED:
            self.stdout.write(
                self.style.SUCCESS(f"run {run.id}: {run.status} - {run.metrics}")
            )
        else:
            self.stdout.write(
                self.style.ERROR(f"run {run.id}: {run.status} - {run.error}")
            )

        scorecard = getattr(run, "scorecard", None)
        if scorecard is not None:
            self.stdout.write(
                self.style.SUCCESS(
                    f"scorecard: overall={scorecard.overall_score} "
                    f"completeness={scorecard.completeness} consistency={scorecard.consistency} "
                    f"accuracy={scorecard.accuracy} passed={scorecard.passed}"
                )
            )
