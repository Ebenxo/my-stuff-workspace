# NEXUS OS — build state

_Last updated: 2026-09-29 (end of Phase 2)_

## Current phase

**Phase 2 — AI providers: complete.** Phases 0–2 done. Next: Phases 3–4 — single-agent runtime, tools, permissions, approvals.

## What works today (verified by automated tests unless noted)

- **API** (FastAPI, Python 3.11): app factory with lifespan migrations; projects, conversations/messages, user settings, notifications, health, events (list, verify, SSE stream with `Last-Event-ID` resume).
- **Security layer:** loopback-only bind (refuses otherwise), bearer token on every call except `/api/health/ping`, Host/Origin allow-lists (DNS-rebinding defence), CORS allow-list, rate limiting, body-size limit, hardening headers, uniform error envelope with no stack traces, secret redaction on events and logs, secret store (OS keychain → private file fallback), repo secret-scan test.
- **Persistence:** SQLite (WAL, FKs on) via SQLAlchemy 2 async; Alembic migration `0001_foundation` verified up/down and against the models (no drift).
- **Audit trail:** every state change emits an event into a per-project SHA-256 hash chain; `/api/events/verify` detects tampering (tested by editing a row).
- **Job queue:** in-process asyncio queue with bounded concurrency, cancel, failure hooks (interface is Redis/Celery-ready).
- **Web app** (React 19, Vite 8, Tailwind 4, Zustand, TanStack Query): app shell with sidebar, top bar, activity panel, bottom panel (events, errors, terminal), status bar; Command Center; Projects (list, create, edit, archive); Settings (general, system health with audit verification); live event stream with resume. Dark-first semantic design tokens (contrast verified) with a light token set. Checked visually at 1440px and 390px: no horizontal overflow, no console errors.
- **Desktop shell:** Rust `nexus-sidecar` crate (spawn API, random port and token, health wait, shutdown, JS-safe init script) **unit-tested (8 tests)**.

### Added in Phase 2 (providers)

- **`LLMProvider` interface** (`generate`, `stream`, `generate_structured`, `count_tokens`, `available_models`, `test_connection`) with adapters for **Anthropic**, **OpenAI-compatible** (OpenAI, LM Studio, vLLM, custom), **Ollama** and **Gemini**, plus a `ScriptedProvider` used only for tests and the labelled demo.
- **Structured output:** each provider uses its native mechanism (Anthropic forced tool-use, OpenAI/LM Studio `json_schema` with automatic step-down to `json_object` then schema-in-prompt, Ollama `format`, Gemini `responseJsonSchema` with fallback), then a bounded validate-and-repair loop. Repair prompts never echo input values.
- **Reasoning:** `reasoning` only sets provider thinking budgets; thinking blocks are discarded inside the adapter and never stored or shown (tested).
- **Model catalog and router:** tier inference by name, per-model user overrides (context, tier, price); routing precedence manual > agent preference > user rules > default policy by task class; **private tasks only use local models and refuse otherwise** (also when overridden); context-window filtering; fallbacks.
- **Gateway:** route → budget check → bounded retries with exponential backoff honouring `Retry-After` (capped) → fallback models → usage recording. Refusals and budget stops are terminal (never shopped around). Failed structured attempts are still billed. Errors map to failure categories.
- **Usage and budgets:** per-call records (tokens, cost, agent, project, purpose); cost is `NULL`/"unpriced" when the price is unknown, never guessed; local models are known-free; daily/monthly USD and token budgets, per-project (from the project's own settings) and per-agent limits, warn-once at a threshold, hard stop optional, "expensive call" warning.
- **Security:** API keys are write-only (stored in the secret store, referenced by name; the API returns only `has_key` and the last four characters); tested absent from responses, database rows, audit events and logs. HTTPS required when a key is sent to a non-loopback URL; credentials in URLs refused; redirects never followed (key-replay defence, tested with a real server); loopback endpoints bypass system proxies; Gemini key sent in a header, not the URL; upstream error text is redacted.
- **UI:** Settings → AI providers (add via kind picker, connect-and-test, edit, rotate/remove key, enable/disable, remove with confirmation) and Settings → Usage & budgets (grouped usage table, budget form); Command Center prompts to connect a provider when none exists; project form has a monthly budget; System Health has an AI-providers check.

## Not verified / not done (honest list)

- **Live provider calls beyond authentication.** The Anthropic adapter reached the real API from this environment and got the expected 401 for a fake key (request format accepted, error mapping confirmed). Successful generation, streaming, structured output and token counting against Anthropic, OpenAI, Gemini and Ollama are verified only against mock servers and one real loopback server; no valid keys are available here.
- Gemini `responseJsonSchema` support per model version is unconfirmed live (fallback to schema-in-prompt is tested).

- **Tauri glue (`apps/desktop/src-tauri`) is written but has never been compiled** — the build container lacks webkit2gtk/GTK. Syntax-checked with `rustfmt` only.
- Production packaging of the Python API for the desktop app (PyInstaller/externalBin) is not done.
- OS keychain path is untested here (the container has no keychain); the file fallback is tested and reported as *degraded*.
- The Command Center objective box is present but disabled until the planner/runtime exist (Phase 5).
- No live provider calls are possible in this environment (no API keys).

## Testing status

| Area | Result |
|---|---|
| Backend (pytest) | 220 passed |
| Lint / format (ruff), strict types (mypy), import contracts | clean |
| Frontend (vitest) | 39 passed (shared 9, web 30) |
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

## Bugs found by tests and live checks in Phase 2 (all fixed, with regression tests)

- **LM Studio without a base URL called `api.openai.com`** (adapter fell through to the OpenAI default). Found only by running the real stack against a local server. Default URLs now live in one table used by both the adapters and the UI.
- 3xx responses were treated as success and non-JSON 200 bodies crashed with a raw `JSONDecodeError`; malformed stream frames crashed the stream. Now clear `ProviderError`s (found by the real-socket redirect test).
- `NoRouteError` surfaced as an HTTP 500; now 409 with an actionable message.
- `GET /api/providers/{id}` was never exposed.
- The scripted demo provider appeared in the manual provider picker.

## Bugs found by tests in Phase 1 (fixed)

- Mixed-type payload keys crashed canonical JSON (hash chain).
- Whitespace-only project names were accepted (now trimmed and rejected).
- Methods named `list` shadowed the builtin in class bodies (renamed).
- Setting form state from query data inside an effect (restructured).

## Next

Phases 3–4: `AgentDefinition`/`AgentRun`, the agent loop with all guards (max steps, timeout, tool-use and token limits, retries, loop detection) and checkpointing; `ToolRegistry`; path-guarded filesystem tools; sandboxed Python and command execution; the policy engine, approvals (once / session / deny / edit) and taint tracking; artifact store with versions; one agent running a real tool-using task end to end (scripted provider), with UI for approvals and tool activity.
