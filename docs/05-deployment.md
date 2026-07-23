# Deployment (v0.9)

Three ways to run this: **PythonAnywhere** (the current live demo — free, always-on, no card,
no expiring database), **Render** (documented as an alternative — free Blueprint-as-code, but its
free Postgres expires after 30 days, which is exactly what took the earlier live demo down), or
**docker-compose** (the full architecture — web, worker, beat, Postgres, Redis, Prometheus,
Grafana) for local dev or any VM that can run Docker.

**None of these three are the same topology**, and that's deliberate — see each option's caveats
before assuming a `worker` process or a Postgres database is running somewhere it isn't.

## Option A — PythonAnywhere (free tier, current live deployment)

Chosen after Render's free Postgres expired mid-demo (Render's free-tier database plan is
time-limited, not indefinite — see Option B). PythonAnywhere's free ("Beginner") tier has a
different, and for a portfolio demo, more favorable trade-off: **no credit card ever, the web app
never sleeps (no 15-minute cold start), and there's no database to expire** — because the trade-off
is running on SQLite instead of Postgres for the public demo, and outbound network calls from the
app are restricted to a whitelist of external hosts.

**What that trade-off actually costs**, concretely:
- ✅ Everything triggered by a click still works exactly as documented: register, create a `FILE`
  data source, run a pipeline, cleansing, validation, statistical anomaly detection, lineage,
  scorecards, dashboards, Swagger docs.
- ❌ No live demo of the S3 connector or a real external `REST_API` source — PythonAnywhere's free
  tier only allows outbound requests to a whitelisted set of hosts, which arbitrary S3
  endpoints/APIs aren't on. (This is not a new loss — the Render deployment already couldn't reach
  MinIO, which is `localhost`-only, either. Both connectors are verified via docker-compose
  instead — see `docs/04-modules.md`.)
- ❌ No cron-scheduled pipelines — same reason as Render: `django-celery-beat` needs an actual
  running worker process to tick, and `CELERY_TASK_ALWAYS_EAGER=1` (the same zero-setup mode this
  project already uses for local dev and the entire pytest suite) runs tasks synchronously
  in-request instead.
- The public demo's data lives in a SQLite file on PythonAnywhere's persistent disk — durable
  across reloads (unlike Render's ephemeral container filesystem), but not the real Postgres
  the stack table in `CLAUDE.md` specifies. That's a demo-hosting concession, not a change to the
  actual architecture — local dev, tests, and docker-compose all still use Postgres/SQLite exactly
  as designed.

### Steps

No code changes needed for this — every setting below is already environment-driven
(`config/settings/base.py`), so switching hosts is a config/deploy exercise, not a diff.

1. Sign up free at [pythonanywhere.com](https://www.pythonanywhere.com) — no card required.
2. Open a **Bash console** (Dashboard → Consoles → New console → Bash).
3. Clone the repo and set up a virtualenv:
   ```bash
   git clone https://github.com/Ravi-1729663/dataflow-studio.git
   cd dataflow-studio
   mkvirtualenv --python=/usr/bin/python3.12 dataflow-venv
   pip install -r requirements.txt
   ```
4. Create a `.env` file in the project root (loaded automatically via `load_dotenv()` in
   `config/settings/base.py` — nothing extra to wire up):
   ```
   DJANGO_SECRET_KEY=<generate one: python -c "import secrets; print(secrets.token_urlsafe(50))">
   DJANGO_DEBUG=0
   DJANGO_ALLOWED_HOSTS=.pythonanywhere.com
   FERNET_KEY=<generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
   CORS_ALLOWED_ORIGINS=<your Vercel/frontend URL, filled in after the frontend is deployed>
   ```
   Leave `USE_POSTGRES` unset (defaults to `0` → SQLite).
5. Migrate, collect static assets (served by WhiteNoise — no separate PythonAnywhere static
   files mapping needed), and seed demo data:
   ```bash
   python manage.py migrate
   python manage.py collectstatic --noinput
   python manage.py seed_demo   # optional — creates a demo user/datasource/pipeline
   ```
6. **Web tab** → **Add a new web app** → **Manual configuration** → Python 3.12. Set:
   - Source code / working directory: `/home/<username>/dataflow-studio`
   - Virtualenv: `/home/<username>/.virtualenvs/dataflow-venv`
   - WSGI configuration file — replace its contents with:
     ```python
     import os
     import sys

     path = "/home/<username>/dataflow-studio"
     if path not in sys.path:
         sys.path.insert(0, path)

     os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.production"

     from config.wsgi import application
     ```
     (`DJANGO_SETTINGS_MODULE` has to be set here, before Django imports its settings — the `.env`
     file from step 4 is loaded *inside* `base.py`, which is too late to pick the settings module
     itself.)
7. Click **Reload** on the Web tab. Your API is live at `https://<username>.pythonanywhere.com`.
8. **Frontend**: deploy `frontend/` to Vercel (see Option A of the old flow, unchanged) — set
   `VITE_API_BASE_URL` to `https://<username>.pythonanywhere.com`. Then come back to step 4's
   `.env` and set `CORS_ALLOWED_ORIGINS` to the Vercel URL; **Reload** the web app again.

### Testing the live demo

Same walkthrough as documented for Render below, minus the S3 connector step — register, create a
`FILE` data source pointing at a bundled `sample_data/*.csv`, run a pipeline, check cleansing
stats and anomaly detection on the dashboard.

## Option B — Render (free tier, documented alternative)

`render.yaml` is a [Render Blueprint](https://render.com/docs/blueprint-spec): infrastructure as
code, a single Web Service + managed Postgres. Kept in the repo as a working, documented
alternative and IaC example — **the free managed Postgres on this plan expires after 30 days**,
which is what took the original live demo down after it had been up and working; that's the
reason Option A (PythonAnywhere) is the current live deployment instead. If you want Postgres in a
live demo and are fine renewing/recreating the database periodically (or upgrading the Postgres
plan), this is still a perfectly valid path.

**Why no worker/beat on Render:** Render's free tier only offers Web Services, Static Sites, a
free Postgres, and a free Redis — **Background Worker is a paid-plan-only service type.** Rather
than pay for that just to run a demo, `render.yaml` sets `CELERY_TASK_ALWAYS_EAGER=1`.

### Steps

1. Push this repo to GitHub (Render deploys from a Git remote, not a local checkout).
2. In the Render dashboard: **New +** → **Blueprint** → connect the repo. Render reads
   `render.yaml` and proposes two resources: `dataflow-studio-web`, `dataflow-studio-db`.
3. Before clicking **Apply**, Render prompts for the `sync: false` values it can't template:
   - `FERNET_KEY` — generate with
     `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
     **Do not reuse the local dev fallback** (`config/settings/base.py` derives one from
     `SECRET_KEY` when unset — fine for zero-setup local dev, not for a real deployment).
   - `CORS_ALLOWED_ORIGINS` — leave blank for now; fill in once the frontend is deployed.
   - `DJANGO_SECRET_KEY` is auto-generated by Render (`generateValue: true`) — no action needed.
4. Apply. Render builds the Docker image and runs `python manage.py migrate` automatically.
5. **Frontend**: deploy `frontend/` to Vercel or a Render Static Site — set `VITE_API_BASE_URL` to
   the web service's URL, then set `CORS_ALLOWED_ORIGINS` on the backend to the frontend's URL.
6. (Optional) Add `RENDER_DEPLOY_HOOK_URL` as a GitHub repo secret so
   `.github/workflows/ci.yml`'s `deploy` job auto-redeploys on every push to `main`.

**Free-tier caveats**: web service spins down after 15 minutes idle (~30-60s cold start on the
next request); **free Postgres expires after 30 days** (the actual failure mode hit in practice —
check the database's status in the Render dashboard if the API starts 503ing); uploaded CSVs live
on the container's ephemeral disk, wiped on every redeploy/restart.

## Option C — docker-compose (local or any Docker host)

```bash
cp .env.example .env
# fill in FERNET_KEY for anything beyond a quick local look (see .env.example)
docker compose up -d --build
```

Brings up `web` (:8000), `worker`, `beat`, `db` (Postgres :5432), `redis` (:6379), `minio` (:9000,
console :9091, free S3-compatible storage — see the `datasources` section of
`docs/04-modules.md`), `prometheus` (:9090), and `grafana` (:3000, default login admin/admin — set
via `GF_SECURITY_ADMIN_PASSWORD` in `docker-compose.yml`). This is the *real* architecture — a
genuine async worker, not eager mode — and is what `loadtest/README.md` and
`scripts/chaos_test.py` target. If you want to demo cron-scheduled pipelines or the chaos-recovery
behavior, this is the only option that actually exercises them.

## CI/CD

`.github/workflows/ci.yml` runs on every push to `main` and every PR: a `backend` job (ruff, black
--check, pytest with coverage), a `frontend` job (`npm run lint`, `npm run build`), and a `deploy`
job that only fires on `main` and only if the `RENDER_DEPLOY_HOOK_URL` repo secret is set (relevant
only if you're using Option B). Without that secret the job logs a message and exits 0 (green)
rather than failing a fork/PR build that has no deploy access. PythonAnywhere has no deploy-hook
equivalent on the free tier — redeploying there means `git pull` + **Reload** in the Web tab.
