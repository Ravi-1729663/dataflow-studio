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
Pure functions: `extract(source_type, config)`, `validate(df, spec)`, `transform(df, spec)`,
`load` helpers, and `engine.run(...)` which orchestrates extractâ†’validateâ†’transformâ†’load, returns
metrics + step logs, and raises on blocking validation failure. Receives a `loader` callable so it
never touches the ORM.

## pipelines
`Pipeline` (source FK, JSON config = validation/transform/target specs, schedule, is_active) and
`PipelineRun` (status, started/finished, metrics JSON, logs, error). `services.execute_pipeline`
bridges models â†’ the etl engine and records the run. `tasks.run_pipeline_task` runs it via Celery
(retries + backoff). `loaders.py` maps engine output to warehouse models idempotently. API: pipeline
CRUD + `run` action + read-only run history.

## scheduler
Cron scheduling on django-celery-beat: a schedule per pipeline, manual trigger, retry-failed-job,
and a queue/inflight view. Pause/resume toggles the beat entry.

## validation
Rule library (schema, null, duplicate, type, range, referential integrity, freshness, business
rules), pluggable backend (custom â†’ optionally Great Expectations/Pandera), and a per-run **quality
scorecard** (completeness/consistency/accuracy) persisted with history. Blocking checks fail the run.

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
