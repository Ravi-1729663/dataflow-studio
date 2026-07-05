# DataFlow Studio â€” Project Plan

**Owner:** Ravi Sankar Reddy Bovilla Â· **Status:** Planning â†’ Build Â· **Version target:** v1.0

This is the project-manager's blueprint. It defines the objectives, the scope, the build strategy,
and a milestone-by-milestone task breakdown with acceptance criteria. Build it **version by
version, in order** (see *Build Strategy*). `CLAUDE.md` defines the engineering conventions.

---

## 1. Objectives & success criteria

**Product objective:** an internal enterprise data platform for registering data sources, building
and scheduling ETL/ELT pipelines, validating and governing data, and monitoring executions through
a documented API and dashboards.

**Success is measured by (KPIs):**

| KPI                                | Target for v1.0                                  |
|------------------------------------|--------------------------------------------------|
| End-to-end pipeline works          | CSV/API/DB source â†’ validate â†’ transform â†’ warehouse â†’ query |
| Pipeline success rate (demo data)  | â‰¥ 99% on healthy inputs                          |
| Test coverage on core logic        | â‰¥ 80% for `etl` + `pipelines` + `validation`     |
| API documented                     | 100% of endpoints in OpenAPI (`/api/docs/`)      |
| Observability                      | Metrics, structured logs, and alerts on failures |
| Reproducible deploy                | `docker compose up` boots the full stack         |
| Portfolio readiness                | README, live demo, ADRs, and case study complete |

**Definition of Done (project):** publicly deployed; auth works; pipelines execute and schedule;
validation + quality scorecards run; monitoring dashboards function; tests + CI pass; docs complete;
and every architectural decision is explainable in an interview.

---

## 2. Scope

| In scope (through v1.0)                          | Out of scope (v1.0)              | Future scope (roadmap)             |
|--------------------------------------------------|----------------------------------|------------------------------------|
| Auth, JWT, RBAC, workspaces, admin               | Real-time streaming (Kafka/Flink)| Streaming ingestion + CDC-over-log |
| File / Postgres / REST API sources               | Cloud-managed warehouses         | Snowflake/BigQuery connectors      |
| ETL engine (batch + incremental), SCD2           | ML training / feature store      | ML feature store + model serving   |
| Validation engine + data-quality scorecards      | Native mobile app                | Mobile companion                   |
| Pipeline engine + cron scheduler + retries       | Multi-region HA                  | Multi-region active-active         |
| Metadata catalog + lineage                       |                                  | Column-level lineage auto-capture  |
| Monitoring, logging, alerting, notifications     |                                  | Cost governance dashboard          |
| REST API (versioned, OpenAPI) + optional React UI|                                  |                                    |
| Docker, CI/CD, tests, encrypted secrets          |                                  |                                    |

---

## 3. Build strategy â€” version by version (decision)

**Decision:** build incrementally, one release at a time, each independently runnable, tested, and
committed. **Rejected:** "build everything, then debug."

**Why incremental wins**

- **Always shippable.** Every version boots and demos on its own â€” you never sit on a broken tree.
- **Scoped debugging.** A regression came from the *last* increment, not from 5,000 lines across
  11 modules. Mean-time-to-fix stays low.
- **No compounding integration bugs.** Interfaces are exercised as they land, not all at once.
- **The story sells you.** Milestones + semantic versions + ADRs are exactly the signal hiring
  managers read as "this person operates like an engineer, not a script-runner."

**Why not slow:** each version is a single Claude Code session â€” many files, tests, and fixes in
one go. You simply *gate* each version (green tests + a demo) before starting the next.

---

## 4. Milestone plan

Each milestone: **Goal Â· Build Â· Acceptance Â· Demo.** Tag on completion (`v0.x.0`).

### v0.1 â€” Walking skeleton  *(foundation; prove the architecture end-to-end)*
- **Goal:** the thinnest complete path works and the layering holds.
- **Build:** Django project + env-based settings; `common` (BaseModel, logging, exceptions, health);
  `accounts` (custom User + JWT + RBAC); `datasources` (FILE source + file connector);
  `etl` (extract/validate/transform/load/engine); `pipelines` (Pipeline + PipelineRun + execute
  service + celery task); `warehouse` (a demo target table + query API); `seed_demo` command;
  unit + integration tests; Dockerfile + compose; README.
- **Acceptance:**
  - [ ] `make seed` ingests `sample_data/customers.csv` â†’ rows land in the warehouse table.
  - [ ] `GET /api/warehouse/customers/` returns data (JWT required).
  - [ ] `make test` is green (ETL unit tests + one end-to-end pipeline test).
  - [ ] `docker compose up` boots web + worker + db + redis.
  - [ ] `/api/docs/` renders the schema.
- **Demo:** register â†’ login â†’ create datasource â†’ create pipeline â†’ run â†’ query results.

### v0.2 â€” Pipeline engine + scheduler + async
- **Goal:** real orchestration, not a single synchronous call.
- **Build:** pipeline lifecycle (create/edit/clone/pause/resume/execute); Celery async execution
  with `run_pipeline_task`; `scheduler` app on django-celery-beat (cron per pipeline, manual run,
  retry failed job, queue view); retries with exponential backoff + a dead-letter record for failed
  runs; run history + metrics per run.
- **Acceptance:** [ ] a scheduled pipeline fires on cron in the worker; [ ] a failing run retries N
  times then lands in FAILED with an error + traceback; [ ] pause/resume respected; [ ] runs are
  idempotent (re-running does not double-load).
- **Demo:** schedule a pipeline every 2 min, watch runs accrue, pause it, force a failure, see retry.

### v0.3 â€” Validation engine + data-quality scorecards
- **Goal:** trustworthy data with visible quality.
- **Build:** `validation` app â€” schema, null, duplicate, data-type, range, referential-integrity,
  freshness, and business-rule checks (pluggable; optionally back with Great Expectations/Pandera);
  per-run **quality scorecard** (completeness/consistency/accuracy %) persisted with history and
  trend; blocking vs warning checks; contract to fail a run on blocking violations.
- **Acceptance:** [ ] a dataset with nulls/dupes produces a scorecard with a numeric score;
  [ ] a blocking failure stops the load; [ ] scorecard history is queryable via API.
- **Demo:** run clean vs dirty data, compare scorecards and the trend.

### v0.4 â€” Metadata catalog + lineage + medallion
- **Goal:** governance and modern lakehouse layering.
- **Build:** `metadata` app â€” dataset registry, schema history/versioning, column metadata,
  table- and column-level **lineage** (source â†’ bronze â†’ silver â†’ gold); local **medallion** layers
  as Parquet queried via DuckDB; schema-drift detection on ingest.
- **Acceptance:** [ ] lineage graph resolvable for any warehouse table; [ ] schema history records a
  column add/rename; [ ] bronze/silver/gold Parquet layers produced and queryable via DuckDB;
  [ ] a drifted source is flagged.
- **Demo:** show the lineage graph and the medallion layers for the customers pipeline.

### v0.5 â€” Observability + alerting + notifications
- **Goal:** operate it like production.
- **Build:** `monitoring` (Prometheus counters/histograms: runs, durations, rows, failures;
  Grafana dashboard JSON); execution dashboard API (success rate, failed jobs, runtime metrics);
  structured JSON logs with correlation/run IDs; OpenTelemetry tracing APIâ†’worker;
  `notifications` (email + Slack webhook on failure/completion/retry); health checks.
- **Acceptance:** [ ] `/metrics` exposes pipeline metrics; [ ] Grafana renders the dashboard;
  [ ] a failed run sends an alert; [ ] logs carry a run/correlation id end-to-end.
- **Demo:** trigger a failure â†’ alert fires â†’ trace + logs pinpoint the failing step.

### v0.6 â€” More connectors + incremental/CDC + SCD2
- **Goal:** ingest from real systems, load efficiently.
- **Build:** Postgres source connector + REST API connector (pagination, rate limiting, retries);
  incremental loads with watermark tracking; Slowly Changing Dimension **Type 2** handling; late-
  arriving data strategy; batch tuning + Parquet partitioning.
- **Acceptance:** [ ] incremental run loads only new/changed rows via watermark; [ ] SCD2 keeps
  history with valid-from/valid-to; [ ] REST connector paginates + respects rate limits.
- **Demo:** incremental load twice â€” second run touches only deltas; show SCD2 history rows.

### v0.7 â€” Multi-tenancy + admin + security hardening
- **Goal:** SaaS realism and a secure default.
- **Build:** workspaces (org isolation across all queries); admin (user/role management, platform
  config, system health); Fernet-encrypted credentials at rest; audit logs; API rate limiting;
  idempotency keys; `/api/v1` versioning; PII masking on serializers; least-privilege review.
- **Acceptance:** [ ] a user in workspace A cannot see workspace B's resources; [ ] credentials are
  encrypted in the DB; [ ] audit log records sensitive actions; [ ] rate limit returns 429.
- **Demo:** two workspaces, isolation proven; show an encrypted credential row and the audit trail.

### v0.8 â€” React dashboard (optional but high-impact)
- **Goal:** a visual portfolio surface.
- **Build:** React SPA â€” login, data sources, pipeline builder, run history + live status, metrics,
  lineage graph, quality scorecards. Talks to the REST API.
- **Acceptance:** [ ] can create + run a pipeline from the UI; [ ] run status updates; [ ] lineage +
  scorecards render.
- **Demo:** full loop performed entirely in the browser.

### v0.9 â€” CI/CD, deploy, load & chaos tests, docs
- **Goal:** reproducible delivery and proven resilience.
- **Build:** GitHub Actions (lint + test + build + optional deploy); deploy to Render (free tier);
  Locust load test; a **chaos test** that kills a worker mid-run and asserts recovery; complete
  `docs/` and diagrams; contributing guide.
- **Acceptance:** [ ] CI green on PRs; [ ] app deployed at a public URL; [ ] load test report;
  [ ] chaos test shows the run recovers/retries cleanly.
- **Demo:** open the live URL; show the CI run and the chaos-test result.

### v1.0 â€” Polish + portfolio
- **Goal:** ship-ready and interview-ready.
- **Build:** README polish + screenshots + demo GIF; portfolio case study; release notes;
  resume bullets + STAR stories + interview Q&A (I can generate these in chat from the final repo).
- **Acceptance:** [ ] a stranger can clone, run, and understand it from the README alone.

---

## 5. Enhancement â†’ milestone map

| Enhancement                          | Lands in |
|--------------------------------------|----------|
| Data lineage (table + column)        | v0.4     |
| Medallion (bronze/silver/gold, DuckDB/Parquet) | v0.4 |
| Data-quality scorecards + trends     | v0.3     |
| Schema drift + evolution + contracts | v0.3â€“v0.4|
| CDC / incremental + watermarks       | v0.6     |
| SCD Type 2                           | v0.6     |
| Idempotent/resumable runs + DLQ      | v0.2     |
| Retries, backoff, circuit breakers   | v0.2/v0.6|
| OpenTelemetry tracing                | v0.5     |
| Prometheus + Grafana                 | v0.5     |
| Multi-tenant workspaces              | v0.7     |
| Encrypted secrets, audit, rate limit | v0.7     |
| React dashboard                      | v0.8     |
| Load test (Locust) + chaos test      | v0.9     |
| dbt for gold transforms (optional)   | v0.4/v0.6 (roadmap if time-boxed) |

---

## 6. Risks & mitigations

| Risk                                        | Impact | Mitigation                                                    |
|---------------------------------------------|--------|---------------------------------------------------------------|
| Scope creep (all enhancements at once)      | High   | Milestone gates; extras go to Future Scope on the roadmap      |
| Heavy deps (Great Expectations) slow setup  | Medium | Keep GE optional; start with lightweight custom + Pandera      |
| Local-only limits realism                   | Medium | Docker mirrors prod topology; deploy to Render for a live demo |
| ETL engine coupling to Django creeps in     | Medium | Enforce the no-Django-imports rule; unit-test the engine alone |
| Data corruption / bad loads                 | High   | Blocking validation, idempotent loads, backups, DLQ            |
| Secrets leakage                             | High   | Fernet encryption at rest, `.env` gitignored, audit logs       |
| Burnout from doing everything manually      | Medium | Delegate implementation to Claude Code; use chat for design    |

---

## 7. Ways of working

- **Branching:** short-lived feature branches â†’ PR â†’ `main`. Protect `main`.
- **Commits:** conventional commits; **semantic versioning** with a tag per milestone.
- **Decisions:** every non-trivial choice gets an ADR in `docs/adr/`.
- **Tracking:** GitHub Issues + a milestone per version + a public roadmap in the README.
- **Quality gate:** no version is "done" until tests are green, the demo works, and it's committed.

## 8. Who does what

| Role            | Responsibility                                                        |
|-----------------|-----------------------------------------------------------------------|
| You (owner/PM)  | Direction, review diffs, run demos, commit/tag, deploy                 |
| Claude Code     | Implement each milestone in the repo per `CLAUDE.md` + this plan       |
| Claude (chat)   | Architecture calls, code review, ADRs, docs, resume/interview prep     |
