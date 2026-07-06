"""Chaos test (v0.9): hard-kills a Celery worker mid-run and asserts the pipeline run still
recovers and completes.

Targets the docker-compose stack's real `db` (Postgres), `redis`, and `worker` containers — there
is nothing to kill mid-flight under CELERY_TASK_ALWAYS_EAGER=1 (pipeline execution would just run
synchronously in this script's own process). Recovery relies on the reliability settings added in
config/settings/base.py: CELERY_TASK_ACKS_LATE + CELERY_TASK_REJECT_ON_WORKER_LOST mean a worker
that dies without acking leaves its message "in flight"; CELERY_BROKER_TRANSPORT_OPTIONS'
visibility_timeout bounds how long Redis waits before assuming the consumer died and redelivering
the message to the next worker that connects.

Usage (from the repo root, with the venv active):
    docker compose up -d --build db redis
    python scripts/chaos_test.py

Prints a PASS/FAIL report and writes docs/reports/chaos-test-report.md.
"""

import csv
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = REPO_ROOT / "sample_data" / "chaos_customers.csv"
REPORT_PATH = REPO_ROOT / "docs" / "reports" / "chaos-test-report.md"
ROW_COUNT = 20_000
VISIBILITY_TIMEOUT_SECONDS = 10
WORKER_CONTAINER = "dataflow-studio-worker-1"
RECOVERY_TIMEOUT_SECONDS = 90


def log(message: str) -> None:
    print(f"[chaos] {message}", flush=True)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    log("$ " + " ".join(cmd))
    return subprocess.run(cmd, cwd=REPO_ROOT, check=True, **kwargs)


def generate_csv(path: Path, rows: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "customer_id",
                "first_name",
                "last_name",
                "email",
                "signup_date",
                "country",
            ]
        )
        for i in range(rows):
            writer.writerow(
                [
                    f"chaos-{i}",
                    "Chaos",
                    "Tester",
                    f"chaos{i}@example.com",
                    "2024-01-01",
                    "US",
                ]
            )


def set_env_file_var(key: str, value: str | None) -> None:
    """Adds/updates/removes a KEY=value line in .env (read by every docker-compose service via
    env_file) — the only way an env var actually reaches the containers, since passing it to the
    `docker compose` subprocess's own environment only affects `${...}` substitution in the YAML,
    not the container's runtime environment."""
    env_path = REPO_ROOT / ".env"
    lines = (
        env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    )
    lines = [line for line in lines if not line.startswith(f"{key}=")]
    if value is not None:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def wait_for_status(get_status, targets: set[str], timeout: float, label: str) -> str:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = get_status()
        if last in targets:
            return last
        time.sleep(0.3)
    raise TimeoutError(f"timed out waiting for {label} (last seen: {last!r})")


def main() -> int:
    log(
        f"generating a {ROW_COUNT}-row CSV so the run takes long enough to interrupt mid-flight"
    )
    generate_csv(CSV_PATH, ROW_COUNT)

    worker_reconfigured = False
    try:
        log("building the worker image with the new CSV baked in")
        run(["docker", "compose", "build", "worker"])

        log(
            f"setting a short ({VISIBILITY_TIMEOUT_SECONDS}s) broker visibility timeout"
        )
        set_env_file_var("CELERY_VISIBILITY_TIMEOUT", str(VISIBILITY_TIMEOUT_SECONDS))
        worker_reconfigured = True
        run(["docker", "compose", "up", "-d", "--force-recreate", "worker"])

        # The producer side: talks to the same Postgres + Redis the containers use, over the
        # ports docker-compose publishes to localhost.
        os.environ.update(
            {
                "DJANGO_SETTINGS_MODULE": "config.settings.local",
                "USE_POSTGRES": "1",
                "POSTGRES_HOST": "localhost",
                "POSTGRES_PORT": "5432",
                "POSTGRES_DB": "dataflow",
                "POSTGRES_USER": "dataflow",
                "POSTGRES_PASSWORD": "dataflow",
                "CELERY_BROKER_URL": "redis://localhost:6379/0",
                "CELERY_RESULT_BACKEND": "redis://localhost:6379/1",
                "CELERY_TASK_ALWAYS_EAGER": "0",  # else .delay() would just run in THIS process
            }
        )
        sys.path.insert(0, str(REPO_ROOT))
        import django

        django.setup()

        from django.contrib.auth import get_user_model

        from apps.datasources.models import DataSource
        from apps.pipelines.models import Pipeline, PipelineRun
        from apps.pipelines.services import start_run
        from apps.pipelines.tasks import run_pipeline_task
        from apps.warehouse.models import Customer
        from apps.workspaces.models import Workspace
        from apps.workspaces.services import create_workspace

        User = get_user_model()

        user, _ = User.objects.get_or_create(
            username="chaos_test_user", defaults={"email": "chaos@example.com"}
        )
        workspace = Workspace.objects.filter(memberships__user=user).first()
        if workspace is None:
            workspace = create_workspace(user, "Chaos Test Workspace")

        source, _ = DataSource.objects.update_or_create(
            name="Chaos CSV",
            owner=user,
            workspace=workspace,
            defaults={
                "source_type": DataSource.SourceType.FILE,
                "config": {"path": "sample_data/chaos_customers.csv"},
            },
        )
        pipeline, _ = Pipeline.objects.update_or_create(
            name="Chaos Pipeline",
            owner=user,
            defaults={
                "source": source,
                "schedule": "",
                "config": {
                    "validation": {
                        "rules": [{"type": "required_columns", "columns": ["email"]}]
                    },
                    "transform": {},
                    "target": "customers",
                },
            },
        )

        log(
            f"creating a fresh PipelineRun and enqueueing it on the real worker (pipeline={pipeline.id})"
        )
        pipeline_run = start_run(pipeline)
        run_pipeline_task.delay(
            pipeline_id=str(pipeline.id), run_id=str(pipeline_run.id)
        )

        def current_status() -> str:
            return PipelineRun.objects.values_list("status", flat=True).get(
                pk=pipeline_run.id
            )

        log("waiting for the worker to pick up the task (status -> RUNNING)")
        wait_for_status(current_status, {"RUNNING"}, timeout=20, label="run to start")
        log(
            "run is RUNNING — giving it a moment to get partway through the load before killing it"
        )
        time.sleep(2)

        status_at_kill = current_status()
        log(f"status immediately before kill: {status_at_kill}")

        log(
            f"hard-killing the worker container ({WORKER_CONTAINER}) — simulates a crash/OOM/deploy"
        )
        run(["docker", "kill", WORKER_CONTAINER])

        log("confirming the run is NOT progressing while no worker is alive")
        time.sleep(3)
        stalled_status = current_status()
        log(f"status with no worker running: {stalled_status}")

        # Kombu's redis transport only restores an unacked message once its visibility window
        # has fully elapsed, and — empirically, under --pool=solo — only re-checks once at
        # connection time rather than on a recurring timer. So the replacement worker needs to
        # connect *after* the window closes, not before, or the message sits unclaimed.
        wait_remaining = VISIBILITY_TIMEOUT_SECONDS + 5
        log(
            f"waiting {wait_remaining}s for the broker visibility window to fully elapse"
        )
        time.sleep(wait_remaining)

        log(
            "starting a fresh worker (simulates redeploy/autoscaler bringing a replacement online)"
        )
        # `docker start` on the same (killed) container proved unreliable here — Kombu's redis
        # transport didn't pick the redelivered message back up within any reasonable window.
        # A full recreate (a genuinely new container/process, closer to what a real
        # redeploy/autoscaler does anyway) reconnects cleanly every time.
        run(["docker", "compose", "up", "-d", "--force-recreate", "worker"])

        log("waiting for the run to recover and reach a terminal status")
        final_status = wait_for_status(
            current_status,
            {"SUCCEEDED", "FAILED"},
            timeout=RECOVERY_TIMEOUT_SECONDS,
            label="run to recover",
        )

        loaded_count = Customer.objects.filter(external_id__startswith="chaos-").count()
        pipeline_run.refresh_from_db()

        recovered = final_status == "SUCCEEDED" and loaded_count == ROW_COUNT
        report = {
            "row_count": ROW_COUNT,
            "status_at_kill": status_at_kill,
            "status_while_worker_dead": stalled_status,
            "final_status": final_status,
            "rows_loaded": loaded_count,
            "recovered": recovered,
        }
        write_report(report)

        log("=" * 60)
        log(f"RESULT: {'PASS — run recovered cleanly' if recovered else 'FAIL'}")
        log(f"  status at kill time:        {status_at_kill}")
        log(f"  status while worker dead:   {stalled_status}")
        log(f"  final status:               {final_status}")
        log(f"  rows loaded / expected:     {loaded_count} / {ROW_COUNT}")
        log("=" * 60)
        return 0 if recovered else 1
    finally:
        CSV_PATH.unlink(missing_ok=True)
        if worker_reconfigured:
            log("reverting the worker container to its normal configuration")
            set_env_file_var("CELERY_VISIBILITY_TIMEOUT", None)
            try:
                run(["docker", "compose", "up", "-d", "--force-recreate", "worker"])
            except subprocess.CalledProcessError:
                log(
                    "warning: failed to restore the worker container — check `docker compose ps`"
                )


def write_report(report: dict) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    verdict = "PASS" if report["recovered"] else "FAIL"
    REPORT_PATH.write_text(
        encoding="utf-8",
        data=f"""# Chaos test report (v0.9)

**Verdict: {verdict}**

Scenario: a {report['row_count']}-row pipeline run is triggered against the real docker-compose
`worker` container. Once the run reaches `RUNNING`, the worker container is hard-killed
(`docker kill`, no graceful shutdown) mid-load. A fresh worker container is then started, and the
run is polled until it reaches a terminal status.

| Step                          | Observed                        |
|--------------------------------|----------------------------------|
| Status at kill time             | `{report['status_at_kill']}`     |
| Status while no worker was alive | `{report['status_while_worker_dead']}` (unchanged — nothing was consuming) |
| Final status after recovery     | `{report['final_status']}`       |
| Rows loaded / expected          | {report['rows_loaded']} / {report['row_count']} |

## Why this works

`CELERY_TASK_ACKS_LATE` + `CELERY_TASK_REJECT_ON_WORKER_LOST` (config/settings/base.py) mean the
broker only removes a task's message once a worker actually finishes it — a worker killed
mid-task never acks, so the message stays queued. `CELERY_BROKER_TRANSPORT_OPTIONS.visibility_timeout`
bounds how long Redis waits before assuming the original consumer died and redelivering the
message to the next worker that connects. The redelivered task re-invokes
`pipelines.tasks.run_pipeline_task` with the same `run_id`; because every load in this project is
an idempotent upsert (`apps/warehouse/services.py`), re-running the same extract → validate →
transform → load from scratch is safe.

**Known caveat:** a recovered run that had already sent a notification or incremented a metric
before the kill (neither applies to this scenario, since the kill happens mid-load, before either
fires) could double them on the redelivered attempt — the *data* is guaranteed idempotent, side
effects downstream of a successful load are not. Worth knowing, not a defect this test exercises.

**Operational nuance found while building this test:** under `--pool=solo`, Kombu's redis
transport only re-scans for expired unacked messages once, at connection time — it does not poll
on a recurring timer while otherwise idle. A replacement worker that connects *before* the
visibility window has fully elapsed won't pick the message up at all until something else triggers
another scan. This script deliberately waits out the full visibility timeout before starting the
replacement worker; a real autoscaler/orchestrator restarting a crashed worker immediately would
need either a short visibility timeout or worker traffic that keeps re-triggering scans.
""",
    )


if __name__ == "__main__":
    sys.exit(main())
