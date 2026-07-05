"""Seeds a demo user, datasource, and pipeline, then runs it end-to-end against sample_data/customers.csv."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.datasources.models import DataSource
from apps.pipelines.models import Pipeline, PipelineRun
from apps.pipelines.services import execute_pipeline

User = get_user_model()


class Command(BaseCommand):
    help = "Seed a demo user + datasource + pipeline and run it end-to-end."

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

        source, _ = DataSource.objects.get_or_create(
            name="Demo Customers CSV",
            owner=user,
            defaults={
                "source_type": DataSource.SourceType.FILE,
                "config": {"path": "sample_data/customers.csv"},
            },
        )
        self.stdout.write(self.style.SUCCESS(f"datasource: {source.name}"))

        pipeline, _ = Pipeline.objects.get_or_create(
            name="Demo Customer Ingest",
            owner=user,
            defaults={
                "source": source,
                "config": {
                    "validation": {
                        "required_columns": ["customer_id", "email"],
                        "not_null": ["email"],
                        "unique": ["email"],
                    },
                    "transform": {},
                    "target": "customers",
                },
            },
        )
        self.stdout.write(self.style.SUCCESS(f"pipeline: {pipeline.name}"))

        run = execute_pipeline(pipeline)
        if run.status == PipelineRun.Status.SUCCEEDED:
            self.stdout.write(
                self.style.SUCCESS(f"run {run.id}: {run.status} - {run.metrics}")
            )
        else:
            self.stdout.write(
                self.style.ERROR(f"run {run.id}: {run.status} - {run.error}")
            )
