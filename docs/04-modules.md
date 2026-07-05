# Module Specifications

Each module is a Django app under `apps/`. Layering: `models` â†’ `services` â†’ `serializers`/`views`.
Acceptance criteria per version are in `PROJECT_PLAN.md`; this file is the per-module contract.

## common
Shared building blocks. `BaseModel` (UUID pk + created/updated timestamps), JSON structured-logging
formatter, domain exceptions (`ConnectorError`, `PipelineExecutionError`, validation errors), a DRF
exception handler producing a consistent error envelope, and a `/api/health/` endpoint.

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
Dataset registry, schema history/versioning, column metadata, and table/column **lineage**
(sourceâ†’bronzeâ†’silverâ†’gold). Schema-drift detection on ingest. Backs the medallion layers (Parquet +
DuckDB).

## monitoring
Prometheus counters/histograms (runs, durations, rows, failures) and an execution-dashboard API
(success rate, failed jobs, runtime metrics). Correlation/run IDs threaded through logs; OTel traces.

## notifications
Email + Slack webhook notifications on run failure, completion, and retry. Pluggable channels,
templated messages, respects per-user/workspace preferences.

## warehouse
The served "gold" layer: target tables (starting with a demo `Customer`) plus a read-only, filtered,
paginated query API. This is what analysts/dashboards read.
