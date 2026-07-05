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
