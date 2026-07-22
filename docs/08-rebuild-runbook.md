# Rebuild runbook (v0.9)

If this repo, the Render project, and the Vercel project all vanished tomorrow, this document is
what you'd hand someone (or your future self) to bring DataFlow Studio back from nothing. It does
not re-explain *what* each module does — `docs/04-modules.md` is the source of truth for that and
is kept in sync per `CLAUDE.md`'s Definition of Done. This is the connective tissue: accounts,
secrets, order of operations, and how to prove each stage actually works before moving to the next.

## 1. What this system is, in one paragraph

DataFlow Studio is a Django 5 + DRF modular monolith (one app per bounded context under `apps/`)
with a framework-agnostic ETL engine (`apps/etl/` — extract → incremental filter → clean →
validate → transform → load, zero Django imports), Celery/Redis for async pipeline execution,
django-celery-beat for cron scheduling, PostgreSQL (or SQLite for zero-setup local dev/tests) as
the OLTP store, and a React/Vite SPA frontend talking to it over a JWT-authenticated REST API. See
`docs/03-architecture.md` for the diagram and rationale.

## 2. Accounts you need before touching code

| Account | Free tier used for | Notes |
|---|---|---|
| GitHub | Source of truth; Render/Vercel deploy from here, not a local checkout | Repo must be pushed — neither platform reads your local filesystem |
| Render | Backend web service + managed Postgres | Free web service spins down after 15 min idle; free Postgres expires after 30 days unless upgraded |
| Vercel | Frontend static build | Root Directory must be set to `frontend/` — it's a subfolder |
| (Optional) A real AWS S3 bucket | Exercising the S3 connector against a real endpoint from the live deployment | Not required — MinIO in docker-compose covers this locally; Render can't reach `localhost:9000` |

No other third-party accounts. Email notifications use Django's console backend by default (logs
only, no real account needed) — see `apps/notifications/`.

## 3. Every environment variable, what breaks without it

| Variable | Where it's set | If missing/wrong |
|---|---|---|
| `DJANGO_SECRET_KEY` | `.env` (local), Render (`generateValue: true`) | Django refuses to start |
| `DJANGO_SETTINGS_MODULE` | `.env` / Render / docker-compose | Wrong settings module (e.g. local settings in prod) → `DEBUG=True` leaking stack traces, or SQLite instead of Postgres |
| `DJANGO_ALLOWED_HOSTS` | `.env` / Render | `DisallowedHost` 400s on every request |
| `FERNET_KEY` | `.env` (generate, don't leave blank), Render (`sync: false`, generate your own) | `DataSource.config` can't encrypt/decrypt — **never reuse the local dev fallback derived from `SECRET_KEY`** in a real deployment |
| `USE_POSTGRES` | `.env` / Render / docker-compose | `0`/unset → SQLite (fine for local, wrong for anything shared) |
| `POSTGRES_DB/USER/PASSWORD/HOST/PORT` | `.env` (docker-compose), Render (`fromDatabase`, auto-wired) | Can't connect to Postgres |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | `.env` (docker-compose only) | Not used on Render (see next row) — needed for the real worker topology |
| `CELERY_TASK_ALWAYS_EAGER` | `.env` (`1` local/tests), docker-compose (`0` — real worker), Render (`1` — no worker service on free tier) | `0` with no worker running = pipelines queue forever and never execute |
| `CORS_ALLOWED_ORIGINS` | `.env` / Render (`sync: false`) | Browser blocks every frontend request with a CORS error (looks like "Network Error" in the SPA) |
| `LOG_LEVEL` | `.env` | Cosmetic only |
| `VITE_API_BASE_URL` | `frontend/.env` (local), Vercel project env var | Frontend calls `localhost:8000` in production → every request fails |

Full defaults live in `.env.example` (backend) and `frontend/.env.example`.

## 4. Rebuild order (local first, always — never debug live first)

1. **Clone + backend deps**: `python -m venv .venv`, activate it, `pip install -r requirements-dev.txt`.
2. **Configure**: `cp .env.example .env`, fill in a real `FERNET_KEY` (command is in the file).
3. **Migrate + seed**: `make migrate && make seed`. Verify: `make seed` prints a completed
   pipeline run with no traceback. This alone proves models, migrations, the ETL engine, and the
   warehouse load path all work end to end on SQLite.
4. **Backend test suite**: `make test` — as of this writing, 144 tests, all passing, no DB
   required for the ETL unit tests and `@pytest.mark.django_db` for the rest. `make lint` (ruff)
   and `black --check .` must also be clean. **Do not skip this before touching deployment** — it
   catches almost everything before it costs you a redeploy cycle.
5. **Frontend deps + checks**: `cd frontend && npm install`, `npm run lint`, `npm run build`
   (runs `tsc -b` first — a type error fails the build, which is the point).
6. **Full local stack**: `docker compose up -d --build` — brings up web, worker, beat, Postgres,
   Redis, MinIO, Prometheus, Grafana. This is the *only* environment that exercises the real async
   worker and cron scheduling; verify with `docker compose logs worker --tail=50` after running a
   pipeline — you should see the task picked up and completed, not just enqueued.
7. **Only once 3-6 are green**, push to GitHub and deploy:
   - Render: New → Blueprint → point at `render.yaml` → fill in the `sync: false` values
     (`FERNET_KEY`, `CORS_ALLOWED_ORIGINS`) → Apply. See `docs/05-deployment.md` Option A for the
     full walkthrough including free-tier caveats.
   - Vercel: import repo, Root Directory = `frontend`, env var `VITE_API_BASE_URL` = the Render
     web service URL. `frontend/vercel.json` handles SPA routing.
   - Go back to Render, set `CORS_ALLOWED_ORIGINS` to the Vercel URL, redeploy.
8. **Prove the live deployment, not just the build**: register a user through the live frontend,
   create a data source, run a pipeline, check the dashboard — the exact walkthrough is in
   `docs/05-deployment.md`'s "Testing the live demo" section. A green build is not the same claim
   as a working deployment; only step 8 proves the latter.

## 5. Known failure modes already hit (troubleshooting table)

These are real incidents from building this project, not hypotheticals — kept here so the same
hour of debugging doesn't happen twice, and because they're also solid interview material (see
`docs/07-portfolio-and-interviews.md`).

| Symptom | Root cause | Fix |
|---|---|---|
| `seed_demo` raises `KeyError: 'path'` | A pre-encryption row's plaintext JSON got type-cast (not re-encrypted) during the JSONField→EncryptedJSONField migration; `EncryptedJSONField.from_db_value` silently returns `{}` on `InvalidToken` | Delete the stale row, re-seed. `apps/common/fields.py` now logs a warning on this path instead of failing silently |
| Frontend "Network Error" on login | Vite fell back to port 5174 (another process held 5173); backend's `CORS_ALLOWED_ORIGINS` only allowlists 5173 | Find and kill the process holding 5173, or add the actual port to `CORS_ALLOWED_ORIGINS` |
| A newly-added `sample_data/*.csv` isn't visible inside a running container | Docker images are built via `COPY . .` — filesystem is baked at build time, not live-mounted | `docker compose build web worker && docker compose up -d` after adding files |
| Render Blueprint sync fails: "service type is not available for this plan" | Free tier has no Background Worker service type | `render.yaml` uses a single Web Service with `CELERY_TASK_ALWAYS_EAGER=1` instead — see the comment block at the top of that file |
| Data source "Test connection" returns a generic "Request failed with status code 400" instead of the real reason | `test_connection`'s view returns `{"error": "..."}` directly (bypassing the common exception handler's `{error: {message, details}}` envelope); `apiErrorMessage` only knew that one shape | `apiErrorMessage` (`frontend/src/lib/api.ts`) now also handles a plain string `error` field |
| Render backend returns HTTP 503 with `Retry-After` on first hit | Free-tier cold start after 15 min idle — expected, not a bug | Hit it again after ~30-60s; if it's still 503 after that, check the Render dashboard logs for an actual crash instead of assuming cold start |

## 6. What "done" looks like right now

- Backend: 144 tests green, ruff/black clean.
- Frontend: lint + `tsc -b` + `vite build` clean.
- Local docker-compose: full async architecture verified (worker picks up and completes tasks).
- Render: backend deployed as a single web service + free Postgres, eager Celery mode.
- Vercel: frontend deploy is a pending step — not yet live as of this writing (confirm your own
  Vercel URL and update this line, and the README's live-demo link, once it is).

Treat this last section as a living checklist, not a permanent claim — update it whenever the
actual deployed state changes, since that's the entire point of this document.
