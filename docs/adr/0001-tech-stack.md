# ADR 0001 â€” Core technology stack

- **Status:** Accepted
- **Context:** Need a productive, hireable, local-first stack to build a data platform that a single
  developer can run, test, and demo without cloud spend, while showcasing production practices.
- **Decision:** Python 3.12 Â· Django 5 + DRF Â· SimpleJWT Â· Celery + Redis Â· django-celery-beat Â·
  PostgreSQL (SQLite for dev/tests) Â· pandas Â· DuckDB + Parquet Â· drf-spectacular Â·
  django-prometheus + Grafana Â· Docker Â· GitHub Actions.
- **Consequences:** Batteries-included web layer (ORM/admin/migrations/DRF), a mature async +
  scheduling story, and industry-standard observability. Trade-off: Python throughput is lower than
  JVM/Go, mitigated by pushing heavy work to workers and columnar formats.
- **Alternatives rejected:** FastAPI/Flask (hand-roll ORM/admin/migrations); RQ/OS-cron (fewer
  features than Celery/beat); MySQL/Mongo (weaker JSON/analytics or wrong data model); Spark/cloud
  warehouses (overkill + cost for portfolio scale).
