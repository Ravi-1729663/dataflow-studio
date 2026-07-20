# Showcasing this project (portfolio + interviews)

This is the "how do I talk about it" companion to the rest of `docs/`. Everything here is grounded
in things that actually happened while building this, not generic advice — use it as a script, not
a suggestion to go improvise.

## The 30-second pitch

> "I built a multi-tenant data platform — ingestion from files, databases, REST APIs, and S3;
> automated data cleansing and statistical anomaly detection; multi-tenant security with encrypted
> credentials and audit logging; and a React dashboard — all on Django, Celery, and Postgres. The
> part I'm most proud of isn't any one feature, it's that I proved it holds up: a load test with
> zero failures, and a chaos test where I hard-kill a live worker mid-pipeline-run and show it
> recovers automatically."

Adjust the last sentence depending on what the interviewer seems to care about — swap "chaos test"
for "multi-tenant security model" or "anomaly detection" if they're clearly more data-quality
focused than infra-focused.

## Why this exists (the framing, not just the feature list)

Don't lead with "I built an ETL tool." Lead with the problem: **companies pull data from
heterogeneous sources into a warehouse, and doing that reliably is actually five different hard
problems** — ingestion, data quality, transformation, orchestration, and governance/security —
that in industry are usually five different vendors (Fivetran/Airbyte, dbt, Great
Expectations/Monte Carlo, Airflow, and a hand-rolled security layer). This project is one coherent
system that implements a working, intentionally-smaller-scale version of all five, so you can
point at any layer and explain both what it does and what the "real" industrial-strength version
of that layer looks like.

That framing does two things: it shows you understand the *ecosystem*, not just your own code, and
it pre-empts the "isn't this just reinventing X?" question (see below) by making clear that was
never the goal.

## Deep-dive talking points, by area

Pick 2-3 of these to go deep on based on the role — don't try to cover all of them in one answer.

**Data cleansing + validation (`apps/etl/clean.py`, `validate.py`)**
The two are deliberately separate steps that run in a specific order: clean *before* validate, not
after. Why: if you clean first, whatever's left gets validated, so a fixable issue (a stray space,
a missing default) doesn't block the whole batch — but the scorecard still reflects genuine,
un-fixable quality problems. If you validated first, you'd either lose visibility into how much
cleaning actually helped, or you'd be scoring pre-repair data forever. This is a real design
decision with a real trade-off, not a random ordering — be ready to explain *why*, not just *what*.

**Statistical anomaly detection (`apps/metadata/services.py`)**
Implements Welford's *parallel* algorithm — merging each run's batch statistics into a running
(count, mean, M2) aggregate — instead of storing every historical value and recomputing. That's a
genuine numerical-stability/space-complexity decision (O(columns) instead of O(rows × runs)), and
it's the same idea Monte Carlo and Bigeye build commercial products on. Good follow-up if asked "why
not just use a library": there wasn't a lightweight one for this exact online-aggregate pattern,
and implementing it forced understanding the math instead of treating it as a black box.

**Multi-tenancy and security (`apps/workspaces/`, `apps/audit/`, `apps/common/fields.py`)**
Workspace isolation is enforced at the *queryset* level in every view — `Model.objects.filter(...
workspace__memberships__user=request.user)` — not just hidden in the UI. Credentials are
Fernet-encrypted via a custom Django field, transparent to callers (still just a dict in Python;
the DB column is opaque ciphertext). Good story here: **a real vulnerability was found and fixed
during this build** — see the STAR story below.

**Chaos engineering (`scripts/chaos_test.py`)**
This is the strongest, most differentiated story in the whole project — see the STAR story below.
Know the mechanism cold: `task_acks_late` + `task_reject_on_worker_lost` + a bounded
`visibility_timeout` on the Redis broker transport. Be ready to explain *why* a killed worker's
task isn't just lost (the broker never removes the message until a worker acks it) and what the
actual failure window looks like if you get the visibility timeout wrong (too short: risk of
duplicate execution on a slow-but-alive worker; too long: slow recovery from a real crash).

**Deployment reality (`render.yaml`, `docs/05-deployment.md`)**
Be upfront about this one rather than hoping it doesn't come up: the free-tier live deployment runs
in a *different* mode (synchronous/eager Celery, no separate worker) than the "real" architecture
(docker-compose, async workers) because Render's free tier doesn't offer background workers. This
is a good "engineering judgment under real constraints" story on its own — see below.

## STAR stories (things that actually happened)

**1. Found and fixed a real security vulnerability (least-privilege review)**

- **Situation:** Building the v0.7 multi-tenancy milestone, doing a deliberate least-privilege
  pass across every serializer.
- **Task:** Verify workspace isolation actually held everywhere, not just in the obvious list
  endpoints.
- **Action:** Found that `PipelineSerializer`'s `source` field used DRF's default
  `PrimaryKeyRelatedField` queryset — unrestricted, meaning a user could set `source` to another
  workspace's DataSource UUID and have it validate successfully, since the *list* endpoint being
  scoped didn't stop a direct-by-ID reference. Fixed by overriding `__init__` to scope that
  field's queryset to the requester's own workspaces.
- **Result:** Closed a cross-tenant data-access bug that had existed since the very first
  milestone, before it ever reached a real deployment. Talking point: security bugs often aren't
  in the obvious place (the endpoint that lists things) — they're in the incidental places (a
  related field on a different serializer) that don't get the same scrutiny by default.

**2. Debugged a subtle distributed-systems timing bug (the chaos test)**

- **Situation:** Building the chaos test — kill a Celery worker mid-run, bring up a replacement,
  expect the run to recover via Redis's unacked-message redelivery.
- **Task:** Make that recovery actually observable and reliable in an automated test, not just
  "usually works."
- **Action:** First attempt timed out — the run never recovered within a 90-second window, even
  though the mechanism (`task_acks_late`, `visibility_timeout`) was configured correctly.
  Investigated by inspecting Redis's `unacked`/`unacked_index` keys directly, and discovered
  empirically that Kombu's Redis transport only re-scans for expired unacked messages *once*, at
  connection time — not on a recurring timer. A replacement worker that reconnects *before* the
  visibility window fully elapses won't pick the message up at all until something else triggers
  another scan.
- **Result:** Fixed by having the test wait out the full visibility timeout before starting the
  replacement worker. Documented the finding in `docs/06-resilience.md` since it's a real,
  non-obvious operational gotcha for anyone running Celery+Redis in production, not just an
  artifact of the test. Talking point: this is a good answer to "tell me about a bug you had to
  really dig into" — it required reading library internals, not just documentation.

**3. Made a pragmatic call under a real platform constraint (Render free tier)**

- **Situation:** Deployed the app to Render's free tier; the Blueprint failed because
  "Background Worker" services aren't available on that plan.
- **Task:** Get a genuinely free, live deployment working without misrepresenting what it does.
- **Action:** Considered faking a worker as a Web Service with a health-check hack (common
  workaround, but fragile and dishonest about what's actually running), versus just running in the
  same synchronous/eager mode the project already uses for local dev and its entire test suite.
  Chose the latter, verified it end-to-end against production settings before relying on it, and
  documented the trade-off explicitly (cron-scheduled pipelines don't fire on the free tier;
  everything else does) rather than glossing over it.
- **Result:** A live, honest, zero-cost deployment, plus a clear written trail of *why* it's
  architected differently from the "real" version — which is itself a better interview story than
  a deployment that just quietly works.

## Questions you should expect — and how to answer them honestly

**"Why not just use Airflow / dbt / Fivetran instead of building this?"**
Because the point wasn't to replace them — it's to demonstrate understanding of the problems those
tools solve, end to end, in a system small enough to hold in your head and explain completely. In
a real job you'd absolutely reach for the mature tool. This project is the "could you have built
the 80% version yourself" proof, not a claim that you shouldn't use the real thing.

**"Isn't this over-engineered for a portfolio project?"**
Push back gently: every piece here maps to a real production concern (multi-tenancy because SaaS
data platforms need it, chaos testing because "have you tested failure recovery" is a real
interview question, load testing because "does it scale" always comes up). The scope is wide
*and* each piece is honestly shallow compared to a specialized tool — that trade-off was
deliberate, not accidental (see `docs/03-architecture.md`'s comparison table).

**"What would you do differently if you started over / had more time?"**
Have a real answer, not a deflection. Honest ones from this build: the cleansing step doesn't do
fuzzy deduplication or real statistical imputation (only exact-duplicate and default-value
filling) — a production version would need that. The DAG orchestration is a single linear
pipeline, not a real dependency graph like Airflow — cross-pipeline dependencies aren't modeled.
The metadata catalog is functional but shallow next to something like DataHub (no glossary, no
usage analytics).

**"How would this scale to real production data volumes?"**
Talk through the actual scaling path already written down in `docs/03-architecture.md`: more
gunicorn workers behind a real load balancer, horizontally scaled Celery workers, Parquet
partitioning already in place (Hive-style, by date) as the starting point for larger medallion
volumes, connection pooling. Be honest that none of this has been tested at real scale — the load
test proves it holds up at a modest concurrent-user count, not at data-warehouse scale.

**"Walk me through what happens when I click 'Run' on a pipeline."**
Know this cold, it's the core loop: API validates the request and enqueues `run_pipeline_task` →
(worker or same-process in eager mode) the ETL engine extracts via the connector → clean → validate
(blocking rules can stop here) → transform → load (idempotent upsert) → metadata/lineage/schema
drift/anomaly detection recorded → notification sent → Prometheus counters incremented → response
returned. Being able to narrate this without looking anything up is worth more than any single
deep-dive.

## Presenting it — the checklist

- **Pin the repo** on your GitHub profile; set the repo's "About" description to the one-line
  pitch at the top of `README.md`, and add topics (`django`, `react`, `celery`, `data-engineering`,
  `etl`, `postgresql`, `docker`) so it's discoverable and signals the right keywords at a glance.
- **Put the live URL front and center** in the README (top, not buried) once deployed — a
  clickable demo beats a wall of text every time.
- **Screenshots + a short demo GIF** matter more than more prose. A 30-60 second loop (create a
  data source → build a pipeline with a cleansing rule → run it → watch the dashboard/anomalies
  panel update) is the single highest-leverage thing left to add. Record it with any free
  screen-recorder, convert to GIF (ScreenToGif, or ffmpeg), drop it right under the pitch in
  `README.md`.
- **Resume:** link the live demo, not just the GitHub repo, if both exist — recruiters click demos
  more than they read code.
- **LinkedIn/portfolio post**, if you write one: lead with the chaos test or the security-fix
  story (STAR stories 1-2 above), not a feature list — a specific, concrete "here's a bug I found
  and how I fixed it" story gets more engagement and is more memorable than "I built a data
  platform with 15 features."
