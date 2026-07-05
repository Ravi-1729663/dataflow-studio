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
