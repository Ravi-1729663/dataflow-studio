# DataFlow Studio - one-shot scaffold generator
# Run this from INSIDE your dataflow-studio folder (where .git lives):
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = 'Stop'
Write-Host 'Creating DataFlow Studio scaffold...' -ForegroundColor Cyan

$content = @'
# ---- Django ----
DJANGO_SECRET_KEY=change-me-in-production
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=*
DJANGO_SETTINGS_MODULE=config.settings.local
LOG_LEVEL=INFO

# ---- Database ----
# Local dev uses SQLite automatically. For the full stack set USE_POSTGRES=1.
USE_POSTGRES=0
POSTGRES_DB=dataflow
POSTGRES_USER=dataflow
POSTGRES_PASSWORD=dataflow
POSTGRES_HOST=db
POSTGRES_PORT=5432

# ---- Celery / Redis ----
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
# Runs pipelines synchronously in-process when 1 (great for local dev/tests)
CELERY_TASK_ALWAYS_EAGER=1

# ---- Security ----
# Fernet key used to encrypt data-source credentials at rest.
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FERNET_KEY=

# ---- Email (notifications) ----
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend

'@
Set-Content -Path ".env.example" -Value $content -NoNewline -Encoding UTF8

$content = @'
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
env/

# Django
db.sqlite3
db.sqlite3-journal
/staticfiles/
/media/

# Env & secrets
.env
*.pem

# Data artifacts
/data/
*.parquet
*.duckdb

# Test / tooling
.pytest_cache/
.coverage
htmlcov/
.ruff_cache/

# OS / editor
.DS_Store
.idea/
node_modules/

'@
Set-Content -Path ".gitignore" -Value $content -NoNewline -Encoding UTF8

$content = @'
# CLAUDE.md — Build Instructions for Claude Code

> Read this file **and** `PROJECT_PLAN.md` before writing any code. This file defines *how* to
> build; `PROJECT_PLAN.md` defines *what* to build and *in what order*. Follow the milestones
> strictly, one version at a time.

## What this project is

**DataFlow Studio** — an internal enterprise data platform. Teams register data sources, build
and schedule ETL/ELT pipelines, validate and govern the data, and monitor everything through a
documented REST API and dashboards. Backend is a **modular monolith** in Django.

## Stack (do not substitute without an ADR)

| Layer         | Choice                                             |
|---------------|----------------------------------------------------|
| Language      | Python 3.12                                        |
| Web/API       | Django 5 + Django REST Framework                   |
| Auth          | djered SimpleJWT (JWT), custom RBAC                 |
| Async/queue   | Celery + Redis                                     |
| Scheduler     | django-celery-beat (DB-backed cron)                |
| OLTP store    | PostgreSQL (SQLite for zero-setup local dev/tests) |
| Analytics     | DuckDB + Parquet (local medallion, v0.4+)          |
| Data          | pandas                                             |
| Docs          | drf-spectacular (OpenAPI + Swagger UI)             |
| Observability | django-prometheus, Grafana, structured JSON logs   |
| Packaging     | Docker + docker-compose                            |
| CI            | GitHub Actions                                     |

> Note: "djered SimpleJWT" above is a typo-safe reminder — the package is
> `djangorestframework-simplejwt`. Import from `rest_framework_simplejwt`.

## Golden rules

1. **Modular monolith, one Django app per bounded context.** Apps live under `apps/`. Never let
   one app import another app's internals — go through its public services/serializers only.
2. **The ETL engine (`apps/etl/`) is framework-agnostic.** It must not import Django models. It
   receives plain specs (dicts/dataclasses) and a `loader` callable. The `pipelines` app is the
   only place that bridges Django models to the engine. This keeps the engine unit-testable and
   swappable.
3. **Clean layering per app:** `models.py` (data) → `services.py` (business logic) →
   `views.py`/`serializers.py` (HTTP). Views stay thin; logic lives in services.
4. **Config comes from the environment.** No secrets, hosts, or paths hardcoded. Read via
   `os.environ` in `config/settings/`. Data-source credentials are encrypted at rest with Fernet.
5. **Every module ships with tests.** Pure logic (ETL, validation) → fast unit tests, no DB.
   Anything touching models → `@pytest.mark.django_db` integration tests.
6. **Structured logging everywhere.** Use `logging.getLogger("dataflow.<area>")` and pass context
   via `extra={...}`. No bare `print`.
7. **UUID primary keys on domain models** (DataSource, Pipeline, PipelineRun, Dataset, …) via a
   shared `apps/common/models.BaseModel`. The `User` model may keep the default integer PK.
8. **Flexible config as JSON.** Pipeline/validation/transform specs are stored in `JSONField`s so
   the schema can evolve without migrations.

## Repository layout

```
dataflow-studio/
├── config/                 # Django project: settings/, urls.py, celery.py, wsgi.py, asgi.py
│   └── settings/           # base.py, local.py, production.py
├── apps/
│   ├── common/             # BaseModel, logging, exceptions, custom DRF exception handler, health
│   ├── accounts/           # User, JWT auth, RBAC permissions
│   ├── datasources/        # DataSource model + connectors/ (file, postgres, rest_api)
│   ├── etl/                # extract / validate / transform / load / engine  (NO Django imports)
│   ├── pipelines/          # Pipeline, PipelineRun, execute service, celery tasks, loaders
│   ├── scheduler/          # cron schedules on top of django-celery-beat
│   ├── validation/         # validation rules + data-quality scorecards
│   ├── metadata/           # dataset registry, schema history, column metadata, lineage
│   ├── monitoring/         # execution metrics + Prometheus counters
│   ├── notifications/      # email/Slack alerts on run events
│   └── warehouse/          # target/serving tables + query API (the "gold" layer)
├── docs/                   # requirements, scope, architecture, ADRs
├── monitoring/             # prometheus.yml, grafana provisioning
├── scripts/                # one-off scripts
├── sample_data/            # demo CSVs
├── .github/workflows/      # CI
└── manage.py
```

## Coding standards

- Format with **black**, lint with **ruff** (`make format`, `make lint`). CI runs `ruff check .`.
- Type hints on public functions; docstrings on modules, services, and non-obvious functions.
- DRF: `ModelViewSet` for CRUD, `@action` for verbs like `run`, `PageNumberPagination`,
  `DjangoFilterBackend` for filters, consistent error envelope from the common exception handler.
- Querysets are always scoped to the requesting user/workspace — never leak another tenant's rows.
- Conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`.

## How to build (per milestone)

For each version in `PROJECT_PLAN.md`, in order:

1. Implement the features listed for that version.
2. Write the tests the acceptance criteria imply.
3. Run `make makemigrations && make migrate && make test` — the suite must be green.
4. Run `make seed` (v0.1+) and confirm the demo path works.
5. Commit with a conventional message and tag the version (`git tag v0.1.0`).
6. Only then move to the next version.

## Definition of Done (per module)

- [ ] Models + migrations
- [ ] Service layer with business logic (not in views)
- [ ] Serializers + thin viewset(s) + URLs registered
- [ ] Permissions enforced and querysets scoped
- [ ] Structured logging on the important paths
- [ ] Unit and/or integration tests, green
- [ ] Appears in the OpenAPI schema (`/api/docs/`)
- [ ] A one-paragraph entry added to `docs/04-modules.md` if behaviour changed

## Do NOT

- Put multiple concerns in one giant file.
- Import Django inside `apps/etl/`.
- Skip tests "to save time."
- Hardcode secrets, credentials, hostnames, or file paths.
- Cross app boundaries by reaching into another app's models/internals.
- Build later milestones before the earlier ones are green and committed.

## Commands

```
make install      # deps
make migrate      # apply migrations
make seed         # demo user + datasource + pipeline, runs end-to-end
make run          # dev server on :8000
make worker       # celery worker
make test         # pytest
make docker-up    # full stack: web, worker, beat, postgres, redis, prometheus, grafana
```

'@
Set-Content -Path "CLAUDE.md" -Value $content -NoNewline -Encoding UTF8

$content = @'
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3"]

'@
Set-Content -Path "Dockerfile" -Value $content -NoNewline -Encoding UTF8

$content = @'
MIT License

Copyright (c) 2026 Ravi Sankar Reddy Bovilla

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

'@
Set-Content -Path "LICENSE" -Value $content -NoNewline -Encoding UTF8

$content = @'
.PHONY: install migrate makemigrations seed run worker beat test lint format docker-up docker-down clean

install:            ## Install dev + runtime dependencies
	pip install -r requirements-dev.txt

makemigrations:     ## Create new migrations
	python manage.py makemigrations

migrate:            ## Apply migrations
	python manage.py migrate

seed:               ## Seed a demo user + datasource + pipeline and run it end-to-end
	python manage.py seed_demo

run:                ## Run the API (dev server)
	python manage.py runserver 0.0.0.0:8000

worker:             ## Run a Celery worker
	celery -A config worker -l info

beat:               ## Run the Celery beat scheduler
	celery -A config beat -l info

test:               ## Run the test suite
	pytest

lint:               ## Lint with ruff
	ruff check .

format:             ## Format with black + ruff
	black . && ruff check --fix .

docker-up:          ## Start the full stack (web, worker, db, redis, prometheus, grafana)
	docker compose up --build

docker-down:        ## Stop the stack
	docker compose down -v

clean:              ## Remove caches and local db
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage db.sqlite3
	find . -type d -name __pycache__ -exec rm -rf {} +

'@
Set-Content -Path "Makefile" -Value $content -NoNewline -Encoding UTF8

$content = @'
# DataFlow Studio — Project Plan

**Owner:** Ravi Sankar Reddy Bovilla · **Status:** Planning → Build · **Version target:** v1.0

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
| End-to-end pipeline works          | CSV/API/DB source → validate → transform → warehouse → query |
| Pipeline success rate (demo data)  | ≥ 99% on healthy inputs                          |
| Test coverage on core logic        | ≥ 80% for `etl` + `pipelines` + `validation`     |
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

## 3. Build strategy — version by version (decision)

**Decision:** build incrementally, one release at a time, each independently runnable, tested, and
committed. **Rejected:** "build everything, then debug."

**Why incremental wins**

- **Always shippable.** Every version boots and demos on its own — you never sit on a broken tree.
- **Scoped debugging.** A regression came from the *last* increment, not from 5,000 lines across
  11 modules. Mean-time-to-fix stays low.
- **No compounding integration bugs.** Interfaces are exercised as they land, not all at once.
- **The story sells you.** Milestones + semantic versions + ADRs are exactly the signal hiring
  managers read as "this person operates like an engineer, not a script-runner."

**Why not slow:** each version is a single Claude Code session — many files, tests, and fixes in
one go. You simply *gate* each version (green tests + a demo) before starting the next.

---

## 4. Milestone plan

Each milestone: **Goal · Build · Acceptance · Demo.** Tag on completion (`v0.x.0`).

### v0.1 — Walking skeleton  *(foundation; prove the architecture end-to-end)*
- **Goal:** the thinnest complete path works and the layering holds.
- **Build:** Django project + env-based settings; `common` (BaseModel, logging, exceptions, health);
  `accounts` (custom User + JWT + RBAC); `datasources` (FILE source + file connector);
  `etl` (extract/validate/transform/load/engine); `pipelines` (Pipeline + PipelineRun + execute
  service + celery task); `warehouse` (a demo target table + query API); `seed_demo` command;
  unit + integration tests; Dockerfile + compose; README.
- **Acceptance:**
  - [ ] `make seed` ingests `sample_data/customers.csv` → rows land in the warehouse table.
  - [ ] `GET /api/warehouse/customers/` returns data (JWT required).
  - [ ] `make test` is green (ETL unit tests + one end-to-end pipeline test).
  - [ ] `docker compose up` boots web + worker + db + redis.
  - [ ] `/api/docs/` renders the schema.
- **Demo:** register → login → create datasource → create pipeline → run → query results.

### v0.2 — Pipeline engine + scheduler + async
- **Goal:** real orchestration, not a single synchronous call.
- **Build:** pipeline lifecycle (create/edit/clone/pause/resume/execute); Celery async execution
  with `run_pipeline_task`; `scheduler` app on django-celery-beat (cron per pipeline, manual run,
  retry failed job, queue view); retries with exponential backoff + a dead-letter record for failed
  runs; run history + metrics per run.
- **Acceptance:** [ ] a scheduled pipeline fires on cron in the worker; [ ] a failing run retries N
  times then lands in FAILED with an error + traceback; [ ] pause/resume respected; [ ] runs are
  idempotent (re-running does not double-load).
- **Demo:** schedule a pipeline every 2 min, watch runs accrue, pause it, force a failure, see retry.

### v0.3 — Validation engine + data-quality scorecards
- **Goal:** trustworthy data with visible quality.
- **Build:** `validation` app — schema, null, duplicate, data-type, range, referential-integrity,
  freshness, and business-rule checks (pluggable; optionally back with Great Expectations/Pandera);
  per-run **quality scorecard** (completeness/consistency/accuracy %) persisted with history and
  trend; blocking vs warning checks; contract to fail a run on blocking violations.
- **Acceptance:** [ ] a dataset with nulls/dupes produces a scorecard with a numeric score;
  [ ] a blocking failure stops the load; [ ] scorecard history is queryable via API.
- **Demo:** run clean vs dirty data, compare scorecards and the trend.

### v0.4 — Metadata catalog + lineage + medallion
- **Goal:** governance and modern lakehouse layering.
- **Build:** `metadata` app — dataset registry, schema history/versioning, column metadata,
  table- and column-level **lineage** (source → bronze → silver → gold); local **medallion** layers
  as Parquet queried via DuckDB; schema-drift detection on ingest.
- **Acceptance:** [ ] lineage graph resolvable for any warehouse table; [ ] schema history records a
  column add/rename; [ ] bronze/silver/gold Parquet layers produced and queryable via DuckDB;
  [ ] a drifted source is flagged.
- **Demo:** show the lineage graph and the medallion layers for the customers pipeline.

### v0.5 — Observability + alerting + notifications
- **Goal:** operate it like production.
- **Build:** `monitoring` (Prometheus counters/histograms: runs, durations, rows, failures;
  Grafana dashboard JSON); execution dashboard API (success rate, failed jobs, runtime metrics);
  structured JSON logs with correlation/run IDs; OpenTelemetry tracing API→worker;
  `notifications` (email + Slack webhook on failure/completion/retry); health checks.
- **Acceptance:** [ ] `/metrics` exposes pipeline metrics; [ ] Grafana renders the dashboard;
  [ ] a failed run sends an alert; [ ] logs carry a run/correlation id end-to-end.
- **Demo:** trigger a failure → alert fires → trace + logs pinpoint the failing step.

### v0.6 — More connectors + incremental/CDC + SCD2
- **Goal:** ingest from real systems, load efficiently.
- **Build:** Postgres source connector + REST API connector (pagination, rate limiting, retries);
  incremental loads with watermark tracking; Slowly Changing Dimension **Type 2** handling; late-
  arriving data strategy; batch tuning + Parquet partitioning.
- **Acceptance:** [ ] incremental run loads only new/changed rows via watermark; [ ] SCD2 keeps
  history with valid-from/valid-to; [ ] REST connector paginates + respects rate limits.
- **Demo:** incremental load twice — second run touches only deltas; show SCD2 history rows.

### v0.7 — Multi-tenancy + admin + security hardening
- **Goal:** SaaS realism and a secure default.
- **Build:** workspaces (org isolation across all queries); admin (user/role management, platform
  config, system health); Fernet-encrypted credentials at rest; audit logs; API rate limiting;
  idempotency keys; `/api/v1` versioning; PII masking on serializers; least-privilege review.
- **Acceptance:** [ ] a user in workspace A cannot see workspace B's resources; [ ] credentials are
  encrypted in the DB; [ ] audit log records sensitive actions; [ ] rate limit returns 429.
- **Demo:** two workspaces, isolation proven; show an encrypted credential row and the audit trail.

### v0.8 — React dashboard (optional but high-impact)
- **Goal:** a visual portfolio surface.
- **Build:** React SPA — login, data sources, pipeline builder, run history + live status, metrics,
  lineage graph, quality scorecards. Talks to the REST API.
- **Acceptance:** [ ] can create + run a pipeline from the UI; [ ] run status updates; [ ] lineage +
  scorecards render.
- **Demo:** full loop performed entirely in the browser.

### v0.9 — CI/CD, deploy, load & chaos tests, docs
- **Goal:** reproducible delivery and proven resilience.
- **Build:** GitHub Actions (lint + test + build + optional deploy); deploy to Render (free tier);
  Locust load test; a **chaos test** that kills a worker mid-run and asserts recovery; complete
  `docs/` and diagrams; contributing guide.
- **Acceptance:** [ ] CI green on PRs; [ ] app deployed at a public URL; [ ] load test report;
  [ ] chaos test shows the run recovers/retries cleanly.
- **Demo:** open the live URL; show the CI run and the chaos-test result.

### v1.0 — Polish + portfolio
- **Goal:** ship-ready and interview-ready.
- **Build:** README polish + screenshots + demo GIF; portfolio case study; release notes;
  resume bullets + STAR stories + interview Q&A (I can generate these in chat from the final repo).
- **Acceptance:** [ ] a stranger can clone, run, and understand it from the README alone.

---

## 5. Enhancement → milestone map

| Enhancement                          | Lands in |
|--------------------------------------|----------|
| Data lineage (table + column)        | v0.4     |
| Medallion (bronze/silver/gold, DuckDB/Parquet) | v0.4 |
| Data-quality scorecards + trends     | v0.3     |
| Schema drift + evolution + contracts | v0.3–v0.4|
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

- **Branching:** short-lived feature branches → PR → `main`. Protect `main`.
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

'@
Set-Content -Path "PROJECT_PLAN.md" -Value $content -NoNewline -Encoding UTF8

$content = @'
# DataFlow Studio

> An internal enterprise **data platform**: register data sources, build and schedule validated
> ETL/ELT pipelines, govern data with a metadata catalog and lineage, and monitor every run — all
> behind a documented REST API. Local-first and fully open-source.

**Status:** planning → build · **License:** MIT · **Owner:** Ravi Sankar Reddy Bovilla

---

## What's in this repository right now

This is the **blueprint + scaffold**. It contains the plan, the architecture, the conventions, and
the empty module structure — ready for implementation, milestone by milestone.

- [`PROJECT_PLAN.md`](PROJECT_PLAN.md) — scope, build strategy, and the v0.1→v1.0 milestone plan with
  tasks and acceptance criteria. **Start here.**
- [`CLAUDE.md`](CLAUDE.md) — engineering conventions and build rules for Claude Code.
- [`docs/`](docs/) — requirements, scope, architecture (with diagrams), module specs, and ADRs.

## How to build it (with Claude Code)

The repo and Claude Code are set up **first**; features are built *into* the repo, not bolted on at
the end.

```bash
# 1. Put this scaffold under version control (do this now, before writing features)
cd dataflow-studio
git init
git add -A
git commit -m "chore: project scaffold and blueprint"

# 2. (optional) create the remote and push
#    git remote add origin <your-repo-url> && git push -u origin main

# 3. Open the folder in VS Code and open Claude Code (extension or `claude` in the terminal).
#    It reads CLAUDE.md + PROJECT_PLAN.md automatically.

# 4. Tell Claude Code:
#    "Implement milestone v0.1 per PROJECT_PLAN.md and CLAUDE.md."
#    Review the diffs, run the tests, then commit and tag:
#      git tag v0.1.0

# 5. Repeat for v0.2 ... v1.0. Push to GitHub after v0.1.
```

Bring architecture questions, code reviews, ADRs, and interview/resume prep back to Claude in chat.

## Quickstart (once v0.1 is implemented)

**Local, zero setup (SQLite, synchronous pipelines):**

```bash
make install
make migrate
make seed      # creates a demo user + datasource + pipeline and runs it end-to-end
make run       # API on http://localhost:8000  (docs at /api/docs/)
make test
```

**Full stack (Postgres + Redis + Celery + Prometheus + Grafana):**

```bash
cp .env.example .env
make docker-up
# API :8000 · Prometheus :9090 · Grafana :3000
```

## Architecture (summary)

A **modular monolith** in Django with Celery workers. Requests hit the DRF API; pipelines are
enqueued to Redis and executed by workers that call a framework-agnostic ETL engine
(extract → validate → transform → load); results land in a warehouse/gold layer and are served over
the API; every step emits metrics, structured logs, and lineage. Full diagrams and the rationale
(with rejected alternatives) are in [`docs/03-architecture.md`](docs/03-architecture.md).

## Project structure

```
config/         Django project (settings/, urls, celery, wsgi/asgi)
apps/
  common/       BaseModel, logging, exceptions, health
  accounts/     User + JWT + RBAC
  datasources/  DataSource + connectors (file / postgres / rest_api)
  etl/          extract / validate / transform / load / engine  (no Django imports)
  pipelines/    Pipeline + PipelineRun + execute service + celery tasks
  scheduler/    cron on django-celery-beat
  validation/   rules + data-quality scorecards
  metadata/     dataset registry + schema history + lineage
  monitoring/   metrics + execution dashboard
  notifications/ email / Slack alerts
  warehouse/    served gold tables + query API
docs/           requirements, scope, architecture, ADRs
monitoring/     prometheus + grafana config
.github/        CI
```

## Tech stack

| Area          | Tech                                             |
|---------------|--------------------------------------------------|
| API           | Django 5, Django REST Framework, drf-spectacular |
| Auth          | JWT (SimpleJWT), custom RBAC                      |
| Async / cron  | Celery, Redis, django-celery-beat                |
| Storage       | PostgreSQL (SQLite local), DuckDB + Parquet       |
| Data          | pandas                                           |
| Observability | django-prometheus, Grafana, structured logs, OTel |
| DevOps        | Docker, docker-compose, GitHub Actions           |

## Roadmap

v0.1 walking skeleton · v0.2 pipeline engine + scheduler + async · v0.3 validation + quality
scorecards · v0.4 metadata + lineage + medallion · v0.5 observability + alerting · v0.6 connectors +
CDC + SCD2 · v0.7 multi-tenancy + security hardening · v0.8 React dashboard · v0.9 CI/CD + deploy +
resilience tests · v1.0 polish + portfolio. Details in [`PROJECT_PLAN.md`](PROJECT_PLAN.md).

## License

MIT — see [`LICENSE`](LICENSE).

'@
Set-Content -Path "README.md" -Value $content -NoNewline -Encoding UTF8

$content = @'
services:
  web:
    build: .
    env_file: .env
    environment:
      USE_POSTGRES: "1"
      CELERY_TASK_ALWAYS_EAGER: "0"
      DJANGO_SETTINGS_MODULE: config.settings.production
    ports:
      - "8000:8000"
    depends_on: [db, redis]

  worker:
    build: .
    command: celery -A config worker -l info
    env_file: .env
    environment:
      USE_POSTGRES: "1"
      CELERY_TASK_ALWAYS_EAGER: "0"
      DJANGO_SETTINGS_MODULE: config.settings.production
    depends_on: [db, redis]

  beat:
    build: .
    command: celery -A config beat -l info
    env_file: .env
    environment:
      USE_POSTGRES: "1"
      DJANGO_SETTINGS_MODULE: config.settings.production
    depends_on: [db, redis]

  db:
    image: postgres:16
    environment:
      POSTGRES_DB: dataflow
      POSTGRES_USER: dataflow
      POSTGRES_PASSWORD: dataflow
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7
    ports:
      - "6379:6379"

  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:latest
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
    volumes:
      - ./monitoring/grafana/provisioning:/etc/grafana/provisioning:ro
    ports:
      - "3000:3000"
    depends_on: [prometheus]

volumes:
  pgdata:

'@
Set-Content -Path "docker-compose.yml" -Value $content -NoNewline -Encoding UTF8

$content = @'
[pytest]
DJANGO_SETTINGS_MODULE = config.settings.local
python_files = tests.py test_*.py *_tests.py
addopts = -q --disable-warnings
testpaths = apps

'@
Set-Content -Path "pytest.ini" -Value $content -NoNewline -Encoding UTF8

$content = @'
-r requirements.txt
pytest>=8.2
pytest-django>=4.8
pytest-cov>=5.0
ruff>=0.5
black>=24.4
faker>=25.0
locust>=2.29        # load testing (v0.9)

'@
Set-Content -Path "requirements-dev.txt" -Value $content -NoNewline -Encoding UTF8

$content = @'
# ---- Core runtime (v0.1+) ----
Django>=5.0,<5.2
djangorestframework>=3.15
djangorestframework-simplejwt>=5.3
drf-spectacular>=0.27          # OpenAPI / Swagger docs
django-filter>=24.2
django-prometheus>=2.3         # /metrics endpoint
python-dotenv>=1.0

# ---- Async / scheduling (v0.2+) ----
celery>=5.4
redis>=5.0
django-celery-beat>=2.6        # DB-backed cron scheduler

# ---- Data processing ----
pandas>=2.2
pyarrow>=16.0                  # Parquet
duckdb>=1.0                    # local medallion / analytics engine (v0.4+)

# ---- Security ----
cryptography>=42.0            # Fernet secret encryption

# ---- Database driver & server ----
psycopg2-binary>=2.9
gunicorn>=22.0

# ---- Data quality (v0.3) -- uncomment when you reach that milestone ----
# great-expectations>=0.18
# pandera>=0.20

'@
Set-Content -Path "requirements.txt" -Value $content -NoNewline -Encoding UTF8

New-Item -ItemType Directory -Force -Path "monitoring" | Out-Null
$content = @'
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: dataflow-web
    metrics_path: /metrics
    static_configs:
      - targets: ["web:8000"]

'@
Set-Content -Path "monitoring/prometheus.yml" -Value $content -NoNewline -Encoding UTF8

New-Item -ItemType Directory -Force -Path "monitoring/grafana/provisioning/datasources" | Out-Null
$content = @'
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true

'@
Set-Content -Path "monitoring/grafana/provisioning/datasources/prometheus.yml" -Value $content -NoNewline -Encoding UTF8

New-Item -ItemType Directory -Force -Path ".github/workflows" | Out-Null
$content = @'
name: CI

on:
  push:
    branches: [ main ]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: pip install -r requirements-dev.txt
      - name: Lint
        run: ruff check .
      - name: Test
        run: pytest

'@
Set-Content -Path ".github/workflows/ci.yml" -Value $content -NoNewline -Encoding UTF8

New-Item -ItemType Directory -Force -Path "docs" | Out-Null
$content = @'
# Requirements Analysis

## Business problem
Organizations pull data from many places — files, spreadsheets, SQL databases, REST APIs, SaaS
tools — and stitch pipelines together manually. The result is inconsistent formats, duplicate and
low-quality records, silent ETL failures, no monitoring, painful debugging, and weak governance.
Companies spend heavily on internal platforms to fix exactly this. DataFlow Studio models such a
platform: a single place to connect sources, run and schedule validated pipelines, and observe
everything.

## Users
- **Primary:** Data Engineers, Backend Engineers, Analytics Engineers, Data Analysts.
- **Secondary:** Business Analysts, Product Managers, DevOps Engineers.
- **Admins:** Platform Administrators, Engineering Managers.

## Pain points addressed
Manual ETL execution · data inconsistency · missing validation · hard debugging · no monitoring ·
frequent pipeline failures · manual scheduling · missing metadata/lineage · poor governance ·
credential/security risk.

## Functional requirements (by module)
- **Access:** register/login, JWT, RBAC (Admin/Engineer/Analyst/Viewer), password reset, workspaces.
- **Data sources:** register file/DB/API sources, test connections, store credentials encrypted.
- **ETL:** extract, transform, load; batch and incremental; SCD2.
- **Pipelines:** create/edit/execute/clone/pause/resume; run history + metrics.
- **Scheduler:** cron schedules, manual runs, retry failed jobs, queue management.
- **Validation:** schema/null/duplicate/type/range/referential/freshness/business-rule checks.
- **Metadata:** dataset registry, schema history, column metadata, lineage.
- **Monitoring:** execution dashboard, runtime metrics, success rate, failed jobs.
- **Logging:** application/pipeline/API/security/audit logs.
- **Notifications:** email/Slack alerts on failure, completion, retry.
- **Admin:** user/role management, platform config, system health.

## Non-functional requirements
- **Performance:** responsive API, efficient ETL, tuned queries.
- **Scalability:** stateless API, horizontal workers, modular apps.
- **Reliability:** automatic retries, health checks, graceful failure, idempotency.
- **Availability:** high uptime, minimal-downtime deploys.
- **Security:** JWT, hashed passwords, RBAC, encrypted secrets, HTTPS, audit.
- **Maintainability:** clean layered code, documentation, ADRs.
- **Observability:** structured logs, metrics, dashboards, alerts, tracing.
- **Portability:** Docker, env-based config.
- **Testability:** unit, integration, and API tests.

## Success metrics (KPIs)
See `PROJECT_PLAN.md` §1 — end-to-end pipeline works; ≥99% success on healthy data; ≥80% coverage on
core logic; 100% of endpoints documented; failures alert; `docker compose up` reproduces the stack.

## Assumptions
- Portfolio scale: thousands→low-millions of rows per run, not petabyte streaming.
- Local-first, open-source stack; a single public demo deploy (Render free tier).
- One owner/developer, with Claude Code implementing to this spec.

## Constraints
- No paid cloud; GCP free tier only if something cannot run locally.
- Effort is time-boxed by milestone; non-core enhancements move to Future Scope.

## Risks
See `PROJECT_PLAN.md` §6 (scope creep, heavy deps, coupling, data corruption, secrets, burnout) with
mitigations.

'@
Set-Content -Path "docs/01-requirements.md" -Value $content -NoNewline -Encoding UTF8

New-Item -ItemType Directory -Force -Path "docs" | Out-Null
$content = @'
# Scope

## In scope (through v1.0)
Auth + RBAC + workspaces + admin · file/Postgres/REST sources · ETL engine (batch + incremental,
SCD2) · validation engine + quality scorecards · pipeline engine + cron scheduler + retries ·
metadata catalog + lineage · monitoring + logging + alerting + notifications · versioned documented
REST API + optional React dashboard · Docker + CI/CD + tests + encrypted secrets.

## Out of scope (v1.0)
Real-time streaming (Kafka/Flink) · cloud-managed warehouses · ML training / feature store · native
mobile app · multi-region high availability.

## Future scope (roadmap)
Streaming + log-based CDC · Snowflake/BigQuery connectors · ML feature store + model serving ·
mobile companion · multi-region active-active · cost-governance dashboard · auto column-level lineage.

## MVP vs Enterprise
- **MVP (v0.1–v0.3):** auth, one source type, pipeline execution + scheduling, validation +
  scorecards. A working, demoable platform.
- **Enterprise (v0.4–v1.0):** lineage + medallion, full observability + tracing, multiple connectors
  + CDC + SCD2, multi-tenancy + security hardening, dashboard, CI/CD + deploy + resilience tests.

Per-version scope lives in `PROJECT_PLAN.md` §4.

'@
Set-Content -Path "docs/02-scope.md" -Value $content -NoNewline -Encoding UTF8

New-Item -ItemType Directory -Force -Path "docs" | Out-Null
$content = @'
# Architecture

DataFlow Studio is a **modular monolith**: one deployable Django application composed of
independent apps (bounded contexts), with heavy work pushed to Celery workers. This gives the
maintainability and clean boundaries of services without the operational tax of a distributed
system at portfolio scale.

## System context

```mermaid
flowchart LR
    User([Engineer / Analyst])
    Admin([Platform Admin])
    Ext[(External sources:\nFiles · Postgres · REST APIs)]

    subgraph DFS[DataFlow Studio]
      API[REST API + OpenAPI]
      UI[React Dashboard]
      Core[Pipeline / ETL / Validation core]
      Store[(PostgreSQL)]
      Lake[(Parquet + DuckDB\nbronze/silver/gold)]
      Obs[Metrics · Logs · Traces · Alerts]
    end

    User --> UI --> API
    Admin --> API
    API --> Core
    Core --> Ext
    Core --> Store
    Core --> Lake
    Core --> Obs
```

## Components (containers)

```mermaid
flowchart TB
    Client[Client / React SPA] -->|JWT| APIGW[Django + DRF API]

    subgraph Apps[Modular monolith apps]
      ACC[accounts / RBAC]
      DS[datasources + connectors]
      PIPE[pipelines]
      SCHED[scheduler]
      VAL[validation]
      META[metadata + lineage]
      MON[monitoring]
      NOTIF[notifications]
      WH[warehouse / serving]
    end

    APIGW --> Apps
    PIPE -->|enqueue| BROKER[(Redis broker)]
    BROKER --> WORK[Celery workers]
    BEAT[Celery beat cron] --> BROKER
    WORK -->|calls| ETL[[etl engine\nframework-agnostic]]
    ETL --> DSQ[(source systems)]
    ETL --> PG[(PostgreSQL)]
    ETL --> LAKE[(Parquet / DuckDB)]
    WORK --> MON
    WORK --> NOTIF
    MON --> PROM[Prometheus] --> GRAF[Grafana]
```

## ETL execution flow

```mermaid
flowchart LR
    R[Raw source] --> E[Extract\nconnector]
    E --> V[Validate\nschema/null/dup/rules]
    V -->|blocking fail| X[Run FAILED\n+ alert + DLQ]
    V -->|pass/warn| T[Transform\nrename/cast/dedupe/SCD2]
    T --> L[Load\nidempotent upsert]
    L --> WH[(Warehouse / gold)]
    WH --> Q[Query API / Dashboard]
    E & V & T & L --> M[Metrics + structured logs + lineage]
    WH --> A{Threshold breach?}
    A -->|yes| ALERT[Notify email/Slack]
```

**Lifecycle in words:** a source is registered → a pipeline defines its validation, transform, and
target specs → the pipeline is run (manually, via API, or on a cron schedule) → a Celery worker
invokes the framework-agnostic ETL engine → the engine extracts, validates (blocking checks can
stop the run), transforms, and idempotently loads into the warehouse → every step emits metrics,
structured logs, and lineage → the served data is queryable over the API and dashboard →
threshold breaches or failures raise alerts and, if needed, land failed records in a dead-letter
record for reprocessing.

## Deployment (docker-compose topology)

```mermaid
flowchart TB
    web[web: gunicorn + Django] --> db[(postgres)]
    web --> redis[(redis)]
    worker[worker: celery] --> db
    worker --> redis
    beat[beat: celery cron] --> redis
    prometheus[prometheus] -->|scrape /metrics| web
    grafana[grafana] --> prometheus
```

## Why each choice — and what was rejected

| Decision            | Chosen                    | Why                                                        | Rejected & why not                                                                 |
|---------------------|---------------------------|------------------------------------------------------------|------------------------------------------------------------------------------------|
| API framework       | Django + DRF              | Batteries-included: ORM, auth, admin, migrations, mature DRF | FastAPI (would hand-roll ORM/admin/migrations); Flask (too much assembly)           |
| Task queue          | Celery + Redis            | De-facto standard, cron via beat, retries, huge ecosystem   | RQ/Dramatiq (lighter but fewer features); OS cron (no retries/visibility)           |
| OLTP database       | PostgreSQL                | JSONB, window functions, reliability, industry default      | MySQL (weaker JSON/analytics); MongoDB (relational modeling here is a better fit)   |
| Analytics/medallion | DuckDB + Parquet          | Lakehouse patterns locally, zero cloud cost, blazing OLAP   | Spark (huge for portfolio scale); Snowflake/BigQuery (needs cloud + spend)          |
| Architecture        | Modular monolith          | Clean boundaries, one deploy, easy local dev + demo         | Microservices (network, infra, and observability overhead unjustified at this size)|
| Auth                | JWT (SimpleJWT) + RBAC    | Stateless, standard for SPA/API, simple to reason about     | Session cookies (worse for SPA/mobile); OAuth server (overkill for internal tool)   |
| Observability       | Prometheus + Grafana + JSON logs + OTel | Industry-standard metrics/dashboards/tracing  | Cloud-only APM (cost + vendor lock-in for a local-first project)                    |
| Docs                | drf-spectacular (OpenAPI) | Auto-generated, always in sync, Swagger UI                  | Hand-written docs (drift out of date immediately)                                   |

## Cross-cutting concerns

- **Security:** JWT + RBAC + workspace isolation; Fernet-encrypted credentials; audit logs; rate
  limiting; PII masking; least privilege. (v0.7)
- **Reliability:** idempotent loads, retries with backoff, blocking validation, dead-letter records,
  health checks. (v0.2, v0.3)
- **Scalability path:** stateless API behind more gunicorn workers; add Celery workers horizontally;
  partition Parquet; batch tuning; connection pooling. Documented, not all built at portfolio scale.
- **Data quality:** validation engine + scorecards with historical trend. (v0.3)
- **Governance:** metadata catalog + table/column lineage + schema history. (v0.4)

'@
Set-Content -Path "docs/03-architecture.md" -Value $content -NoNewline -Encoding UTF8

New-Item -ItemType Directory -Force -Path "docs" | Out-Null
$content = @'
# Module Specifications

Each module is a Django app under `apps/`. Layering: `models` → `services` → `serializers`/`views`.
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

## etl  (framework-agnostic — no Django imports)
Pure functions: `extract(source_type, config)`, `validate(df, spec)`, `transform(df, spec)`,
`load` helpers, and `engine.run(...)` which orchestrates extract→validate→transform→load, returns
metrics + step logs, and raises on blocking validation failure. Receives a `loader` callable so it
never touches the ORM.

## pipelines
`Pipeline` (source FK, JSON config = validation/transform/target specs, schedule, is_active) and
`PipelineRun` (status, started/finished, metrics JSON, logs, error). `services.execute_pipeline`
bridges models → the etl engine and records the run. `tasks.run_pipeline_task` runs it via Celery
(retries + backoff). `loaders.py` maps engine output to warehouse models idempotently. API: pipeline
CRUD + `run` action + read-only run history.

## scheduler
Cron scheduling on django-celery-beat: a schedule per pipeline, manual trigger, retry-failed-job,
and a queue/inflight view. Pause/resume toggles the beat entry.

## validation
Rule library (schema, null, duplicate, type, range, referential integrity, freshness, business
rules), pluggable backend (custom → optionally Great Expectations/Pandera), and a per-run **quality
scorecard** (completeness/consistency/accuracy) persisted with history. Blocking checks fail the run.

## metadata
Dataset registry, schema history/versioning, column metadata, and table/column **lineage**
(source→bronze→silver→gold). Schema-drift detection on ingest. Backs the medallion layers (Parquet +
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

'@
Set-Content -Path "docs/04-modules.md" -Value $content -NoNewline -Encoding UTF8

New-Item -ItemType Directory -Force -Path "docs/adr" | Out-Null
$content = @'
# ADR 0001 — Core technology stack

- **Status:** Accepted
- **Context:** Need a productive, hireable, local-first stack to build a data platform that a single
  developer can run, test, and demo without cloud spend, while showcasing production practices.
- **Decision:** Python 3.12 · Django 5 + DRF · SimpleJWT · Celery + Redis · django-celery-beat ·
  PostgreSQL (SQLite for dev/tests) · pandas · DuckDB + Parquet · drf-spectacular ·
  django-prometheus + Grafana · Docker · GitHub Actions.
- **Consequences:** Batteries-included web layer (ORM/admin/migrations/DRF), a mature async +
  scheduling story, and industry-standard observability. Trade-off: Python throughput is lower than
  JVM/Go, mitigated by pushing heavy work to workers and columnar formats.
- **Alternatives rejected:** FastAPI/Flask (hand-roll ORM/admin/migrations); RQ/OS-cron (fewer
  features than Celery/beat); MySQL/Mongo (weaker JSON/analytics or wrong data model); Spark/cloud
  warehouses (overkill + cost for portfolio scale).

'@
Set-Content -Path "docs/adr/0001-tech-stack.md" -Value $content -NoNewline -Encoding UTF8

New-Item -ItemType Directory -Force -Path "docs/adr" | Out-Null
$content = @'
# ADR 0002 — Modular monolith over microservices

- **Status:** Accepted
- **Context:** The platform has clear bounded contexts (auth, sources, pipelines, validation,
  metadata, monitoring, …). We want clean boundaries without distributed-systems overhead.
- **Decision:** One deployable Django app; each context is its own app under `apps/`; apps interact
  only through public services/serializers, never internal imports; heavy work runs on Celery.
- **Consequences:** Simple local dev and demo, one deploy, transactional integrity, easy refactors —
  while boundaries stay explicit so contexts could be extracted later if ever needed.
- **Alternatives rejected:** Microservices — network hops, per-service infra, distributed tracing,
  and deployment complexity that a single developer at portfolio scale should not take on.

'@
Set-Content -Path "docs/adr/0002-modular-monolith-vs-microservices.md" -Value $content -NoNewline -Encoding UTF8

New-Item -ItemType Directory -Force -Path "docs/adr" | Out-Null
$content = @'
# ADR 0003 — PostgreSQL for OLTP, DuckDB + Parquet for the medallion layers

- **Status:** Accepted
- **Context:** We need reliable transactional storage for platform state (users, sources, pipelines,
  runs) and an analytical layer that demonstrates modern lakehouse patterns without cloud spend.
- **Decision:** PostgreSQL for OLTP (SQLite locally for zero-setup). Bronze/silver/gold layers as
  partitioned Parquet files queried with DuckDB for analytics and lineage demonstration.
- **Consequences:** Clear separation of operational vs analytical concerns; fast local OLAP; genuine
  medallion story; portable and free. Trade-off: not a distributed warehouse — documented as Future
  Scope (Snowflake/BigQuery connectors) rather than built now.
- **Alternatives rejected:** Everything-in-Postgres (no medallion story, weaker OLAP); Spark or a
  cloud warehouse (infrastructure and cost unjustified at this scale).

'@
Set-Content -Path "docs/adr/0003-storage-and-medallion.md" -Value $content -NoNewline -Encoding UTF8

New-Item -ItemType Directory -Force -Path "config" | Out-Null
New-Item -ItemType File -Force -Path "config/.gitkeep" | Out-Null
New-Item -ItemType Directory -Force -Path "config/settings" | Out-Null
New-Item -ItemType File -Force -Path "config/settings/.gitkeep" | Out-Null
New-Item -ItemType Directory -Force -Path "scripts" | Out-Null
New-Item -ItemType File -Force -Path "scripts/.gitkeep" | Out-Null
New-Item -ItemType Directory -Force -Path "sample_data" | Out-Null
New-Item -ItemType File -Force -Path "sample_data/.gitkeep" | Out-Null
New-Item -ItemType Directory -Force -Path "apps/metadata" | Out-Null
New-Item -ItemType File -Force -Path "apps/metadata/.gitkeep" | Out-Null
New-Item -ItemType Directory -Force -Path "apps/warehouse" | Out-Null
New-Item -ItemType File -Force -Path "apps/warehouse/.gitkeep" | Out-Null
New-Item -ItemType Directory -Force -Path "apps/monitoring" | Out-Null
New-Item -ItemType File -Force -Path "apps/monitoring/.gitkeep" | Out-Null
New-Item -ItemType Directory -Force -Path "apps/pipelines" | Out-Null
New-Item -ItemType File -Force -Path "apps/pipelines/.gitkeep" | Out-Null
New-Item -ItemType Directory -Force -Path "apps/scheduler" | Out-Null
New-Item -ItemType File -Force -Path "apps/scheduler/.gitkeep" | Out-Null
New-Item -ItemType Directory -Force -Path "apps/common" | Out-Null
New-Item -ItemType File -Force -Path "apps/common/.gitkeep" | Out-Null
New-Item -ItemType Directory -Force -Path "apps/datasources" | Out-Null
New-Item -ItemType File -Force -Path "apps/datasources/.gitkeep" | Out-Null
New-Item -ItemType Directory -Force -Path "apps/datasources/connectors" | Out-Null
New-Item -ItemType File -Force -Path "apps/datasources/connectors/.gitkeep" | Out-Null
New-Item -ItemType Directory -Force -Path "apps/notifications" | Out-Null
New-Item -ItemType File -Force -Path "apps/notifications/.gitkeep" | Out-Null
New-Item -ItemType Directory -Force -Path "apps/etl" | Out-Null
New-Item -ItemType File -Force -Path "apps/etl/.gitkeep" | Out-Null
New-Item -ItemType Directory -Force -Path "apps/validation" | Out-Null
New-Item -ItemType File -Force -Path "apps/validation/.gitkeep" | Out-Null
New-Item -ItemType Directory -Force -Path "apps/accounts" | Out-Null
New-Item -ItemType File -Force -Path "apps/accounts/.gitkeep" | Out-Null

Write-Host 'Done. 22 files created.' -ForegroundColor Green