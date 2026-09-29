# NEXUS OS — build state

_Last updated: 2026-09-29 (Phase 0)_

## Current phase

**Phase 0 — Architecture** (in progress → completing). Next: Phase 1 — Foundation.

## Completed

- Improved brief with resolved contradictions and acceptance criteria (`docs/BRIEF.md`)
- Architecture, database, agents, tools, memory/context, security, roadmap docs
- Project location decided: `Projects/nexus-os/` (workspace rule: new work under `Projects/`)

## In progress

- Phase 0 self-review (consistency pass across docs)

## Next

1. Phase 1: pnpm/uv monorepo, FastAPI app factory, settings, SQLite + Alembic `0001`, auth + host/origin checks, EventBus + hash-chained events + SSE, health API, secret store, projects/conversations API, React shell + dashboard, OpenAPI→TS types, Tauri scaffold.

## Known issues / limits of the build environment

- No live provider API keys: adapters will be verified against mock upstreams only.
- Tauri cannot be compiled here (no webkit2gtk/GTK): the desktop shell will be scaffolded and marked **unverified**.
- OS keychain, Windows sandbox limits, and Docker sandbox cannot be exercised here.

## Architecture decisions

See `docs/ARCHITECTURE.md` §12 and `docs/BRIEF.md` §3. Highlights: one Python service with enforced module boundaries; custom provider adapters; structured-step agent protocol; SQLite+Alembic with soft cross-aggregate references; hash-chained event log; taint-aware policy engine; bearer-token local API.

## Testing status

| Area | Status |
|---|---|
| Backend unit/API | not started |
| Frontend | not started |
| E2E | not started |
| Lint / typecheck / build | not started |
