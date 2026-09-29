# NEXUS OS — build state

_Last updated: 2026-09-29 (end of Phases 3–4)_

## Current phase

**Phases 3–4 — agent runtime, tools, permissions, approvals: complete.** Phases 0–4 done. Next: Phases 5–6, planner, orchestrator, task graph and the multi-agent team.

### Added in Phases 3–4 (agent runtime, tools, permissions)

- **Ten built-in agents** (Orchestrator, Planner, Researcher, Coder, Data Analyst, Writer, Designer, File Manager, Critic, Verifier) defined in code with role prompts, tool allow-lists, risk ceilings and limits; synced at startup; built-ins can be *tuned* (model, limits, tools, permissions, enabled) but not rewritten; custom agents can be created, edited and deleted.
- **`AgentRunner`**: structured `AgentStep` loop (tool call / finish / ask the person) through the gateway with repair. Guards: step cap with a last-step warning, tool-call cap, token budget with an 85 % warning, working-time limit that excludes time waiting for a person, loop detection (nudge at 3 identical calls, stop at 5). Checkpoint after every step; resume after a crash, a restart or an answer; an in-flight action is never silently re-run; taint survives resume; cancel closes approvals and tool calls; app shutdown parks runs as `INTERRUPTED`; only artifacts the run really created appear in its result; the prompt and observations are stored redacted; old results are elided from the model's view (never from the checkpoint) to fit the context budget.
- **Tools (22 built in):** filesystem (path-guarded, history on overwrite, soft delete to trash), artifacts (versioned), CSV/JSON parsing, calculator (safe AST), datetime, read-only SQLite queries (authorizer + time limit), sandboxed Python (stdlib only, no site-packages, scrubbed env), commands (always ask; denylist; working folder checked before anyone is asked), read-only git (hostile repo config neutralised), SSRF-safe HTTP, web search (SearXNG/Brave, user-configured), clipboard offer (needs a click).
- **`ToolExecutor`**: the only path to a tool handler: allow-list → private-run check → schema validation → risk assessment → pure policy engine → approval (once / session / deny / edit, with re-validation and re-assessment of edits) → timeout → redaction and size cap → taint and injection scan → `ToolCall` row and events.
- **Sandbox**: local subprocess backend with process-group kill, rlimits, network namespace isolation where the OS allows, scrubbed environment; `enforced` reports what was really applied.
- **Private runs** ("Keep on this device"): local models only (router) and no tool that reaches off the machine (web, search, MCP, networked commands); hidden from the model and refused by the executor.
- **APIs**: agents (CRUD, run), runs (list, detail with steps and tool calls, cancel, resume, answer), approvals (list, decide, session grants list/revoke), tools (catalogue, enable switch), tool calls, artifacts (list, versions, content), project files (list, read, write with history, soft delete) with the same path guard agents use.
- **UI**: Agents page (team cards, run dialog, tune/create dialog with risk-ceiling warnings and validation), live run page (status, question box, approval cards, step timeline, result with artifact links, tool calls, cancel/resume), approval cards (what will happen, taint warning, approve once/for session/edit JSON/deny), Approvals page and side-panel tab with counts in the sidebar, project tabs (Files with editor, Deliverables with version picker and sandboxed preview, Runs, Tool activity, Approvals), Settings → Tools & approvals (per-tool switches, session grants), bottom-panel Tools tab, Command Center approval banner and recent runs, plain-language activity for every agent/tool/approval event, copy offers as a toast.
- **Operations**: one API per data folder (OS lock taken before startup recovery); no trailing-slash redirects; `scripts/dev.py` refuses to start over an existing server and shuts down every child process on Ctrl-C or SIGTERM.

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
- Multi-step objectives are not built yet (planner and orchestrator arrive in Phase 5). The Command Center runs a single agent directly until then.
- No live provider calls are possible in this environment (no API keys).
- **Agents have run end to end only against scripted models**: the `ScriptedProvider` in tests, and in the live UI check a local OpenAI-compatible stand-in server that replays fixed steps. How well real models follow the step protocol is unverified; the structured-output repair loop and `INVALID_OUTPUT` handling are the safety net.
- Sandbox limits are verified on Linux only (rlimits, process-group kill, network namespace). On Windows only the timeout, env scrubbing and working folder apply, and that path has not been run.
- Memory tools (`search_memory`, `remember`) are Phase 7; agent allow-lists will gain them then.

## Testing status

| Area | Result |
|---|---|
| Backend (pytest) | 714 passed |
| Lint / format (ruff), strict types (mypy), import contracts (3) | clean |
| Frontend (vitest) | 83 passed (shared 9, web 74) |
| ESLint, `tsc` (all packages) | clean |
| Web production build | ok |
| Rust sidecar (`cargo test`) | 8 passed |
| API-type drift (`scripts/gen_openapi.py --check`) | up to date |
| Live UI check (Playwright, real API + web app, local stand-in model) | run a Writer that saves an artifact; run a File Manager whose delete waits for approval (file verified present before and gone after); answer an agent's question; browse files, deliverables, runs and tool activity; Tools settings. No console errors; no horizontal overflow at 390 px. Screenshots checked by eye |
| Scripted E2E | arrives with the demo objective (Phase 10) |

Run everything: `python scripts/check.py`.

## Architecture decisions made in Phases 3–4

- Agents never import the ORM; they use repository stores that return DTOs. The import contract forbids *direct* imports (the stores naturally depend on the ORM).
- The agent protocol is one structured `AgentStep` per model turn (provider-native structured output plus repair), not provider-specific tool calling, so every provider, including local models, behaves the same and every action lands in the executor.
- Runs execute as supervised asyncio tasks, not on the bounded job queue: a run parked on an approval can wait a day and must not hold a worker slot. At most 8 run at once.
- The checkpoint records the proposed action before it executes, so recovery can tell "done" from "may have happened"; the latter is reported to the agent, never replayed.
- Time waiting for a person is excluded from an agent's working-time limit.
- Private means private: besides local-only models, tools that reach off the machine are unavailable (hidden and refused).
- Session approvals live in memory: they end when NEXUS restarts, by design.

## Bugs found by tests and live checks in Phases 3–4 (all fixed, with regression tests)

- **A second API instance on the same data folder interrupted the first one's live runs**: startup recovery ran before the port bind failed. Found live when a stale dev server was still running. Now an OS lock on the data folder is taken before any startup work.
- **Trailing-slash redirects leaked past the dev proxy**: the run page asked for `/api/projects/` before it knew the project, FastAPI redirected to the API's own origin, and the browser followed without its token (401s in the console). Fixed both ends: no redirects at all, and the query waits for an id.
- `scripts/dev.py` left Vite and the API running after it was stopped (children inherited an ignored SIGINT; pnpm does not forward signals), and reported "ready" against an old server on the same port.
- The Activity panel showed each approval and completion twice (notification events repeated them) plus a "Usage recorded" line per model call; these stay in the raw Events tab only.
- **The sandbox could hang until its timeout after an output flood**: once the output cap was hit it stopped reading, asyncio paused the full pipe and never saw EOF after the kill, and `proc.wait()` waits for the pipes. Seen once as an intermittent full-suite failure; reproduced deterministically by delaying the kill; fixed by reading (and discarding) until EOF.
- Recursive CTEs were refused by the SQLite authorizer instead of being time-limited.
- `run_command` with an impossible working folder asked a person to approve a command that could never start.
- A cancel that arrived while a tool call was being set up for approval left the call "awaiting approval" forever.
- Approval cards could appear before the tool call's status said it was waiting (ordering).
- A run's status can briefly lag its new approval (the approval row is written first, then the run is marked waiting). A test assumed otherwise and failed intermittently; tests now wait for the status, and the UI refreshes on the approval event.
- `TOOLS.md` promised that web search was blocked for private runs; it was not. Now it is, for every outside-reaching tool.
- `SECURITY.md` claimed dependency audits ran in `scripts/check.py`; they do not (corrected; scheduled for Phase 10).

## Architecture decisions made in earlier phases

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

Phases 5–6: `Objective`, `Task`, `TaskDependency` tables (migration `0003`); `PlanResult` from the Planner with a validator (DAG, known agents, tools on allow-lists, approvals flagged); `TaskGraph` (topological order, ready set, cycle detection, downstream cancellation); a strategy estimator that picks the cheapest shape (single agent, pipeline, parallel, reviewer); the orchestrator executing tasks with bounded concurrency through `AgentRunner`, passing upstream outputs as fenced context, with deterministic recovery per failure category; Critic review → revision loop; Verifier with PASS/PARTIAL/FAIL and one replan; agent messages as events; objective APIs (create, plan preview, edit plan, run, auto-run safe steps, cancel, retry task); the Command Center objective box, plan preview and task-graph view; the demo project (clearly labelled, scripted).
