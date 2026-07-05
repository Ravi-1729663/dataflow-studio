# ADR 0002 â€” Modular monolith over microservices

- **Status:** Accepted
- **Context:** The platform has clear bounded contexts (auth, sources, pipelines, validation,
  metadata, monitoring, â€¦). We want clean boundaries without distributed-systems overhead.
- **Decision:** One deployable Django app; each context is its own app under `apps/`; apps interact
  only through public services/serializers, never internal imports; heavy work runs on Celery.
- **Consequences:** Simple local dev and demo, one deploy, transactional integrity, easy refactors â€”
  while boundaries stay explicit so contexts could be extracted later if ever needed.
- **Alternatives rejected:** Microservices â€” network hops, per-service infra, distributed tracing,
  and deployment complexity that a single developer at portfolio scale should not take on.
