# NEXUS OS — build state

_Last updated: 2026-09-29 (end of Phases 5–6)_

## Current phase

**Phases 5–6 — planner, orchestrator, task graph, multi-agent review and verification: complete.** Phases 0–6 done. Next: Phase 7, memory and the context engine.

### Added in Phases 5–6 (objectives and the multi-agent team)

- **Objectives** (migration `0003`: `objectives`, `tasks`, `task_dependencies`). An objective moves `RECEIVED → PLANNING → AWAITING_PLAN_APPROVAL → RUNNING → VERIFYING → COMPLETED | PARTIAL | FAILED`, or `PAUSED` when something needs the person, or `CANCELLED`. Run modes: *review the plan first* (default) or *auto*. Execution modes: *normal* (the project's permission level) or *safe steps only* (the cautious level: anything above SAFE asks).
- **Planner → validator → tasks.** The Planner (read-only tools) returns a structured `PlanResult`. The validator rejects cycles, unknown/disabled/fixed-role agents, duplicate keys and too many tasks for the stated complexity (hard limit 12), giving the Planner one repair round; it silently corrects soft problems (a tool outside the agent's allow-list) and reports them as warnings shown in the plan. A strategy estimator names the cheapest shape that fits (`single_agent`, `pipeline`, `parallel`, `reviewer`) with a rationale and a token estimate.
- **Plan review.** The person sees the tasks, dependencies, approach, completion criteria, assumptions and risks, and can edit the plan (tasks, agents, dependencies, review/optional switches, criteria) with the same validation as the Planner's plan, run it, run only the safe steps, or cancel.
- **Orchestrator.** Ready tasks run in parallel (at most 3) as supervised asyncio tasks through the same `AgentRunner` as single runs. Upstream outputs are passed as fenced, untrusted context. A task parked on an approval shows `NEEDS_APPROVAL`; a question from an agent blocks the task and pauses the objective once nothing else can run.
- **Critic review loop.** A task marked for review gets a Critic task; blocking issues (blocker/major) create a *Revise* task for the original agent with the issues as input, then a fresh review, up to 2 rounds. Every round is a real node in the graph. If issues remain after the limit, the review is flagged `open_issues` and the Verifier sees it.
- **Verifier.** Checks each completion criterion against the deliverables themselves (it must read them) and returns PASS / PARTIAL / FAIL with evidence and missing requirements. One follow-up re-plan (at most 4 tasks, covering only what is missing) before an honest PARTIAL or FAIL.
- **Deterministic recovery** (`orchestration/recovery.py`): per failure category and code, retry, resume from the checkpoint (limits and interruptions, with a fresh per-attempt allowance), skip (optional tasks), block for the person, or fail; every decision is an event with its reason. Retry, skip and answer are available per task in the UI; blocked tasks never deadlock the objective.
- **Agent messages** (`TASK_REQUEST`, `TASK_RESULT`, `QUESTION`, `ERROR`, `REVIEW_REQUEST`, `REVIEW_RESULT`) are recorded as `AGENT_MESSAGE` events: structured fields and short summaries only, never reasoning.
- **Demo project** (`POST /api/demo`, "Try the demo" on the Command Center): *Research three AI coding assistants and create a comparison report.* Fictional products in files labelled "DEMO DATA", answered by the scripted demo model chosen by manual override. Everything else is the real system: Planner, validator, orchestrator, Researcher, Writer, Critic (asks for one revision), Verifier, tools, artifacts, events. The demo model is never routed automatically and never offered in model pickers.
- **APIs:** objectives (create, list, detail with tasks and messages, run, edit plan, cancel, resume), tasks (detail, retry, skip, answer), demo.
- **UI:** the Command Center objective box (project, *review the plan first*, *keep on this device*, Ctrl/⌘+Enter) and objectives list; the objective page (status and progress, plan review with approach and criteria, plan editor, task graph in React Flow with a list view, task details with answer/retry/skip, approvals for the objective's runs, verified result with criteria and deliverable links, agent hand-offs, activity); an Objectives tab per project; plain-language activity for every objective, task, review, verification and recovery event.

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
- No live provider calls are possible in this environment (no API keys).
- **Agents and objectives have run end to end only against scripted models**: the `ScriptedProvider` in tests and the demo, and a local OpenAI-compatible stand-in server in the Phase 3–4 live check. How well real models plan, follow the step protocol, review and verify is unverified; validation, the repair loop, `INVALID_OUTPUT` handling and deterministic recovery are the safety net.
- Recovery does not yet switch to a different model or tool, or delegate to another agent, as the design allows; the gateway's own fallback models are the only model switch. Supervisor, debate, map-reduce and swarm strategies are not built.
- Sandbox limits are verified on Linux only (rlimits, process-group kill, network namespace). On Windows only the timeout, env scrubbing and working folder apply, and that path has not been run.
- Memory tools (`search_memory`, `remember`) are Phase 7; agent allow-lists will gain them then.

## Testing status

| Area | Result |
|---|---|
| Backend (pytest) | 785 passed |
| Lint / format (ruff), strict types (mypy), import contracts (3) | clean |
| Frontend (vitest) | 102 passed (shared 9, web 93) |
| ESLint, `tsc` (all packages) | clean |
| Web production build | ok |
| Rust sidecar (`cargo test`) | 8 passed |
| API-type drift (`scripts/gen_openapi.py --check`) | up to date |
| Live UI check (Playwright, real API + web app, local stand-in model) | run a Writer that saves an artifact; run a File Manager whose delete waits for approval (file verified present before and gone after); answer an agent's question; browse files, deliverables, runs and tool activity; Tools settings. No console errors; no horizontal overflow at 390 px. Screenshots checked by eye |
| Live objective check (Playwright, real API + web app, scripted demo model) | Try the demo → plan review (2 tasks, approach, criteria) → plan editor opens → Run plan → graph fills in live (research, write, Critic review, revision, second review, verification: 6 nodes, 5 edges) → Verifier PASS with 4/4 criteria → report opens from the result. 15 hand-offs shown; project Objectives tab and Command Center list it. No console errors, no failed requests, no overflow at 390 px; screenshots checked by eye |
| Scripted E2E in `check.py` | Phase 10 |

Run everything: `python scripts/check.py`.

## Architecture decisions made in Phases 5–6

- The orchestrator is code, not a model: planning, reviewing and verifying are agent runs with typed results (`PlanResult`, `ReviewResult`, `VerificationResult`), but dispatch, recovery, revision limits and replanning are deterministic and unit-tested.
- A plan from a model is a proposal: it is validated before anything exists, and an edited plan is validated the same way.
- Objectives, like runs, execute as supervised asyncio tasks, not on the job queue (they wait on people). Startup recovery resumes interrupted objectives and requeues their in-flight tasks; a run is resumed from its checkpoint rather than restarted.
- A task that hit a limit resumes with a fresh allowance per attempt (steps, tool calls, tokens × attempt); without it, resuming a step-limited run would stop again immediately.
- Revisions and reviews are real tasks with their own rows, dependencies and runs, so the graph shows exactly what happened and each round can be inspected.
- The scripted demo model is excluded from automatic routing, and fallbacks stay within the same kind (demo to demo, real to real), so a real objective can never be answered by the demo, and the demo can never spend money on a real provider.
- Orchestrated runs carry a short title (the task's name, or "Plan: …"); activity and run lists show it instead of the machine-built prompt.

## Bugs found by tests and live checks in Phases 5–6 (all fixed, with regression tests)

- **Resuming a run that stopped at its step limit stopped again at once**; fixed with the per-attempt allowance above.
- **Scripted demo answers never matched**: the prompt fences untrusted content with a random id, so the script key changed every run; the id is stripped when keying.
- Provider schema names must match `[A-Za-z0-9_-]{1,64}`; generic step types produced names like `StepWith[PlanResult]`. Now named subclasses, and names are sanitised.
- Recovery treated a model refusal, a missing model or key, and a bad request as retryable.
- Restricting the demo model from automatic routing broke fallbacks between scripted models in tests; fallbacks are now limited to the same kind instead of dropping demo candidates.
- After the demo ran, its scripted provider counted as "a connected provider", hiding the *Connect an AI provider* prompt and enabling objectives that no model could plan. Only real providers count now.
- Live check: the Activity panel showed the Planner's full internal prompt as the run's description (now the short title); the task graph did not re-fit when reviews and revisions joined it mid-run, or when the details panel closed; task rows were clipped on a 390 px screen (grid columns now shrink).

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

Phase 7, memory and the context engine: memory records with scopes (user, project, agent) and visible provenance; proposals from finished objectives (sensitive data filtered) that the person can keep, edit or discard; `search_memory` and `remember` tools on the relevant agents' allow-lists; a context builder that ranks and budgets what each agent sees (objective, task, upstream outputs, relevant memory, files) with the same fencing for untrusted text; a Memory page to browse, edit, pin and delete.
