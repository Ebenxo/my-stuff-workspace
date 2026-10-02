# NEXUS OS — build state

_Last updated: 2026-10-02 (after Phase 10: Timeline and Ideas & notes added to the finished MVP)_

## Current phase

**Phase 10 — polish and end-to-end verification: complete.** Phases 0–10 are done, and every item of the 20-point MVP definition is verified (table below): by unit and integration tests, and again in one scripted browser walkthrough that runs in `scripts/check.py` (items 4 and 14 through the demo objective). What remains is listed under *Not verified / not done*: above all, real models (only scripted ones and a local stand-in were available here), the Tauri shell (cannot be compiled here) and packaging the API for the desktop app.

### Added after Phase 10 (Timeline, Ideas & notes)

Asked for by the owner: one working view of everything that is going on, has gone on and is going to go on, plus a place for ideas and the other small things that matter.

- **Timeline** page (`/timeline`, sidebar, `G T`): *Needs you* (pending approvals, plans awaiting review, paused objectives, agents with a question, workflow runs at an approval step, overdue to-dos), *Happening now* (objectives planning/running/verifying, agents working, workflow runs running), *Coming up* (enabled schedules by next run, dated to-dos), *Keep in mind* (pinned ideas), and *Earlier*: the event log as a history, newest first, grouped by day, every entry linking to what it is about, with *Show every step* and *Load older*. Project filter; live updates. Backed by `GET /api/timeline` (reads the stores of record) and `/api/events` with the new `before_seq` and `exclude_types`.
- **Ideas & notes** page (`/ideas`, `G I`): capture an idea, note or to-do (Enter saves), with an optional project, pin and due time (quick choices); filter by status and kind, search, mark done, edit in place, delete (with a second click), and **start an idea as an objective** (plan reviewed first by default). Migration `0007` (`ideas` table), `/api/ideas` CRUD, `/api/ideas/{id}/objective`, `/api/ideas/due-count` (sidebar badge).
- **Due reminders**: when a to-do comes due the scheduler's tick sends one notification and an `IDEA_DUE` event; moving the due time arms a new one. Events `IDEA_CREATED`, `IDEA_UPDATED`, `IDEA_DELETED`, `IDEA_DUE` carry only a redacted first line.
- Ideas are in universal search (kind `idea`), the command palette (*Ideas & notes*, *Timeline*, *Capture an idea, note or to-do*) and the Command Center (*Needs you & coming up*, *Jot something down* with `todo:`/`note:` prefixes).

### Added in Phase 10 (polish and verification)

- **First-run onboarding**: name, default permission level (with what each level means), workspace folder, connecting a model (the provider dialog, then a connection test with the result shown), then *Try the demo* or *Go to the Command Center*. Skippable; saved once, at the end. Shown until `onboarding_completed` is set.
- **Command palette** (Ctrl/⌘+K, or the top bar's *Commands* button): pages, settings sections, create actions (objective, project, workflow, MCP server, provider), the demo, panel toggles, the command line, shortcuts; the person's projects; live search results; and "Search everything for …". Ranked by prefix, word start, substring and scattered letters, with keywords (typing "mcp" or "api key" finds the right page). Full keyboard use (↑ ↓ Enter Esc) with combobox/listbox semantics. Create actions open their dialogs through `?new=1`/`?add=1` links, so they also work as bookmarks.
- **Keyboard shortcuts**: `/` search, `?` help, `G` then a letter to go to a page, Ctrl/⌘+J bottom panel, Ctrl/⌘+. activity panel. Letters never fire while typing in a field or inside a dialog; modifier shortcuts always do. A help dialog lists them all with the right modifier for the platform.
- **NEXUS command line**: `approvals` (what waits for you), `open <page>`, `search <words>`, `palette`, `keys`, besides `help`, `status`, `events`, `verify`, `clear`.
- **End-to-end walkthrough in `check.py`** (`scripts/e2e.py` + `scripts/e2e/mvp.mjs`): boots an isolated stack (fresh data folder, free ports, its own token, a scripted OpenAI-compatible stand-in model) and drives Chromium through onboarding → palette → project → an agent's tools and an approval → the demo objective to verification → memory and search → a workflow built in the editor and run twice → audit-log verification → shortcuts → 21 pages at 1440 and 390 px checked for sideways scrolling and basic accessibility (named controls, labelled fields, image alt text, unique ids, one main landmark, an h1, page language). The audit first proves it catches planted problems. Any console error or failed request fails the run. Skipped, and reported as skipped, when no browser is installed.
- **Dependency audits in `check.py`**: `pip-audit` (the API's environment) and `pnpm audit` (all JavaScript packages, dev tools included). Clean today. `--offline` skips them.
- Small fixes: System Health lists the MCP check after the core checks; the shared dialog can hide its title visually while keeping it for screen readers.

## The 20-point MVP definition of done

| # | Item | Verified by |
|---|---|---|
| 1 | Launch locally | `scripts/dev.py`; E2E boots API, web app and model and completes onboarding |
| 2 | Connect a provider | provider API tests against mock upstreams; E2E onboarding connects an OpenAI-compatible endpoint and its connection test passes |
| 3 | Create a project | API tests; E2E creates one from the command palette |
| 4 | Give an objective | objective API and UI tests; E2E starts the demo objective (a real objective through the composer is covered by UI tests and the Phase 5–6 live check) |
| 5 | Planner creates tasks | orchestration tests with scripted models; E2E reviews the plan |
| 6 | See a task graph | React Flow component tests; E2E counts ≥ 6 graph nodes |
| 7 | Orchestrator delegates | orchestrator tests (assignments recorded); E2E sees ≥ 3 distinct agents on the objective's tasks |
| 8 | Multiple agents work | as 7: Researcher, Writer, Critic and Verifier in the demo |
| 9 | Agents use tools | agent-loop and executor tests; E2E: the File Manager lists a folder and deletes a file |
| 10 | Review tool activity | tool-call API tests; E2E finds both calls in the project's Tool activity |
| 11 | Approve restricted actions | approval tests (once / session / deny / edit); E2E: the delete waits, the file exists until *Approve once*, then it is gone |
| 12 | Read/write project files | filesystem tests incl. traversal and symlink escapes; E2E writes a file through the files API and an agent reads the folder and removes it |
| 13 | Receive artifacts | artifact versioning tests; E2E opens the verified report |
| 14 | Critic reviews | orchestration tests (review → revise loop); the demo's Critic asks for one revision (graph nodes in E2E) |
| 15 | Verifier checks | PASS / PARTIAL / FAIL tests; E2E sees *Verified* with every criterion met |
| 16 | Store project memory | memory service tests incl. sensitive-data refusal; E2E keeps the objective's memory suggestion |
| 17 | Search memory | retrieval and search tests; E2E search lists Memory and Deliverables results |
| 18 | Create a reusable workflow | workflow API and editor tests; E2E builds one in the editor and saves version 2 |
| 19 | Re-run a workflow | engine tests; E2E runs it twice with different inputs and sees two runs with the right outputs |
| 20 | Inspect full activity log | event-log and hash-chain tests; E2E verifies the chain in System Health and finds the key events recorded |


### Added in Phase 9 (MCP)

- **In-house MCP client** (`app/mcp/`, no new dependency): JSON-RPC 2.0, protocol 2025-06-18 (also accepts 2025-03-26 and 2024-11-05). **stdio**: the server runs as a child process in its own process group with a scrubbed environment plus its configured variables; newline-delimited JSON; stray stdout lines and stderr kept (redacted) as the server's log; the process group is stopped with the server. **Streamable HTTP**: POST per message, JSON or event-stream answers, session id and protocol-version headers, session ended with DELETE, no redirects, loopback never proxied. Every request has a time limit and is cancelled on the server when abandoned; messages over 4 MB end the connection; paginated listing (at most 20 pages, 500 items). NEXUS declares no client capabilities, so a server's sampling/roots/elicitation requests are refused; `ping` is answered.
- **Servers as configuration** (migration `0006`: `integrations`, plus `tools.fingerprint` and `tools.note`): name (becomes the tool prefix, fixed), transport, command/arguments/working folder/variables or address/headers, **secret variables and headers stored write-only in the secret store**, risk level (MODERATE, HIGH default, VERY_HIGH), per-call time limit, on/off. Credentials in plain values, credential-named variables or headers, keys in arguments, tokens in addresses, and secret headers over plain http to another machine are refused with a reason.
- **Tools join the registry** as `mcp__<server>__<tool>` at the server's risk level with `Capability.MCP` (never in private runs) and untrusted results (fenced, scanned, tainting the run as `mcp:<server>/<tool>`). They run only through the ToolExecutor: allow-lists, agent ceilings, policy, approvals (the card names the server and tool), unattended rules and logging are unchanged. Arguments are checked against the server's JSON Schema first. Results: text joined, structured content as JSON, images/audio/binary described, `isError` as a readable failure.
- **Defences against hostile servers**: descriptions and schemas cleaned (invisible and bidi characters removed, lengths capped) and introduced to the model as the server's words; a tool whose description reads like instructions to an AI is registered switched off with the reason (`SECURITY_FLAG`); definitions are fingerprinted, and a changed tool is switched off until the person turns it on again; annotations are shown as the server's claims only.
- **Lifecycle**: enabled servers start with NEXUS (awaited up to 5 s so resumed runs find their tools; slower ones keep starting in the background); start, stop, check (ping with round-trip time), `list_changed` refreshes, a server that exits is reported (`MCP_SERVER_FAILED`) and its tools withdrawn, never restarted silently; the last error is kept; a missing secret is named. System Health has an "MCP servers" check.
- **APIs**: `/api/mcp/servers` (list, create, detail with tools/resources/prompts, edit, delete, start, stop, check, log, read a resource, get a prompt); `/api/tools` now reports `available` and `note`, and a stopped server's tools can still be switched on or off.
- **UI**: Settings → Integrations: server cards (status, risk, launch line, counts, errors, last check, start/stop/check/edit/remove), an add/edit dialog (program or web address, arguments one per line, variables and headers, secret values that are never shown again, risk level with what it means, time limit), details with tools (on/off, arguments, the server's hints, why a tool was switched off), resources (open and preview), prompts and the server's log. Tools & approvals lists MCP tools per server with "Server not running" and review notes. Plain-language activity for every MCP event; live refresh on MCP events.

### Added in Phase 8 (workflows, scheduler)

- **Workflow definitions** (migration `0005`: `workflows`, `workflow_versions`, `workflow_runs`, `schedules`). A definition is a versioned JSON graph of typed steps: start (trigger), agent, tool, condition, approval, transform, output, delay (1 s–24 h), loop (one agent or tool per item, at most 50) and sub-workflow, plus typed inputs (text, number, yes/no). Every save that changes the graph is a new version; a run records the version it used.
- **Validation** before saving counts as runnable: exactly one start, no unknown steps or duplicate ids, no cycles (loops are a step type), everything reachable from the start, yes/no outcomes only on conditions and approvals, each step's config checked against its type, every `{{ expression }}` parsed, agents, tools and sub-workflows checked against what exists and is enabled. Issues come back per step in plain words.
- **Safe expression language** (`workflows/expr.py`): parsed with Python's `ast` and interpreted over an allow-list (literals, arithmetic, comparisons, boolean logic, `x if c else y`, key and index lookup, 21 named functions such as `len`, `lower`, `join`, `default`). No attribute access, no names starting with `_`, no imports or lambdas, size and depth caps. `{{ }}` templates render text; a lone template keeps the value's type.
- **Engine** (`workflows/engine.py`): up to 3 steps run at once; a step runs when every incoming connection is settled; a condition or rejection skips the path not taken (skips propagate, joins wait for their live inputs); the first failure stops the run unless the step says *continue on error*. Agent steps run through the same `AgentRunner` as any run (values from other steps reach the agent as fenced data, and untrusted values taint it); tool steps go through the same `ToolExecutor` under a per-workflow identity allowed only that one tool. Approval steps and tool approvals park the run as *Needs you*; the decision is delivered live or on resume. **Unattended (scheduled) runs never auto-approve a HIGH or VERY_HIGH action**, whatever the project's permission level; they wait.
- **Recovery**: at startup, running workflows resume: a finished agent step keeps its result, an interrupted agent step resumes its run from its checkpoint, an interrupted tool or loop step is marked failed (never re-executed blindly), waiting approvals stay waiting. Cancel stops running steps, cancels their runs and denies their pending approvals. Failed runs can be retried from the failed steps.
- **Sub-workflows** run as child runs (nesting at most 3 deep, never themselves); the parent waits and takes the child's outputs.
- **Scheduler** (`scheduler/`): five-field cron (names, ranges, steps, `@daily`-style shortcuts, day-of-month OR day-of-week like classic cron), any IANA time zone (a time skipped by a DST jump does not fire that day; a repeated time fires once), next-run preview in plain words ("Weekdays at 08:30"). A tick every 30 s while NEXUS is open; a run missed while it was closed fires once on the next start (no pile-up); a schedule whose previous run is still going is skipped and says so; a turned-off workflow's schedule is skipped with a reason, and a deleted workflow's schedule is paused. Scheduled runs are unattended.
- **Events** for every change and run step (`WORKFLOW_*`, `SCHEDULE_*`), shown in plain words in Activity.
- **APIs**: workflows (CRUD, validate, versions, run, runs), workflow runs (list, detail, cancel, retry, approve/reject/answer a step), schedules (list, preview, create, edit, delete, run now).
- **UI**: Workflows page and project Workflows tab (create from a starter, on/off); the editor: React Flow canvas flowing top to bottom, a step toolbar (a new step follows the selected one and is connected to it, so a sequence is built by clicking; handles can also be dragged, with yes/no handles on branching steps), an inspector per step type (agent and tool pickers, JSON arguments, values editor, loop body, sub-workflow picker and inputs), workflow inputs editor, live validation with per-step problems, save as a version, run dialog with typed inputs; a run page with the graph coloured by step state, step details (input, output, error, linked agent run or child workflow), approve/reject/answer, cancel and retry; run history, versions, and a schedule panel (presets, cron with live preview and errors, time zone, inputs, run now, pause).


### Added in Phase 7 (memory, context, search)

- **Memory** (migration `0004`: `memory_items`, `memory_embeddings`, the `search_index` FTS5 table, and `agent_runs.context_report`). One `MemoryService` owns every write: sensitivity guard (refuses keys, tokens, credentials, card, national-ID and bank numbers; records the category only), exact-duplicate reuse, near-duplicate merge that never rewrites the person's own words, pending status for agent-proposed global memory and objective suggestions, importance bands an agent cannot escape, events for every change. Delete is recoverable; erase is permanent.
- **Recall**: `.45 semantic + .15 keyword (BM25) + .15 recency + .15 importance + .10 task relation`, with a relevance gate so importance never makes an unrelated item relevant, and a visible score breakdown. Local deterministic hashing embedder (no download, no network); stale vectors are re-embedded at startup.
- **ContextBuilder**: each run gets its upstream inputs, the project's pinned facts and the most relevant memories within a token budget, cut at sentence boundaries when needed, fenced as data; the decision is stored with the run (a resumed run sees the same context) and reported on the run page.
- **Taint and privacy carry through memory**: notes written after reading untrusted content are marked, capped and taint whoever recalls them; notes from private runs are only recalled into private runs.
- **Tools**: `search_memory` (every agent) and `remember` (agents that may write memory), limited by each agent's `memory_scope`.
- **Suggestions**: a finished objective proposes remembering its outcome; the person keeps, edits or dismisses it on the objective page.
- **Compression**: old, rarely used, low-importance project notes that belong together fold into one extractive summary (no model call), reversibly.
- **Universal search**: projects, objectives, text deliverables and memory in one FTS5 index kept current from the event log (LIKE fallback without FTS5; rebuilt when empty); typed FTS syntax is always literal.
- **APIs**: memory (list with filters, stats, search with score breakdown, create, get, edit/pin, keep, dismiss, delete, restore, erase, compress, undo compression), `GET /api/search`, and `context` on run detail.
- **UI**: Memory page and a project Memory tab (Remembered / Suggestions / Deleted, filters, "rank as agents would", add/edit dialog, pin, tidy), a Memory nav item with the suggestion count, the objective page's "Remember this for next time?" card, the run page's "What it was given" panel, a top-bar search box and a Search page with highlighted matches, and plain-language activity for memory events.

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
- The embedder is lexical (feature hashing), not neural: synonyms do not match. A neural embedder can be plugged in behind the `Embedder` protocol; none is wired up. A `VectorStore` interface for external vector databases is not extracted (vectors live in SQLite and similarity is computed in process over up to 2,000 candidates per query).
- Conversation-scoped memory is defined but unused (no conversation UI drives agents yet). Compression is manual (a button); it is not scheduled (automatic tidying would change what people see without asking). Project files are not in universal search.
- **Workflow agent steps have run only with scripted models**; tool, approval, condition, loop, delay, sub-workflow and schedule paths are exercised with real tools in tests and live.
- **Schedules fire only while NEXUS is running** (a missed run fires once on the next start). There is no OS-level background service.
- Workflows have no webhook, file-watch or event triggers yet (manual, schedule and sub-workflow only). The canvas has no undo; saved versions are the history. Workflows cannot be exported or imported.
- **MCP has been verified against the in-repo fixture server only** (stdio and streamable HTTP, over real processes and sockets). No third-party MCP server (npx/uvx packages) was run: this environment does not install them. The older HTTP+SSE transport is not supported. MCP servers are not sandboxed. Agents cannot read MCP resources or use server prompts yet (the person can browse them); no OAuth flow for remote servers (tokens go in secret headers). A stdio command on Windows that is a `.cmd` shim (such as `npx`) is untested there.
- Memory recall quality with real models is untested; ranking is verified with unit tests and the scripted demo.
- **The end-to-end run uses a scripted stand-in model** (and the scripted demo), not a real one. Its accessibility checks are structural heuristics, not a full audit (no axe-core, which would be a new dependency): colour contrast was computed for the design tokens in Phase 1, and no screen reader has been used. Keyboard use is covered for the palette, shortcuts and forms, not exhaustively.
- The desktop shell received no Phase 10 changes it could not verify: the web app's shortcuts and palette work inside it by design, but the Tauri window itself has still never been built here.

## Testing status

| Area | Result |
|---|---|
| Backend (pytest) | __PYTEST__ passed |
| Lint / format (ruff), strict types (mypy), import contracts (3) | clean |
| Frontend (vitest) | __VITEST__ |
| ESLint, `tsc` (all packages) | clean |
| Web production build | ok |
| Rust sidecar (`cargo test`) | 8 passed |
| API-type drift (`scripts/gen_openapi.py --check`) | up to date |
| Live UI check (Playwright, real API + web app, local stand-in model) | run a Writer that saves an artifact; run a File Manager whose delete waits for approval (file verified present before and gone after); answer an agent's question; browse files, deliverables, runs and tool activity; Tools settings. No console errors; no horizontal overflow at 390 px. Screenshots checked by eye |
| Live objective check (Playwright, real API + web app, scripted demo model) | Try the demo → plan review (2 tasks, approach, criteria) → plan editor opens → Run plan → graph fills in live (research, write, Critic review, revision, second review, verification: 6 nodes, 5 edges) → Verifier PASS with 4/4 criteria → report opens from the result. 15 hand-offs shown; project Objectives tab and Command Center list it. No console errors, no failed requests, no overflow at 390 px; screenshots checked by eye |
| Live memory check (Playwright, real API + web app, scripted demo model) | Demo objective → "Remember this for next time?" → Remember (nav badge showed the suggestion); project Memory tab: add a pinned memory, a key refused in the dialog with its category, "rank as agents would" lists both with reasons; a second demo objective: all 6 runs were given memory (12 items in total), the run page lists what was given; top-bar search finds the report with highlights. No console errors or failed requests besides the deliberate refusal; no overflow at 390 px on Memory, Search, run and objective pages; screenshots checked by eye |
| Live workflow check (Playwright, real API + web app) | Create a workflow; build Start → Approval → Tool (`write_file`) → Output by clicking, add a Delay and connect it by dragging handle to handle (4 connections); validation says *Ready to run*; save as v2; run with an input: the run waits on the approval and the file does not exist (404), approve → Completed and the file holds the rendered text; a bad cron is explained in words; a weekday schedule is created and previewed. No console errors besides the deliberate bad-cron 422s; no overflow at 390 px on the list, editor and run pages; screenshots checked by eye |
| Live MCP check (Playwright, real API + web app, fixture MCP server, local stand-in model) | Settings → Integrations: add the fixture as a program with a secret variable → Running, 11 tools · 2 resources · 1 prompt; tools, a resource preview and the server's log shown; the secret appears in no page, API response or event; Tools & approvals lists the 11 tools under the server. An agent allowed `mcp__fixture__*` proposed `mcp__fixture__echo`: the run waited on a HIGH approval whose card named the server and tool; approved → completed, result `echo: hello from an agent`, run tainted `mcp:fixture/echo`. Stop → 11 tools marked "Server not running" and still listed on the card; start → running; check → answered in 0.4 ms; a server with a wrong command explains it could not find the program. Stopping NEXUS stopped the server process too. No console errors or failed requests; no overflow at 390 px; screenshots checked by eye |
| **Scripted E2E in `check.py`** (`scripts/e2e.py`, Chromium, isolated stack, stand-in model) | 11 steps pass in about a minute: audit self-check, onboarding with a connected model, palette → new project, File Manager tools with an approval (file present before, gone after, both calls in Tool activity), demo objective verified with ≥ 3 agents and ≥ 6 graph nodes, memory kept, search finds Memory and Deliverables, workflow built in the editor and run twice (right outputs, 2 runs), audit chain verified with the key events present, shortcuts, an idea and an overdue to-do (on the timeline under *Needs you* and in today's history, then marked done and gone from it, found by search); 23 pages at 1440 and 390 px with no sideways scrolling and no accessibility findings; no console errors or failed requests |
| Live Timeline / Ideas check (Playwright, real API + web app, demo objective, workflows, schedules and ideas created through the API) | Timeline lanes, *Keep in mind* and *Earlier* by day; Ideas list with overdue/today badges, projects and pins; Command Center cards. No console errors or failed requests; no sideways scrolling at 1440 or 390 px; screenshots checked by eye (they led to: kind icons on the timeline, no repeated "overdue", a clearer pin button, actions under the text on phones) |
| Dependency audits (`pip-audit`, `pnpm audit`) | no known vulnerabilities |

Run everything: `python scripts/check.py`.

## Architecture decisions made after Phase 10 (Timeline, Ideas & notes)

- **Ideas are their own table, not memory.** Memory is what agents are given (with a sensitivity guard that refuses secrets); ideas are the person's notes, kept exactly as written and never given to an agent unless started as an objective (which redacts, like any objective).
- **History is the event log**, paged with `before_seq`, rather than a second store; the timeline's live lists are computed from the stores of record on each request (no cache to go stale).
- **Reminders ride on the scheduler's tick** through a generic `also_on_tick` hook, so the scheduler keeps no dependency on services (layer contract unchanged) and a failing job never stops schedules.
- **Timeline links are built by the client** from `kind`, `id` and `ref_id`; the API stays free of UI routes.

## Architecture decisions made in Phase 10

- The end-to-end run is a plain Playwright script driven by a Python runner, not a Playwright Test project: it needs to boot and tear down its own isolated stack (API, web, stand-in model) on free ports, and one ordered walkthrough mirrors the MVP story better than independent specs.
- The stand-in model is a test fixture under `scripts/e2e/`, reached through the ordinary provider path (so onboarding's connection test is real); the scripted demo provider stays reserved for the demo.
- Accessibility is checked with in-page heuristics plus a self-test, rather than adding axe-core; the trade-off is recorded above.
- Palette create actions are URLs (`?new=1`, `?add=1`, `?focus=objective`), so every action is also a link, and pages stay the owners of their dialogs.
- Single-letter shortcuts are disabled while typing and inside dialogs; only modifier shortcuts work everywhere, so a shortcut can never swallow what someone types.

## Bugs found by tests and the end-to-end run in Phase 10 (all fixed, with regression tests)

- **The palette acted on stale results**: it ranked commands on a deferred copy of the query, so pressing Enter straight after typing "new project" opened *New objective*. Found by the end-to-end run; commands now rank on the live query (only the network search is deferred), and the palette test types and presses Enter in one go.
- Caught while building, not by a test: a form inside the onboarding step contained the provider dialog; React propagates events from portals through the component tree, so submitting the provider form would also have advanced the step. Moved outside the form before it shipped.
- Walkthrough-script issues only (a shortcut pressed before the page had mounted, a wrong field name); the product was fine.

## Architecture decisions made in Phase 9

- The MCP client is written in-house (about 1,500 lines with comments: argument checking, protocol, two transports, client, manager) instead of adding the official SDK: NEXUS needs a small, auditable subset (no sampling, roots or elicitation), the SDK would bring a large dependency tree into a security-sensitive path, and adding software needs the owner's say-so. The fixture server exercises it over real processes and sockets.
- MCP tools are ordinary `ToolDefinition`s, so there is one execution path. Their arguments use a per-tool pydantic model whose JSON schema is the server's own and whose validation is a small JSON Schema checker (no `jsonschema` dependency; `pattern` deliberately not evaluated).
- Risk is chosen per server, not per tool (HIGH by default, never SAFE); the person refines further by switching individual tools off and choosing which agents get them.
- A tool the person has not seen before is on by default (agents still need it on their allow-list), but a *changed* or *instruction-like* definition is off until reviewed: that is where a hostile server would act.
- Runtime state (running, tool lists) lives in memory; only configuration, the last error and the last health check are stored. Tool rows persist while a server is stopped so on/off choices survive restarts.
- Stopping a server from the UI also turns it off for the next start; starting turns it on. There is one switch, not two.

## Bugs found by tests and live checks in Phase 9 (all fixed, with regression tests)

- **A crashed server's failure event was lost**: the stdio reader reported the exit, the manager closed the client, and closing cancelled the reader task that was still writing the event. The report now runs in its own task.
- An edit through `model_copy` skipped validation, so a risk level from the API was stored as a plain string (a serializer warning in the tests showed it); updates are now validated as a whole.
- Live-check script issues only (a wrong provider kind in setup, counting badges before the page had loaded); the product behaved correctly once the checks were fixed.

## Architecture decisions made in Phase 8

- A workflow graph is stored as one validated JSON document per version, not as node and edge tables: versions are immutable snapshots, runs point at the version they used, and nothing ever queries individual steps across workflows.
- Expressions are an allow-listed interpreter over Python's `ast`, not `eval` or a sandboxed language: small, auditable, and safe even for text an agent wrote.
- Workflow steps reuse the agent runner and tool executor instead of a second execution path, so permissions, taint, private-run rules, approvals, redaction and events apply unchanged. A tool step acts under a synthetic per-workflow agent whose allow-list is exactly that one tool.
- Unattended runs never auto-approve HIGH or VERY_HIGH actions, even when the project would; a scheduled run waits for the person instead.
- An interrupted tool step is failed, not replayed (it may already have acted); an interrupted agent step resumes from its checkpoint.
- The scheduler runs in the API process (a 30 s tick) rather than as a separate service; catch-up fires a missed schedule once, not once per missed slot.
- The canvas flows top to bottom and new steps attach to the selected one: the live check showed that dragging small handles was the hardest part of building a workflow, and a horizontal flow did not fit the editor's column or a phone.

## Bugs found by tests and live checks in Phase 8 (all fixed, with regression tests)

- **A decision could be lost**: an approval that arrived while the engine was between checking its waiting steps and going to sleep was not seen until the next event. Decisions are now delivered to the live run and wake it.
- Cancelling a run whose tool step waited on an approval left that approval pending: the executor cleared the step's approval id on cancel. The id is now kept until the step returns normally, and cancel denies it.
- Shutting NEXUS down marked running workflow steps *cancelled* instead of *interrupted* (the runner learned of the shutdown after the engine), so they did not resume. The shutdown order is fixed.
- When a schedule's workflow had been deleted, the schedule was turned off but the generic *skipped* status overwrote the reason, so the schedule list did not say why it stopped.
- Live check: connecting steps by dragging failed on the tiny handles (now larger, and adding a step connects it); the horizontal layout was unreadable in the editor's column and on phones (now vertical).

## Architecture decisions made in Phase 7

- Memory refuses sensitive content instead of redacting it: a half-redacted secret is still a leak, and the person can write the non-sensitive part.
- Context is decided once per run, when it is created, and stored with the request, so resuming a run never changes what the agent knew.
- Files are not pre-loaded into context: reading through tools keeps every read logged and taint accurate.
- Privacy and taint are properties of a memory's provenance, enforced at recall time (private only into private runs; tainted taints the recaller).
- Universal search is fed by an event listener, not by calls sprinkled through services, so anything that emits an event can be indexed; listeners run after the event is committed, so results are current when an action returns.
- Tool handlers may add taint sources (they append to `ToolContext.taint_sources`; the executor merges them), so a tool that passes on untrusted content taints the run like one that fetches it.

## Bugs found by tests and live checks in Phase 7 (all fixed, with regression tests)

- **Privacy leak in the design**: memories written in a private run could have been recalled into a later cloud run. Caught while wiring the ContextBuilder, before any code shipped; now enforced at recall and merge time, with tests.
- An all-zero placeholder ("0000 0000 0000 00") passed the Luhn check and was refused as a card number; cards now need a major-network first digit and more than one distinct digit.
- The first compression threshold (0.45, seed-only linkage) never grouped genuinely related notes; measured similarities (related 0.30–0.36, unrelated ≤ 0.17) set it to 0.28 with any-member linkage.
- A `search_memory` call that recalled a tainted memory did not taint the run (tools could not report taint); now they can.

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

The MVP is built. The most valuable next steps, in order:

1. **Try it with real models** (a local model through Ollama or LM Studio, or a cloud key): planning, the step protocol, reviews and verification have only met scripted models. Expect prompt and repair tuning.
2. **Desktop build on a machine with the Tauri prerequisites**: compile `apps/desktop`, then package the API as a sidecar executable (PyInstaller or uv) so NEXUS runs without a Python toolchain.
3. Windows pass: the sandbox's Windows path, `.cmd` MCP servers, the keychain.
4. Deferred features with seams already in place: agents reading MCP resources and prompts, recovery that switches model/tool or delegates, webhook/file triggers for workflows, a neural embedder, scheduled memory tidying (opt-in), conversation memory.
