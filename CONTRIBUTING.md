# Contributing

DataFlow Studio is built one milestone at a time — see [`PROJECT_PLAN.md`](PROJECT_PLAN.md) for
the roadmap and [`CLAUDE.md`](CLAUDE.md) for the architectural rules this codebase follows. Read
both before making a non-trivial change; they're the actual source of truth for "how this project
wants to be built," not just AI-assistant configuration.

## Getting set up

```bash
make install && make migrate && make seed && make run   # backend on :8000
make frontend-install && make frontend-dev               # SPA on :5173 (separate terminal)
```

See [`README.md`](README.md) for the full quickstart and [`docs/05-deployment.md`](docs/05-deployment.md)
for running the full docker-compose stack or deploying to Render.

## Before opening a PR

```bash
make lint && make format && make test        # backend: ruff, black, pytest
make frontend-lint && make frontend-build    # frontend: oxlint, tsc + vite build
```

CI (`.github/workflows/ci.yml`) runs the same checks on every PR — get them green locally first.

## Conventions

- **Branch naming:** `feature/vX.Y-short-slug` for milestone work (matches the tags this repo
  cuts per version), `fix/short-slug` for bug fixes outside a milestone.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/) — `feat:`, `fix:`,
  `test:`, `docs:`, `chore:`, `refactor:`. Keep the subject line under ~70 characters; put the
  "why" in the body, not just the "what."
- **App boundaries (backend):** one Django app per bounded context under `apps/`. Never import
  another app's models/internals directly — go through its `services.py` or serializers. See
  `CLAUDE.md`'s "Golden rules" for the full list (this one and "no Django imports in
  `apps/etl/`" are the two most load-bearing).
- **Tests:** every module ships with tests. Pure logic (`apps/etl/`, validation rules) gets fast
  unit tests with no DB; anything touching models gets a `@pytest.mark.django_db` test. A PR that
  changes behavior without a test to show it is incomplete.
- **Docs:** if you change a module's behavior, add a one-paragraph note to
  [`docs/04-modules.md`](docs/04-modules.md) — that file is the per-module contract, and it drifts
  fast if changes land without it.

## Reporting issues

There's no separate issue tracker for this portfolio project — open a PR with the fix, or describe
the problem in a PR/commit description if you can't fix it yourself. Include: what you expected,
what happened instead, and how to reproduce it (a failing test is the best possible reproduction).
