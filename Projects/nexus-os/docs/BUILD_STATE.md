# NEXUS OS — build state

_Last updated: 2026-09-29 (end of Phase 1)_

## Current phase

**Phase 1 — Foundation: complete.** Next: Phase 2 — AI providers.

## What works today (verified by automated tests unless noted)

- **API** (FastAPI, Python 3.11): app factory with lifespan migrations; projects, conversations/messages, user settings, notifications, health, events (list, verify, SSE stream with `Last-Event-ID` resume).
- **Security layer:** loopback-only bind (refuses otherwise), bearer token on every call except `/api/health/ping`, Host/Origin allow-lists (DNS-rebinding defence), CORS allow-list, rate limiting, body-size limit, hardening headers, uniform error envelope with no stack traces, secret redaction on events and logs, secret store (OS keychain → private file fallback), repo secret-scan test.
- **Persistence:** SQLite (WAL, FKs on) via SQLAlchemy 2 async; Alembic migration `0001_foundation` verified up/down and against the models (no drift).
- **Audit trail:** every state change emits an event into a per-project SHA-256 hash chain; `/api/events/verify` detects tampering (tested by editing a row).
- **Job queue:** in-process asyncio queue with bounded concurrency, cancel, failure hooks (interface is Redis/Celery-ready).
- **Web app** (React 19, Vite 8, Tailwind 4, Zustand, TanStack Query): app shell with sidebar, top bar, activity panel, bottom panel (events, errors, terminal), status bar; Command Center; Projects (list, create, edit, archive); Settings (general, system health with audit verification); live event stream with resume. Dark-first semantic design tokens (contrast verified) with a light token set. Checked visually at 1440px and 390px: no horizontal overflow, no console errors.
- **Desktop shell:** Rust `nexus-sidecar` crate (spawn API, random port and token, health wait, shutdown, JS-safe init script) **unit-tested (8 tests)**.

## Not verified / not done (honest list)

- **Tauri glue (`apps/desktop/src-tauri`) is written but has never been compiled** — the build container lacks webkit2gtk/GTK. Syntax-checked with `rustfmt` only.
- Production packaging of the Python API for the desktop app (PyInstaller/externalBin) is not done.
- OS keychain path is untested here (the container has no keychain); the file fallback is tested and reported as *degraded*.
- The Command Center objective box is present but disabled until the planner/runtime exist (Phase 5).
- No live provider calls are possible in this environment (no API keys).

## Testing status

| Area | Result |
|---|---|
| Backend (pytest) | 74 passed |
| Lint / format (ruff), strict types (mypy), import contracts | clean |
| Frontend (vitest) | 26 passed (shared 9, web 17) |
| ESLint, `tsc` (all packages) | clean |
| Web production build | ok |
| Rust sidecar (`cargo test`) | 8 passed |
| API-type drift (`scripts/gen_openapi.py --check`) | up to date |
| E2E (Playwright) | ad-hoc screenshots only so far; scripted E2E arrives with the demo objective (Phase 10) |

Run everything: `python scripts/check.py`.

## Architecture decisions made in this phase

- One Python service with import-linter-enforced layers (see `pyproject.toml`); runtime modules may not import FastAPI, and orchestration/agents may not touch the ORM.
- Migrations live inside the package (`app/migrations`) and are independent of app code (custom type rendered as plain `DateTime`).
- Cross-aggregate references are soft (indexed IDs), aggregate-internal ones are enforced foreign keys.
- Event payloads are normalised through canonical JSON before hashing so the chain always matches what the database returns (found by a test with mixed-type keys).
- TypeScript pinned to 5.9 because `openapi-typescript` and `typescript-eslint` need the JS compiler API that TS 7's native port does not expose.
- API types are generated from OpenAPI with `--default-non-nullable false` so request bodies keep optional defaults.
- Dev auth: the Vite proxy adds the token server-side; desktop injects it via `window.__NEXUS__`.

## Bugs found by tests and fixed this phase

- Mixed-type payload keys crashed canonical JSON (hash chain).
- Whitespace-only project names were accepted (now trimmed and rejected).
- Methods named `list` shadowed the builtin in class bodies (renamed).
- Setting form state from query data inside an effect (restructured).

## Next

Phase 2: `LLMProvider` interface; Anthropic, OpenAI-compatible (OpenAI, LM Studio, custom), Ollama and Gemini adapters verified against mock upstreams; structured output with repair; model catalog and router; usage, cost and budgets; Providers settings UI with Test Connection.
