# Scope

## In scope (through v1.0)
Auth + RBAC + workspaces + admin Â· file/Postgres/REST sources Â· ETL engine (batch + incremental,
SCD2) Â· validation engine + quality scorecards Â· pipeline engine + cron scheduler + retries Â·
metadata catalog + lineage Â· monitoring + logging + alerting + notifications Â· versioned documented
REST API + optional React dashboard Â· Docker + CI/CD + tests + encrypted secrets.

## Out of scope (v1.0)
Real-time streaming (Kafka/Flink) Â· cloud-managed warehouses Â· ML training / feature store Â· native
mobile app Â· multi-region high availability.

## Future scope (roadmap)
Streaming + log-based CDC Â· Snowflake/BigQuery connectors Â· ML feature store + model serving Â·
mobile companion Â· multi-region active-active Â· cost-governance dashboard Â· auto column-level lineage.

## MVP vs Enterprise
- **MVP (v0.1â€“v0.3):** auth, one source type, pipeline execution + scheduling, validation +
  scorecards. A working, demoable platform.
- **Enterprise (v0.4â€“v1.0):** lineage + medallion, full observability + tracing, multiple connectors
  + CDC + SCD2, multi-tenancy + security hardening, dashboard, CI/CD + deploy + resilience tests.

Per-version scope lives in `PROJECT_PLAN.md` Â§4.
