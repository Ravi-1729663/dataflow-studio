# Chaos test report (v0.9)

**Verdict: PASS**

Scenario: a 20000-row pipeline run is triggered against the real docker-compose
`worker` container. Once the run reaches `RUNNING`, the worker container is hard-killed
(`docker kill`, no graceful shutdown) mid-load. A fresh worker container is then started, and the
run is polled until it reaches a terminal status.

| Step                          | Observed                        |
|--------------------------------|----------------------------------|
| Status at kill time             | `RUNNING`     |
| Status while no worker was alive | `RUNNING` (unchanged — nothing was consuming) |
| Final status after recovery     | `SUCCEEDED`       |
| Rows loaded / expected          | 20000 / 20000 |

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
