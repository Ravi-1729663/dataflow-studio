"""Locust load test (v0.9) against the live REST API. Each simulated user registers its own
account so per-user rate limiting (v0.7) doesn't make every virtual user share one throttle
bucket, then exercises the same loop a real engineer would: create a workspace, register a data
source, build a pipeline, run it, and poll the dashboard/scorecards — the same calls the React
SPA makes (see frontend/src/lib/resources.ts).

Run against the full docker-compose stack (Postgres + Redis + a real Celery worker), not
`manage.py runserver` — see loadtest/README.md for the exact invocation and why.
"""

import uuid

from locust import HttpUser, between, task

CSV_PATH = "sample_data/customers.csv"


class DataFlowUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        username = f"loadtest_{uuid.uuid4().hex[:12]}"
        password = "loadtest-pw-123"

        self.client.post(
            "/api/v1/auth/register/",
            json={
                "username": username,
                "email": f"{username}@example.com",
                "password": password,
            },
            name="/auth/register/",
        )
        response = self.client.post(
            "/api/v1/auth/token/",
            json={"username": username, "password": password},
            name="/auth/token/",
        )
        access = response.json()["access"]
        self.client.headers.update({"Authorization": f"Bearer {access}"})

        workspace = self.client.post(
            "/api/v1/workspaces/",
            json={"name": f"Load test {username}"},
            name="/workspaces/",
        ).json()
        self.workspace_id = workspace["id"]

        source = self.client.post(
            "/api/v1/datasources/",
            json={
                "name": "Load test CSV",
                "source_type": "FILE",
                "config": {"path": CSV_PATH},
                "workspace": self.workspace_id,
            },
            name="/datasources/",
        ).json()

        pipeline = self.client.post(
            "/api/v1/pipelines/",
            json={
                "name": "Load test pipeline",
                "source": source["id"],
                "schedule": "",
                "config": {
                    "validation": {
                        "rules": [{"type": "required_columns", "columns": ["email"]}]
                    },
                    "transform": {},
                    "target": "customers",
                },
            },
            name="/pipelines/",
        ).json()
        self.pipeline_id = pipeline["id"]

    @task(5)
    def list_datasources(self):
        self.client.get(
            f"/api/v1/datasources/?workspace={self.workspace_id}",
            name="/datasources/?workspace=[id]",
        )

    @task(5)
    def list_pipelines(self):
        self.client.get(
            f"/api/v1/pipelines/?workspace={self.workspace_id}",
            name="/pipelines/?workspace=[id]",
        )

    @task(3)
    def dashboard(self):
        self.client.get("/api/v1/monitoring/dashboard/")

    @task(2)
    def scorecards(self):
        self.client.get(
            f"/api/v1/validation/scorecards/?run__pipeline={self.pipeline_id}",
            name="/validation/scorecards/?run__pipeline=[id]",
        )

    @task(1)
    def run_pipeline(self):
        self.client.post(
            f"/api/v1/pipelines/{self.pipeline_id}/run/", name="/pipelines/[id]/run/"
        )
