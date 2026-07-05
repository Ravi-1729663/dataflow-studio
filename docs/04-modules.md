# Module Specifications

Each module is a Django app under `apps/`. Layering: `models` â†’ `services` â†’ `serializers`/`views`.
Acceptance criteria per version are in `PROJECT_PLAN.md`; this file is the per-module contract.

## common
Shared building blocks. `BaseModel` (UUID pk + created/updated timestamps), domain exceptions
(`ConnectorError`, `PipelineExecutionError`, validation errors), a DRF exception handler producing
a consistent error envelope. `logging.py` is the structured-logging core: `JSONFormatter` plus
`CorrelationIdFilter`, which reads a `run_id` contextvar (`set_run_id`/`get_run_id`) and injects it
into every log record automatically — so code that has never heard of a "run id" (e.g.
`apps.warehouse`) still gets tagged correctly during a run's execution, without passing `extra=`
everywhere by hand. `/api/health/` checks the database and, when async execution is actually in
play, the Celery broker (skipped under `CELERY_TASK_ALWAYS_EAGER=1`, since no broker exists there).

## accounts
Custom `User` with a `role` (ADMIN/ENGINEER/ANALYST/VIEWER). JWT auth via SimpleJWT (token +
refresh). RBAC permission classes (`IsAdmin`, `IsEngineerOrAdmin`, read-only-for-viewers). Endpoints:
register, me, token, token/refresh. Later: password reset, workspace membership (v0.7).

## datasources
`DataSource` (name, type FILE/POSTGRES/REST_API, JSON `config`, owner, is_active). A `connectors/`
package with a `Connector` ABC and one class per type, plus a registry `get_connector(type, config)`.
Connectors return a pandas DataFrame. Credentials are Fernet-encrypted (v0.7). CRUD API scoped to the
owner; a "test connection" action.

## etl  (framework-agnostic â€” no Django imports)
Pure functions: `extract(source_type, config)`, `transform(df, spec)`, `load` helpers, and
`engine.run(...)` which orchestrates extractâ†’validateâ†’transformâ†’load, returns metrics + step logs
(including the validation outcome), and raises on blocking validation failure. Receives a `loader`
callable so it never touches the ORM.

`validate(df, spec)` is the rule library behind data-quality scorecards: a pluggable registry of
checks (`required_columns`, `not_null`, `unique`, `no_duplicate_rows`, `column_type`, `range`,
`allowed_values`, `freshness`, `business_rule`), each with a `severity` of `blocking` (default) or
`warning`. It always computes a completeness/consistency/accuracy scorecard â€” completeness and
consistency come from the raw data's null/duplicate rates regardless of which rules are configured;
accuracy is the mean pass-rate of whichever domain-specific rules were actually set. A blocking
violation raises `ValidationFailed`, which still carries the full `ValidationOutcome` so a scorecard
can be persisted even for a failed run.

## pipelines
`Pipeline` (source FK, JSON config = validation/transform/target specs, schedule, is_active) and
`PipelineRun` (status incl. RETRYING, started/finished, metrics JSON, logs, error, traceback,
retry_count) plus `DeadLetterRecord` (one-to-one with a run that exhausted every retry).
`services.start_run`/`execute_attempt`/`mark_retrying`/`mark_failed` are the building blocks;
`execute_pipeline` composes them for a single synchronous attempt (used by `seed_demo` and tests).
`tasks.run_pipeline_task` is the Celery entrypoint: a plain retry loop with exponential backoff
(2s/4s/8s, capped at 30s, base configurable via `PIPELINE_RETRY_BACKOFF_BASE_SECONDS`) — a manual
loop rather than Celery's `self.retry()`, because that API only re-queues through the broker and is
a no-op under `CELERY_TASK_ALWAYS_EAGER=1` (this project's zero-setup local-dev default). After
`MAX_RETRIES` (3) failed attempts the run lands in FAILED with its error + full traceback and a
`DeadLetterRecord` is filed. `loaders.py` maps engine output to warehouse models idempotently, so
re-running (manually or via retry) never double-loads. API: pipeline CRUD + `run` (async, returns
immediately with the new run) + `clone` + `pause`/`resume` actions + read-only run history.

## scheduler
Bridges `Pipeline.schedule` (a 5-field cron string) to django-celery-beat's
`PeriodicTask`/`CrontabSchedule` — the only app that touches django-celery-beat models. A signal on
`Pipeline`'s `post_save` (in `signals.py`) keeps the beat entry in sync on every save from any call
site (API, admin, `seed_demo`): create/edit the schedule, pause/resume (toggles `enabled`), or clear
the schedule (deletes the `PeriodicTask`). This is a one-directional dependency — `pipelines` has no
knowledge scheduler exists. API: `GET queue/` (in-flight PENDING/RUNNING/RETRYING runs), `GET
dead-letter/` (exhausted runs), `POST runs/<id>/retry/` (re-enqueues a FAILED run's pipeline as a
brand-new run — safe because loads are idempotent).

## validation
The rule library and scoring math live in `apps.etl.validate` (framework-agnostic, kept out of
this app so it stays fast to unit test with no DB). This app's job is just to persist that outcome:
`QualityScorecard` (one-to-one with a `PipelineRun`: completeness/consistency/accuracy/overall_score,
`passed`, and the raw per-check `checks` JSON for drill-down) and `services.persist_scorecard(run,
outcome)`, called from `pipelines.services.execute_attempt` on both success and a blocking
`ValidationFailed`. Read-only API: `GET scorecards/?run__pipeline=<id>`, ordered oldest-first for
charting, with a computed `score_delta` against the previous scorecard for the same pipeline —
this is the "trend". A blocking-severity rule stops the load entirely (no scorecard-less runs);
warning-severity rules still lower the score but let the run succeed.

## metadata
Populated by `pipelines.services.execute_attempt` on every successful run (a run a blocking
validation rule stopped is never cataloged). `Dataset` is the registry entry for a warehouse
target (e.g. "customers") â€” shared across every pipeline that feeds it, just like the shared
warehouse table it describes isn't owner-scoped. `SchemaVersion` snapshots the raw/bronze schema
per run and flags drift against the previous version; a column that both disappeared and
reappeared under the name the pipeline's transform `rename` config maps it to is recorded as a
rename, not an unrelated add/drop pair. `ColumnMetadata` is the current column catalog
(`created_at`/`updated_at` double as first/last-seen). `LineageNode`/`LineageEdge` model the
SOURCEâ†’BRONZEâ†’SILVERâ†’GOLD graph â€” bronze/silver/gold nodes are shared per dataset, so a graph can
show multiple sources feeding one warehouse table; each edge keeps its own column mapping per
pipeline for provenance. `medallion.py` writes bronze/silver (per-run batches) and gold (a full
warehouse-table snapshot after each load) as Parquet under `data/medallion/<layer>/<dataset>/`,
queried back via DuckDB (`read_parquet`) â€” gold queries only the latest file, since each one is a
complete snapshot. API: `datasets/`, `schema-versions/`, `columns/` (read-only), plus
`datasets/<name>/lineage/` (the full graph) and `datasets/<name>/medallion/<layer>/` (DuckDB query).

## monitoring
`metrics.py` defines the custom Prometheus counters/histogram (`dataflow_pipeline_runs_total` by
status, `..._run_duration_seconds`, `..._rows_processed_total`, `..._run_retries_total`), recorded
from `pipelines.services` at each terminal/retry state. **Pipeline execution happens in the Celery
worker process, not web/gunicorn** — a counter incremented there lives in that process's own
in-memory registry, invisible to django-prometheus's `/metrics` view in the web process. So the
worker runs its own tiny Prometheus HTTP server (`config/celery.py`'s `worker_init` hook,
`prometheus_client.start_http_server`), scraped by Prometheus as a second job
(`monitoring/prometheus.yml`); Grafana/PromQL then aggregates both jobs with `sum()`. This only
holds together because the worker runs `--pool=solo` (see `docker-compose.yml`) — Celery's default
prefork pool forks child processes per task, each with its own registry the parent's HTTP server
can't see. `services.get_dashboard(owner)` computes the execution dashboard (success rate, failed
jobs, avg duration) from `PipelineRun` directly — duration is read out of the `metrics` JSONField in
Python rather than an ORM aggregate, since JSON-key aggregation isn't equally portable across
SQLite and PostgreSQL. `tracing.py` sets up an OpenTelemetry `TracerProvider` with a console
exporter; `inject_context`/`extract_context` carry a run's trace context from the API's `run`
action into the Celery task via a plain dict task kwarg (hand-rolled rather than the
django/celery auto-instrumentation packages — a few lines with `opentelemetry-api` alone), so a
run's spans cover both processes and `span.record_exception` pinpoints exactly which step failed.
API: `GET dashboard/`.

## notifications
`NotificationPreference` (per-user email/Slack opt-in; `slack_webhook_url` is validated to actually
be a `hooks.slack.com` URL, since a user-controlled webhook target is otherwise an SSRF vector) and
`NotificationLog` (audit trail: event/channel/recipient/success/error per attempt).
`channels.py` is pluggable — `EmailChannel` (Django's `send_mail`) and `SlackChannel` (a plain
`urllib.request` POST, no extra dependency) each just raise on failure. `services.notify(event,
run)` renders one of three templates (`templates/notifications/run_{failed,succeeded,retrying}.txt`)
and dispatches through whichever channels the pipeline owner has enabled, always recording a
`NotificationLog` — a channel exception is caught and logged, never allowed to break the run itself.
Called from `pipelines.services` on every success, retry, and terminal failure. API: `GET/PATCH
preference/` (the caller's own), `GET logs/` (read-only, owner-scoped).

## warehouse
The served "gold" layer: target tables (starting with a demo `Customer`) plus a read-only, filtered,
paginated query API. This is what analysts/dashboards read.
