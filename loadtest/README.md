# Load testing (v0.9)

`locustfile.py` drives the same calls the React SPA makes (see `frontend/src/lib/resources.ts`):
each simulated user registers its own account (so v0.7's per-user rate limiting doesn't make every
virtual user share one throttle bucket), creates a workspace, registers a data source, builds a
pipeline, then loops over listing data sources/pipelines, checking the dashboard and scorecards,
and occasionally triggering a run.

## Running it

Load test against the **full docker-compose stack** (Postgres + Redis + a real Celery worker,
`CELERY_TASK_ALWAYS_EAGER=0`), not `manage.py runserver` — the dev server is single-threaded and
would just measure its own concurrency ceiling instead of the app's.

```bash
docker compose up -d --build db redis web worker

# Register/login are throttled to 10/min per IP by default (v0.7) — since every virtual user
# onboards from the same test-runner IP, raise it for the duration of the run so the test
# measures the data-plane endpoints, not the (separately pytest-covered) auth throttle:
echo "THROTTLE_RATE_AUTH=1000/min" >> .env
docker compose up -d --force-recreate web worker

.venv/Scripts/python -m locust -f loadtest/locustfile.py --host=http://localhost:8000 \
  --users 25 --spawn-rate 5 --run-time 90s --headless \
  --html loadtest/reports/report.html --csv loadtest/reports/results

# revert the throttle override afterwards
git checkout .env   # or manually remove the THROTTLE_RATE_AUTH line
docker compose up -d --force-recreate web worker
```

Open `loadtest/reports/report.html` for the full charts, or `results_stats.csv` for the raw
numbers.

## Latest result (25 users, 5/s spawn rate, 90s, committed under `reports/`)

| Endpoint                                     | Requests | Failures | Median | p95   | Max   |
|-----------------------------------------------|---------:|---------:|-------:|------:|------:|
| `POST /auth/register/`                        |       25 |        0 |  140ms | 280ms | 282ms |
| `POST /auth/token/`                            |       25 |        0 |  250ms | 280ms | 278ms |
| `POST /workspaces/`                            |       25 |        0 |   35ms | 140ms | 146ms |
| `POST /datasources/`                           |       25 |        0 |   27ms |  56ms |  69ms |
| `GET /datasources/?workspace=[id]`             |      321 |        0 |   17ms |  36ms | 110ms |
| `POST /pipelines/`                             |       25 |        0 |   31ms |  45ms |  57ms |
| `GET /pipelines/?workspace=[id]`               |      354 |        0 |   18ms |  36ms |  77ms |
| `POST /pipelines/[id]/run/`                    |       55 |        0 |   26ms |  76ms | 140ms |
| `GET /validation/scorecards/?run__pipeline=`  |      145 |        0 |   17ms |  37ms | 140ms |
| `GET /monitoring/dashboard/`                   |      203 |        0 |   19ms |  35ms |  49ms |
| **Aggregate**                                  | **1203** |    **0** | **19ms** | **88ms** | **282ms** |

**Zero failures across 1203 requests.** Register/login are the slowest endpoints (~150-280ms) —
expected, since Django's password hasher (PBKDF2) is deliberately slow; every other endpoint stays
under 50ms at the median even with 25 concurrent users hammering it. `POST /pipelines/[id]/run/`
executes the pipeline asynchronously in the real Celery worker (not in-request), so its ~26-140ms
is just the enqueue + `PipelineRun` row creation, not the ETL run itself.

**Known limits at this scale:** the free-tier profile this targets (SQLite/single-gunicorn-worker
local dev) is not what was load tested here — this run targeted the docker-compose stack
(Postgres + a single Celery worker process). Scaling further would mean more gunicorn workers
behind a real reverse proxy and horizontally scaling the Celery worker, both already called out as
the scaling path in `docs/03-architecture.md`.
