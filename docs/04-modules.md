# Module Specifications

Each module is a Django app under `apps/`. Layering: `models` â†’ `services` â†’ `serializers`/`views`.
Acceptance criteria per version are in `PROJECT_PLAN.md`; this file is the per-module contract.

**Cross-cutting (v0.7):** every business endpoint lives under `/api/v1/` now (`config/urls.py`) —
`/api/health/`, `/api/schema/`, `/api/docs/`, `/metrics`, and `/admin/` (Django admin) stay
unversioned, since they're infrastructure surfaces rather than versioned business API. DRF
throttling is on globally (`UserRateThrottle`/`AnonRateThrottle`, rates via `THROTTLE_RATE_USER`/
`THROTTLE_RATE_ANON`), plus a tighter `auth` scope (`THROTTLE_RATE_AUTH`, default 10/min) applied to
register/login specifically.

## common
Shared building blocks. `BaseModel` (UUID pk + created/updated timestamps), domain exceptions
(`ConnectorError`, `PipelineExecutionError`, validation errors), a DRF exception handler producing
a consistent error envelope. `logging.py` is the structured-logging core: `JSONFormatter` plus
`CorrelationIdFilter`, which reads a `run_id` contextvar (`set_run_id`/`get_run_id`) and injects it
into every log record automatically — so code that has never heard of a "run id" (e.g.
`apps.warehouse`) still gets tagged correctly during a run's execution, without passing `extra=`
everywhere by hand. `/api/health/` checks the database and, when async execution is actually in
play, the Celery broker (skipped under `CELERY_TASK_ALWAYS_EAGER=1`, since no broker exists there).
`fields.EncryptedJSONField` (v0.7) is a `TextField` that transparently Fernet-encrypts/decrypts a
JSON-serializable value — the column holds opaque ciphertext, never plaintext; `FERNET_KEY` comes
from the environment, with a dev-only fallback derived from `SECRET_KEY` (see `config/settings/base.py`).
`idempotency.idempotent(action_name)` (v0.7) is a decorator for side-effecting viewset actions: a
client-supplied `Idempotency-Key` header makes a retried request replay the original response
instead of re-triggering the action, backed by the `IdempotencyKey` model.

## accounts
Custom `User` with a `role` (ADMIN/ENGINEER/ANALYST/VIEWER). JWT auth via SimpleJWT (token +
refresh) — `LoginView` wraps SimpleJWT's `TokenObtainPairView` to add an audit-log entry and the
tighter `auth` throttle scope (10/min by default), since login/register are classic brute-force
targets. RBAC permission classes (`IsAdmin`, `IsEngineerOrAdmin`, read-only-for-viewers). Endpoints:
register, me, token, token/refresh.

## workspaces  (v0.7)
The tenant boundary. `Workspace` + `WorkspaceMembership` (through table with a `role` of
OWNER/MEMBER). Every workspace-owned resource (`DataSource`, and `Pipeline` via its source) carries
a `workspace` FK, and every other app's `get_queryset()` filters through
`workspace__memberships__user=request.user` — this is the actual isolation enforcement, not just a
convention. `services.create_workspace` also makes the creator its first OWNER; only an OWNER can
add/remove members. API: workspace CRUD + `members/` (list/add) + `members/<user_id>/` (remove).
Deliberately *not* extended to `metadata`/`warehouse` — see those sections below.

## audit  (v0.7)
`AuditLog` (actor, workspace, action, target, metadata JSON) — an immutable trail of sensitive
actions (register, login, workspace/datasource/pipeline create-update-delete-run, admin user/role
changes). `actor` and `workspace` are `SET_NULL` on delete, not `CASCADE`: an audit trail must
outlive the thing it describes, so deleting a workspace nulls the FK but the row (and its `target`
name) survives. `services.record(actor, action, workspace=None, target="", metadata=None)` is the
only write path, called from every app that needs to audit something — never written to directly.
Read API (`GET /api/v1/audit/logs/`) is platform-admin-only, since the trail is a global,
cross-workspace surface.

## platform_admin  (v0.7)
Admin-only surface, gated by the existing `IsAdmin` permission (not a new role). `UserAdminViewSet`
lists/patches users (role, `is_active`) — no create (registration is self-service) or delete
(deactivate instead, to preserve FK history on everything the user owns/authored).
`PlatformConfig` is a runtime-editable key/value store for platform-wide settings. `SystemHealthView`
extends `common.HealthView` with platform-wide counts (workspaces/users/pipelines/runs) for an
at-a-glance ops view. API: `admin/users/`, `admin/config/`, `admin/health/`.

## datasources
`DataSource` (name, type FILE/POSTGRES/REST_API, Fernet-encrypted `config`, owner, workspace,
is_active). A `connectors/` package with a `Connector` ABC and one class per type (`FileConnector`,
`PostgresConnector`, `RestApiConnector`), plus a registry `get_connector(type, config)`. Connectors
return a pandas DataFrame. Each connector's `extract()` is a thin wrapper that delegates to
`apps.etl.extract` (the one place that actually implements reading a file/running a SQL
query/paginating a REST API) — connectors only add the Django-settings-aware bits (file path
resolution) and a cheap standalone `test_connection()` probe on top of that shared,
framework-agnostic logic; this keeps the real extraction logic in exactly one place instead of
duplicated between the two apps. CRUD API scoped to workspace membership (v0.7: `workspace` is a
required, serializer-validated field — the client must be a member of the workspace it names); a
"test connection" action.

## etl  (framework-agnostic â€” no Django imports)
Pure functions: `extract(source_type, config)` (file/postgres/rest_api — postgres via a plain
`psycopg2` cursor, rest_api via `urllib` with pagination, a configurable rate limit, and retry with
backoff), `transform(df, spec)`, `load` helpers, and `engine.run(...)` which orchestrates
extractâ†’incrementalâ†’validateâ†’transformâ†’load, returns metrics + step logs (including the
validation outcome and the next watermark), and raises on blocking validation failure. Receives a
`loader` callable so it never touches the ORM.

`incremental.py` is the watermark logic: `filter_incremental(df, column, watermark, grace_seconds)`
keeps only rows newer than the watermark (client-side, so it applies uniformly regardless of
source type or whether a connector pushed the filter into its query), and `compute_watermark`
returns the max value seen for next time. `grace_seconds` is the late-arriving-data strategy — a
row within that window *before* the watermark is still included, tolerating an out-of-order
arrival; idempotent loads make the resulting overlap harmless. `engine.run()`'s `rows_extracted`
is the raw source pull; `rows_loaded` is what survived incremental filtering — the gap between the
two is the whole point of watermark tracking.

`validate(df, spec)` is the rule library behind data-quality scorecards: a pluggable registry of
checks (`required_columns`, `not_null`, `unique`, `no_duplicate_rows`, `column_type`, `range`,
`allowed_values`, `freshness`, `business_rule`), each with a `severity` of `blocking` (default) or
`warning`. It always computes a completeness/consistency/accuracy scorecard â€” completeness and
consistency come from the raw data's null/duplicate rates regardless of which rules are configured;
accuracy is the mean pass-rate of whichever domain-specific rules were actually set. A blocking
violation raises `ValidationFailed`, which still carries the full `ValidationOutcome` so a scorecard
can be persisted even for a failed run.

## pipelines
`Pipeline` (source FK, JSON config = validation/transform/target specs, schedule, is_active,
`workspace` — v0.7: auto-derived from `source.workspace` in `save()`, never client-settable, so a
pipeline can't be pointed at another workspace's source) and `PipelineRun` (status incl. RETRYING,
started/finished, metrics JSON, logs, error, traceback, retry_count) plus `DeadLetterRecord`
(one-to-one with a run that exhausted every retry). `services.start_run`/`execute_attempt`/
`mark_retrying`/`mark_failed` are the building blocks; `execute_pipeline` composes them for a single
synchronous attempt (used by `seed_demo` and tests). `tasks.run_pipeline_task` is the Celery
entrypoint: a plain retry loop with exponential backoff (2s/4s/8s, capped at 30s, base configurable
via `PIPELINE_RETRY_BACKOFF_BASE_SECONDS`) — a manual loop rather than Celery's `self.retry()`,
because that API only re-queues through the broker and is a no-op under
`CELERY_TASK_ALWAYS_EAGER=1` (this project's zero-setup local-dev default). After `MAX_RETRIES` (3)
failed attempts the run lands in FAILED with its error + full traceback and a `DeadLetterRecord` is
filed. `loaders.py` maps a pipeline's `target` to a warehouse loader (`customers`: Type-1 upsert;
`customers_scd2`: Type 2 history), idempotently, so re-running (manually or via retry) never
double-loads. `PipelineWatermark` (one-to-one with a pipeline) persists the incremental cursor
between runs, read/written by `_build_incremental_spec` and `execute_attempt` respectively — only
exists for pipelines with `config["incremental"]` set. API: pipeline CRUD (queryset scoped to
workspace membership, v0.7) + `run` (async, returns immediately with the new run; supports an
`Idempotency-Key` header via `apps.common.idempotency`, v0.7) + `clone` + `pause`/`resume` actions +
read-only run history. `PipelineSerializer` scopes the `source` field's own queryset to the
requester's workspaces (v0.7) — without this, DRF's default `PrimaryKeyRelatedField` queryset would
let a client reference another workspace's source by UUID even though they can't list it.

## scheduler
Bridges `Pipeline.schedule` (a 5-field cron string) to django-celery-beat's
`PeriodicTask`/`CrontabSchedule` — the only app that touches django-celery-beat models. A signal on
`Pipeline`'s `post_save` (in `signals.py`) keeps the beat entry in sync on every save from any call
site (API, admin, `seed_demo`): create/edit the schedule, pause/resume (toggles `enabled`), or clear
the schedule (deletes the `PeriodicTask`). This is a one-directional dependency — `pipelines` has no
knowledge scheduler exists. API (queryset/lookups scoped to workspace membership, v0.7): `GET
queue/` (in-flight PENDING/RUNNING/RETRYING runs), `GET dead-letter/` (exhausted runs), `POST
runs/<id>/retry/` (re-enqueues a FAILED run's pipeline as a brand-new run — safe because loads are
idempotent).

## validation
The rule library and scoring math live in `apps.etl.validate` (framework-agnostic, kept out of
this app so it stays fast to unit test with no DB). This app's job is just to persist that outcome:
`QualityScorecard` (one-to-one with a `PipelineRun`: completeness/consistency/accuracy/overall_score,
`passed`, and the raw per-check `checks` JSON for drill-down) and `services.persist_scorecard(run,
outcome)`, called from `pipelines.services.execute_attempt` on both success and a blocking
`ValidationFailed`. Read-only API (scoped to workspace membership, v0.7): `GET
scorecards/?run__pipeline=<id>`, ordered oldest-first for charting, with a computed `score_delta`
against the previous scorecard for the same pipeline — this is the "trend". A blocking-severity
rule stops the load entirely (no scorecard-less runs); warning-severity rules still lower the score
but let the run succeed.

## metadata
Populated by `pipelines.services.execute_attempt` on every successful run (a run a blocking
validation rule stopped is never cataloged). **Deliberately not workspace-scoped (v0.7):** the
catalog describes the shared warehouse/gold layer, which itself isn't workspace-partitioned — see
`warehouse` below. `Dataset` is the registry entry for a warehouse
target (e.g. "customers") â€” shared across every pipeline that feeds it, just like the shared
warehouse table it describes isn't owner-scoped. `SchemaVersion` snapshots the raw/bronze schema
per run and flags drift against the previous version; a column that both disappeared and
reappeared under the name the pipeline's transform `rename` config maps it to is recorded as a
rename, not an unrelated add/drop pair. `ColumnMetadata` is the current column catalog
(`created_at`/`updated_at` double as first/last-seen). `LineageNode`/`LineageEdge` model the
SOURCEâ†’BRONZEâ†’SILVERâ†’GOLD graph â€” bronze/silver/gold nodes are shared per dataset, so a graph can
show multiple sources feeding one warehouse table; each edge keeps its own column mapping per
pipeline for provenance. `medallion.py` writes bronze/silver (per-run batches) and gold (a full
warehouse-table snapshot after each load) as Parquet, Hive-partitioned by date
(`data/medallion/<layer>/<dataset>/dt=YYYY-MM-DD/<run_id>.parquet`, using the run's own date so
re-processing old data partitions correctly instead of always landing in "today"), queried back via
DuckDB (`read_parquet`) across every partition â€” gold queries only the latest file, since each one
is a complete snapshot. API: `datasets/`, `schema-versions/`, `columns/` (read-only), plus
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
jobs, avg duration) from `PipelineRun` filtered by the caller's workspace memberships (v0.7) —
duration is read out of the `metrics` JSONField in
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
preference/` (the caller's own — deliberately kept user-scoped rather than workspace-scoped even
after v0.7 introduced workspaces, since alerting preferences are personal), `GET logs/` (read-only,
scoped to workspace membership via the log's run→pipeline chain, v0.7).

## warehouse
The served "gold" layer: target tables (starting with a demo `Customer`) plus a read-only, filtered,
paginated query API. This is what analysts/dashboards read. **Deliberately not workspace-scoped
(v0.7):** the gold layer is an org-wide shared surface by design, consistent with `metadata` above —
only the write side (`pipelines`/`datasources`) is tenant-isolated. `CustomerSerializer.email` masks
the address (`a***@example.com`) for anyone who isn't ADMIN/ENGINEER (v0.7 PII masking); analysts and
viewers querying the served layer never see the raw address.

`Customer` supports two load strategies over the same table (`pipelines.loaders` picks one via a
pipeline's `target`): a plain Type-1 upsert (`services.upsert_customers`, target `"customers"`)
always overwrites in place, one row per `external_id`; Slowly Changing Dimension Type 2
(`services.upsert_customers_scd2`, target `"customers_scd2"`) keeps every version — a changed
tracked attribute closes out the current row (`valid_to`/`is_current=False`) and inserts a new
current one, so `external_id` is deliberately *not* globally unique, only enforced unique among
`is_current=True` rows (a partial `UniqueConstraint`). An identical reload is a no-op either way.
Both loaders batch writes into chunked transactions (`DEFAULT_BATCH_SIZE`) rather than one
transaction per row or one giant transaction for the whole run. `get_dataframe()` (used for the
metadata app's gold Parquet snapshot) only returns current rows regardless of load strategy.

## frontend  (v0.8, not a Django app — lives at repo root, not under `apps/`)
A React + TypeScript SPA (Vite) that talks to the same REST API as everything else — no server-side
rendering, no separate backend-for-frontend. `src/lib/api.ts` is the only place that knows about
JWT: an axios instance attaches the access token to every request and, on a 401, transparently
refreshes it (concurrent 401s share one in-flight refresh) before retrying the original request once;
a refresh failure clears tokens and bounces to `/login`. `src/lib/resources.ts` is thin typed
wrappers per backend app (mirrors the URL layout under `/api/v1/`); `src/lib/types.ts` mirrors the
DRF serializers by hand (no codegen — `/api/schema/` is the source of truth if they drift).

Two React contexts carry cross-cutting state: `AuthContext` (current user, login/register/logout)
and `WorkspaceContext` (the v0.7 tenant boundary — every workspace-scoped page reads/writes through
`WorkspaceGate`, which prompts to create a workspace if none exists yet, since there's no useful
empty state otherwise). Every workspace-scoped list call is filtered by `?workspace=<id>` so
switching workspaces in the header actually re-scopes every page.

Pages: Data Sources (create + list + a "test connection" action), a pipeline builder (dynamic
validation-rule editor covering every `apps.etl.validate` rule type, a rename-column editor, target
and incremental-column pickers) + pipeline detail (run history, run/pause/resume/clone actions, and
a `setInterval` poll against `GET /pipelines/runs/<id>/` after triggering a run — stopped once the
run reaches SUCCEEDED/FAILED — satisfying "run status updates" without a websocket), a monitoring
dashboard (recharts bar chart over `GET /monitoring/dashboard/`), a lineage viewer (a hand-rolled SVG
DAG renderer over `GET /metadata/datasets/<name>/lineage/` — skipped a graph library since the graph
is small and fixed-shape: SOURCE→BRONZE→SILVER→GOLD columns), and quality scorecards (a recharts
trend line over `GET /validation/scorecards/?run__pipeline=<id>`).

CORS (`django-cors-headers`, `CORS_ALLOWED_ORIGINS` env var, default `localhost:5173`) is the only
backend change this milestone required — JWT travels as an `Authorization` header, not a cookie, so
no `CORS_ALLOW_CREDENTIALS` is needed. Run with `make frontend-install && make frontend-dev`
alongside `make run`. No automated frontend tests were added for this milestone (out of scope per
`PROJECT_PLAN.md`'s v0.8 acceptance criteria) — `npm run build` (`tsc -b && vite build`) is the only
gate, run in place of a test suite.
