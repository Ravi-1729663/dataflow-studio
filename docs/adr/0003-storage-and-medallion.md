# ADR 0003 â€” PostgreSQL for OLTP, DuckDB + Parquet for the medallion layers

- **Status:** Accepted
- **Context:** We need reliable transactional storage for platform state (users, sources, pipelines,
  runs) and an analytical layer that demonstrates modern lakehouse patterns without cloud spend.
- **Decision:** PostgreSQL for OLTP (SQLite locally for zero-setup). Bronze/silver/gold layers as
  partitioned Parquet files queried with DuckDB for analytics and lineage demonstration.
- **Consequences:** Clear separation of operational vs analytical concerns; fast local OLAP; genuine
  medallion story; portable and free. Trade-off: not a distributed warehouse â€” documented as Future
  Scope (Snowflake/BigQuery connectors) rather than built now.
- **Alternatives rejected:** Everything-in-Postgres (no medallion story, weaker OLAP); Spark or a
  cloud warehouse (infrastructure and cost unjustified at this scale).
