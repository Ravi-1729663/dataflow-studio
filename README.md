# DataFlow Studio

> A multi-tenant data platform — register data sources, build validated ETL/ELT pipelines with
> automated cleansing and statistical anomaly detection, govern data with a lineage catalog, and
> monitor every run through a React dashboard and a documented REST API.

**Live demo:** _[add your Render URL here once deployed — see `docs/05-deployment.md`]_
**License:** MIT · **Author:** Ravi Sankar Reddy Bovilla

[![CI](https://github.com/Ravi-1729663/dataflow-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/Ravi-1729663/dataflow-studio/actions/workflows/ci.yml)

---

## The problem this solves

Every company that isn't purely a spreadsheet shop eventually needs the same thing: pull data out
of a pile of different systems (a CSV someone emailed, a production Postgres replica, a partner's
REST API, an S3 bucket), make sure it isn't garbage before it lands anywhere important, reshape it,
and load it somewhere queryable — reliably, on a schedule, without one team's data source being
readable by another team, and with enough of a paper trail that when something looks wrong six
months later you can actually find out why.

In industry, that's usually five separate vendors stitched together: Fivetran/Airbyte for
ingestion, dbt for transforms, Great Expectations or Monte Carlo for quality/observability, Airflow
for orchestration, and a home-grown multi-tenancy + security layer on top of all of it. **DataFlow
Studio is a single, coherent system that implements a working (if intentionally smaller-scale)
version of that entire stack** — built solo, end to end, to prove the underlying platform-engineering
competency rather than to compete with any one of those tools.

## What it actually does

- **Ingest** from a file, a Postgres query, a paginated REST API, or an S3-compatible bucket (real
  AWS S3 or a free self-hosted MinIO — same code path either way).
- **Clean** the raw batch before it's judged: trim whitespace, normalize case, fill missing values
  with a default, drop rows that don't meet a completeness threshold — so a pipeline can repair
  fixable data instead of either failing outright or silently loading garbage.
- **Validate** against 9 configurable rule types (required columns, nulls, uniqueness, ranges,
  allowed values, freshness, custom expressions, ...), each independently blocking or
  warning-only, producing a quality scorecard with a historical trend per pipeline.
- **Detect statistical anomalies** — every numeric column's mean is checked against a running
  baseline (updated via Welford's online algorithm) and flagged if it drifts more than 3 standard
  deviations, the same mechanism behind commercial data-observability tools, implemented from
  scratch.
- **Transform and load** idempotently (safe to re-run), either as a plain upsert or full
  Slowly-Changing-Dimension-Type-2 history, into a served "gold" warehouse table.
- **Track lineage and schema drift** automatically for every dataset, queryable as a graph and
  browsable in the UI.
- **Isolate tenants**: workspaces, RBAC, Fernet-encrypted credentials at rest, audit logging of
  every sensitive action, rate limiting, and PII masking — enforced at the database query level,
  not just the UI.
- **Recover from failure**: automatic retry with backoff, dead-letter queues for exhausted runs,
  and Celery reliability settings that let a killed worker's in-flight task be picked up cleanly by
  a replacement — proven with an actual chaos test, not just a claim (see below).

## Proof, not claims

| Claim | Evidence |
|---|---|
| "It's tested" | 167 automated tests, `ruff`/`black` clean, CI on every push/PR |
| "It handles load" | Locust: 1,203 requests, 25 concurrent users, **0% failure rate**, p95 latency 88ms — [`loadtest/README.md`](loadtest/README.md) |
| "It recovers from failure" | A script hard-kills a real Celery worker mid-pipeline-run and proves the run still completes correctly on a replacement worker — [`docs/06-resilience.md`](docs/06-resilience.md), [`docs/reports/chaos-test-report.md`](docs/reports/chaos-test-report.md) |
| "It's deployable" | Infrastructure-as-code (`render.yaml`) + Docker Compose, both documented in [`docs/05-deployment.md`](docs/05-deployment.md) |

## Screenshots

_[Add screenshots here once you've clicked through the deployed app — Data Sources, Pipeline
Builder, Pipeline detail with run history, Dashboard (with the anomalies panel), Lineage graph,
Scorecards. Drop them in a `docs/screenshots/` folder and reference them here. A 30-60s demo GIF
of the full create → run → watch-it-succeed loop is worth more than any of the bullet points
above.]_

## Quickstart

**Local, zero setup (SQLite, synchronous pipelines):**

```bash
make install
make migrate
make seed      # demo user + datasource + pipeline, runs end-to-end
make run       # API on http://localhost:8000  (docs at /api/docs/)
make test
```

**React dashboard** (talks to the API above — run alongside it):

```bash
make frontend-install
make frontend-dev   # SPA on http://localhost:5173
```

**Full stack** (Postgres + Redis + real Celery worker + MinIO + Prometheus + Grafana):

```bash
cp .env.example .env
make docker-up
```

Deploying it for free (Render) is in [`docs/05-deployment.md`](docs/05-deployment.md), including a
walkthrough for testing cleansing/anomaly detection/S3 on the live instance using the demo CSVs in
`sample_data/`.

## Architecture

A **modular monolith** in Django — one Django app per bounded context (`apps/`), a
framework-agnostic ETL engine with zero Django imports so it's independently testable, and a
React/TypeScript SPA talking to the same REST API. Requests hit DRF; pipeline runs execute the
engine (extract → clean → validate → transform → load) either synchronously (local dev / the free
deployment) or via Celery workers (docker-compose); every step emits metrics, structured logs, and
lineage. Full diagrams and the rationale — including what was considered and rejected — are in
[`docs/03-architecture.md`](docs/03-architecture.md).

```
config/         Django project (settings/, urls, celery, wsgi/asgi)
apps/
  common/         BaseModel, logging, exceptions, health, idempotency
  accounts/       User + JWT + RBAC
  workspaces/     multi-tenant org isolation
  audit/          sensitive-action audit trail
  platform_admin/ user/role management, platform config, extended health
  datasources/    DataSource + connectors (file / postgres / rest_api / s3)
  etl/            extract / clean / validate / transform / load / engine  (no Django imports)
  pipelines/      Pipeline + PipelineRun + execute service + celery tasks
  scheduler/      cron on django-celery-beat
  validation/     rules + data-quality scorecards
  metadata/       dataset registry, schema history, lineage, statistical anomaly detection
  monitoring/     metrics + execution dashboard
  notifications/  email / Slack alerts
  warehouse/      served gold tables + query API
frontend/       React + TypeScript SPA — talks to the REST API
docs/           requirements, scope, architecture, deployment, resilience, ADRs
loadtest/       Locust load test + latest report
scripts/        chaos_test.py
.github/        CI
```

## Tech stack

| Area          | Tech                                             |
|---------------|--------------------------------------------------|
| API           | Django 5, Django REST Framework, drf-spectacular |
| Auth          | JWT (SimpleJWT), custom RBAC                      |
| Frontend      | React + TypeScript (Vite), react-router, recharts |
| Async / cron  | Celery, Redis, django-celery-beat                |
| Storage       | PostgreSQL (SQLite local), DuckDB + Parquet, S3-compatible object storage (boto3 + MinIO) |
| Data quality  | pandas, custom validation/cleansing engine, Welford's-algorithm anomaly detection |
| Observability | django-prometheus, Grafana, structured logs, OpenTelemetry |
| DevOps        | Docker, docker-compose, GitHub Actions, Render (Blueprint), Locust |

## Documentation

- [`docs/01-requirements.md`](docs/01-requirements.md), [`docs/02-scope.md`](docs/02-scope.md) — what this is and isn't
- [`docs/03-architecture.md`](docs/03-architecture.md) — diagrams + decisions (with rejected alternatives)
- [`docs/04-modules.md`](docs/04-modules.md) — what every app does, one paragraph each
- [`docs/05-deployment.md`](docs/05-deployment.md) — Render + docker-compose, step by step
- [`docs/06-resilience.md`](docs/06-resilience.md) — load test + chaos test methodology and results
- [`docs/07-portfolio-and-interviews.md`](docs/07-portfolio-and-interviews.md) — how to present this project, STAR stories, and answers to the tough interview questions
- [`docs/08-rebuild-runbook.md`](docs/08-rebuild-runbook.md) — every account/secret/step needed to rebuild this from nothing, plus a troubleshooting table of real incidents hit while building it
- [`docs/adr/`](docs/adr/) — architecture decision records
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — conventions, how CI gates a PR
- [`PROJECT_PLAN.md`](PROJECT_PLAN.md) — the milestone-by-milestone build plan this was built against

## License

MIT — see [`LICENSE`](LICENSE).
