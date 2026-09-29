# NEXUS OS — architecture

## 1. Shape of the system

```
┌──────────────────────────── Host (one of) ────────────────────────────┐
│  apps/desktop  Tauri shell: window, keychain, launches the sidecar    │
│  browser       `pnpm dev` for development                             │
└──────────────┬────────────────────────────────────────────────────────┘
               │ loads
┌──────────────▼────────────────┐   HTTP + SSE (127.0.0.1, bearer token)
│ apps/web  React UI            │◄──────────────────────────────────────┐
│ state: Zustand + TanStack Query│                                       │
│ graphs: React Flow  code: Monaco│                                     │
└───────────────────────────────┘                                       │
                                                       ┌────────────────▼───────────────┐
                                                       │ services/api   FastAPI          │
                                                       │  api/  thin routers, auth, SSE  │
                                                       │  services/  use-case layer      │
                                                       │  orchestration/ agents/ tools/  │
                                                       │  permissions/ memory/ workflows/│
                                                       │  providers/ events/ scheduler/  │
                                                       │  repositories/ models/ (SQLAlchemy)│
                                                       └───────┬──────────────┬──────────┘
                                                               │              │
                                                     SQLite (WAL)      Workspace filesystem
                                                     + vector table    (per-project roots)
```

Everything runs on the user's machine. Cloud model providers are optional adapters; with Ollama or LM Studio nothing leaves the machine.

## 2. Repository layout

```
nexus-os/
  apps/
    web/          React + Vite + TS + Tailwind UI (the only UI codebase)
    desktop/      Tauri 2 shell around apps/web; supervises the Python sidecar
  services/
    api/          The Python service (FastAPI + runtime). See §3.
  packages/
    ui/           Design tokens (CSS variables) + primitives (shadcn-style, Radix-based)
    shared/       Framework-free TS helpers (formatting, event stream client, id utils)
    schemas/      TS types generated from the backend OpenAPI + Zod schemas for SSE events
  data/           Fixtures only: demo source pack, model catalog. Runtime data is NOT here.
  docs/           This documentation
  tests/          Cross-cutting tests (E2E with Playwright)
  scripts/        dev / test / lint / openapi-generation helpers
```

Runtime data (database, secrets, project workspaces) lives in `NEXUS_HOME` (default: the OS user-data directory; `scripts/dev` uses `data/dev/`, which is gitignored).

## 3. Backend modules and their allowed dependencies

The dependency direction is strictly downward. Lint enforces it (import-linter contracts in `pyproject.toml`).

```
api ─► services ─► orchestration ─► agents ─► tools ─► permissions
                        │             │         │          │
                        ▼             ▼         ▼          ▼
                     memory        providers  files/    events ─► repositories ─► models
                     workflows                sandbox                     ▲
                     scheduler                                          core
```

| Module | Responsibility | May import |
|---|---|---|
| `core` | settings, ids, clock, logging, errors, secret store, security primitives (path guard, SSRF guard, redaction) | stdlib + pydantic only |
| `models` | SQLAlchemy ORM tables | `core` |
| `repositories` | all SQL; returns ORM rows or pydantic DTOs; no business rules | `models`, `core` |
| `schemas` | pydantic API/contract models shared across layers | `core` |
| `events` | EventBus (in-process pub/sub), persistent audit log with hash chain, SSE fan-out | `repositories`, `schemas`, `core` |
| `providers` | `LLMProvider` interface + adapters, model catalog, router, usage recorder | `schemas`, `core`, `events` |
| `permissions` | risk model, policy engine, approvals, session grants | `events`, `repositories`, `schemas`, `core` |
| `files` | per-project virtual workspace, path guard, artifact store, versioning | `repositories`, `events`, `core` |
| `tools` | ToolDefinition, registry, built-in tools, sandbox manager | `permissions`, `files`, `events`, `core` |
| `memory` | MemoryItem service, embedder, vector store, retrieval, context builder | `repositories`, `providers`, `events`, `core` |
| `agents` | AgentDefinition, built-in agents and prompts, AgentRunner (the loop) | `tools`, `permissions`, `memory`, `providers`, `events` |
| `mcp` | MCP client (stdio, streamable HTTP), server manager that registers MCP tools into the registry (a sibling of `agents`; neither imports the other) | `tools`, `repositories`, `events`, `core` |
| `orchestration` | Planner integration, plan validation, task graph, executor, review loop, recovery, verifier | `agents`, `memory`, `events`, `repositories` |
| `workflows` | workflow schema, expression evaluator, engine | `orchestration`, `agents`, `tools`, `events` |
| `scheduler` | cron schedules, job queue | `workflows`, `events` |
| `services` | use cases called by routers (ProjectService, ObjectiveService, …) | everything below |
| `api` | FastAPI routers, auth middleware, rate limiting, SSE endpoint | `services`, `schemas` |

Rules of thumb: routers contain no logic; services own transactions; `orchestration` and `agents` never import FastAPI or SQLAlchemy sessions directly (they use repositories through injected interfaces), which keeps them testable with in-memory fakes and splittable into a worker process.

## 4. The action pipeline (the only path to side effects)

```
AgentRunner
   │ proposes ToolCall(name, args)         ← model output is a *proposal*, never an action
   ▼
ToolRegistry.resolve(name)                 ← unknown/disallowed-for-this-agent → rejected
   ▼
Arguments validated against tool.input_schema (pydantic)
   ▼
PolicyEngine.evaluate(tool, args, agent, project policy, run context)
   │   effective risk = max(static risk, tool.assess_risk(args))
   │   ─► DENY | ALLOW | REQUIRE_APPROVAL
   ▼ (REQUIRE_APPROVAL)
ApprovalService.request()  → Approval row + APPROVAL_REQUIRED event → run parks
   │   human: Approve Once / Approve For Session / Deny / Edit Action
   │   edited args are re-validated and re-evaluated; an edit can never lower risk
   ▼
ExecutionRuntime.execute(tool, args, ToolContext)   ← sandboxed where relevant, timeout, output cap
   ▼
ToolCall row (args, redacted result, status, duration, provenance) + TOOL_CALLED / TOOL_COMPLETED events
   ▼
Result returned to the agent wrapped as UNTRUSTED tool result
```

There is no other way for an agent to touch the filesystem, network, processes or database. Future computer-use actions plug into the same pipeline as a `ComputerActionProposal → PolicyEngine → ComputerExecutor` (see §11).

## 5. Execution lifecycle of an objective

```
User submits objective (project, run mode, private?)
  → OBJECTIVE_CREATED                                  status RECEIVED
  → Planner agent run (read-only tools)                status PLANNING
       output: PlanResult (structured, schema-validated)
  → PlanValidator: DAG acyclic, agents exist and may take tasks, keys unique,
       task cap by complexity; tools outside an agent's allow-list dropped (warning);
       one repair round with the issues                PLAN_CREATED
  → StrategyEstimator names the shape + rationale
  → Tasks + TaskDependency rows created                TASK_CREATED (status WAITING)
  → run_mode == review_plan → AWAITING_PLAN_APPROVAL  (Run plan / Run safe steps only / Edit plan / Cancel)
    run_mode == auto → proceed (tool approvals still apply)
  → Orchestrator loop                                  status RUNNING
       ready tasks (all deps COMPLETED or SKIPPED) run as supervised asyncio tasks, at most 3 at once
       each task = one AgentRun (loop in §6), upstream outputs passed as fenced untrusted context
       TaskResult → outputs stored, artifacts versioned
       review-marked tasks → Critic task → ReviewResult
            blocking issues + rounds left → "Revise" task, then a new review (visible in graph)
       failure → recovery.decide → retry | resume | skip (optional) | block (ask the person) | fail
       nothing can run and a task needs the person → PAUSED (Continue after answering / retrying / skipping)
  → Verifier agent run against completion criteria     status VERIFYING → PASS | PARTIAL | FAIL
       PARTIAL/FAIL with replan budget → follow-up tasks (≤ 4), verify again; else finalise
  → OBJECTIVE_COMPLETED | OBJECTIVE_FAILED             status COMPLETED | PARTIAL | FAILED, result + artifact list
  (Phase 7) memory proposals from the finished objective
```

Task statuses: `WAITING` dependencies unmet · `QUEUED` ready · `RUNNING` · `NEEDS_APPROVAL` its run is parked on an approval · `BLOCKED` needs the person (a question or a recovery decision) · `COMPLETED` · `SKIPPED` optional or skipped by the person · `FAILED` · `CANCELLED`.

Objective statuses: `RECEIVED, PLANNING, AWAITING_PLAN_APPROVAL, RUNNING, VERIFYING, PAUSED, COMPLETED, PARTIAL, FAILED, CANCELLED`.

Runs and objectives are supervised asyncio tasks rather than `JobQueue` jobs because they can wait on a person for a day and must not hold a worker slot. On restart, interrupted objectives resume: in-flight tasks are requeued and their runs continue from the last checkpoint.

### Strategy selection ("cheapest effective")

Before dispatching, the `StrategyEstimator` reads the validated plan's shape: task count, distinct specialisations, dependency depth, parallel width, reviews, and estimates tokens. It names the cheapest strategy that fits: `single_agent` (one specialist, no review), `pipeline` (sequential handoff), `reviewer` (produce → critique → revise), `parallel` (independent branches). The Planner is asked for the fewest tasks that will reliably work, and the validator caps the count by the complexity the plan declares (trivial 2, small 4, medium 8, large 12), so a trivial objective is never fanned out across many agents. `supervisor`, `debate`, `map_reduce` and `swarm` are not built.

## 6. The agent loop

```
observe → retrieve context → decide (structured AgentStep) → validate → policy → execute → observe → evaluate → repeat | finish
```

- **Protocol:** each model turn returns an `AgentStep` (Pydantic): `{summary: str(≤200 chars), action: tool_call | finish | ask_human}`. `summary` is a one-line, user-visible description of intent; no reasoning trace is requested, stored or shown. Structured output is obtained through each provider's native mechanism (Anthropic forced tool-use, OpenAI/LM Studio `json_schema`, Ollama `format`, Gemini `responseSchema`) with a validate-and-repair fallback.
- **Guards (all enforced in `AgentRunner`, all configurable per agent):** `max_steps`, wall-clock `max_runtime`, `max_tool_calls`, token budget, model-call retry limit, invalid-output repair limit, loop detection (identical `(tool, normalised-args)` seen `N` times, or `M` consecutive steps with no new information).
- **Checkpointing:** after every step the run's step history is persisted on `AgentRun.checkpoint`. On startup `recover_interrupted()` finds runs left `RUNNING` and either resumes from the checkpoint or marks them `FAILED(TIMEOUT)` depending on policy. A parked approval survives a restart because the Approval row is the source of truth.
- **Cancellation:** cooperative, checked between steps and inside long tool calls.

## 7. Context engine

`ContextBuilder` assembles each model call from typed segments, each with a **trust level**, a **rank score** and a **token cost**:

| Segment | Trust | Where it goes |
|---|---|---|
| system instructions, agent definition | TRUSTED | system message |
| current objective, assigned task | TRUSTED (user-authored) | system/user preamble |
| project settings and stated facts | TRUSTED | user message, labelled |
| memory recalls | DATA (recalled notes, not instructions) | user message, labelled |
| upstream task outputs | UNTRUSTED-DERIVED | user message, labelled |
| file contents, web pages, MCP results, other tool results | UNTRUSTED | user message, fenced with a per-request random nonce; fence-breaking sequences neutralised |

Ranking = weighted blend of semantic relevance, recency, importance and task relationship; lowest-ranked segments are dropped (or summarised) to fit the token budget. Trust labelling is a soft defence; hard defences are structural (SECURITY.md §6–7).

As built (Phase 7, `app/agents/context.py`): the ContextBuilder runs once when a run is created. Candidates in priority order are the caller's blocks (an orchestrated task's upstream outputs and reviews), the project's pinned memories, and memories recalled for the run's title and task. The budget (12,000 tokens by default, estimated at 3.5 characters per token plus 10 %) is filled in that order; a caller's block that does not fit is cut at a sentence boundary, a memory that does not fit is left out. The chosen blocks are stored with the run's request, so a resumed run sees exactly the same context, and a `ContextReport` (given, shortened, left out, why, tokens) is stored with the run and shown on the run page. Files are not pre-loaded: agents read them through tools, so every read is logged and taints the run.

## 8. Real-time model

All state changes go through `EventBus.emit(event)`, which (1) persists to the `events` table with a per-project hash chain, then (2) fans out in-process. `GET /api/events/stream` is an SSE endpoint that replays from `Last-Event-ID` (event sequence number) and then tails live events, so the UI can reconnect without gaps. The UI uses a fetch-based SSE reader (so it can send the bearer header) and applies events to TanStack Query caches and Zustand stores.

## 9. Providers and routing

`LLMProvider` (abstract): `generate`, `stream`, `generate_structured`, `count_tokens`, `available_models`. Adapters: Anthropic, OpenAI-compatible (covers OpenAI, LM Studio, vLLM, custom), Ollama (native), Gemini. A scripted `DemoProvider` exists for the demo and tests only and is labelled as such everywhere it appears.

`ModelRouter` picks `[primary, *fallbacks]` for a call from: the agent's `preferred_model`/`fallback_models`; user routing rules (task class → model, privacy: private → local only, context size → long-context model); model profiles (capabilities, context length, cost, latency); and a manual override on the run. Usage (tokens, estimated cost, agent, project, workflow) is recorded per call; budgets are checked before calls and can warn or block.

## 10. Workflows, scheduler, MCP

- **Workflow** = inputs + typed steps (`trigger, agent, tool, condition, approval, transform, output, delay, loop, subworkflow`) + connections, stored as one versioned graph. As built (Phase 8, `app/workflows/`): a step runs when everything before it has settled and at least one incoming connection is active (condition and approval outcomes choose connections; skipping flows on); up to 3 steps run in parallel; the first failure stops the run unless the step may fail. Expressions and `{{ … }}` templates use a whitelisted AST evaluator over plain data (key lookups only, no attribute access, size caps, no `eval`). Agent steps run through the AgentRunner and tool steps through the ToolExecutor (under a per-workflow identity with exactly that one tool), so workflows cannot bypass permissions, approvals or the sandbox. Values from other steps reach agents only as fenced data, and tool steps whose arguments use them are tainted. Runs are supervised asyncio tasks; every step change is saved; after a restart agent steps resume from their checkpoints and an interrupted tool step fails (it may or may not have happened) for the person to retry. A decision made while a run is still walking other branches is delivered to the live walk rather than written underneath it.
- **Scheduler** (`app/scheduler/`): dependency-free five-field cron with names, steps and shortcuts, evaluated in the schedule's time zone (DST-safe). It ticks in-process every 30 s, starts runs flagged `unattended` (never auto-approving high-risk actions), collapses missed times into one catch-up run, skips a firing while the previous run is still going, and records every firing or skip as an event with its reason.
- **MCP** (`app/mcp/`, as built in Phase 9): an in-house client (JSON-RPC 2.0, protocol 2025-06-18 with 2025-03-26 and 2024-11-05 accepted) over stdio (child process, own process group, scrubbed environment) and streamable HTTP (session id, SSE or JSON answers, no redirects). `MCPServerManager` starts servers the person added (Settings → Integrations; configuration in `integrations`, secret values in the secret store), discovers tools, resources and prompts (paginated), and registers each tool into the `ToolRegistry` as `mcp__<server>__<tool>` with `source="mcp:<server>"`, the server's risk level (HIGH by default), `Capability.MCP` (never in private runs) and untrusted results. Arguments are validated with a small JSON Schema checker behind a per-tool pydantic model, so the executor treats MCP tools like any other. Definitions are cleaned, scanned and fingerprinted into the `tools` table: a suspicious or changed tool is switched off until the person reviews it. `list_changed` notifications refresh the tools; a server that exits is reported and its tools withdrawn (no silent restart). Enabled servers start with the app, awaited briefly so resumed runs find their tools.

## 11. Extension points for the P2 list

| Future capability | Seam that already exists |
|---|---|
| Custom tools / plugin SDK / skills | `ToolRegistry.register(source=…)`; skill packages register tools, prompts, and agent presets under a namespaced source |
| Browser / computer-use agent | Tools whose handler is an executor behind a `ComputerActionProposal → PolicyEngine`; policy has `risk`+`taint` inputs already; UI approval card already shows arguments and impact |
| Remote execution nodes / remote workers | `JobQueue` interface (in-process today; Redis/Celery later) and `ExecutionRuntime` interface (local subprocess today; Docker/remote later) |
| Postgres / pgvector / Qdrant | SQLAlchemy models use portable types; `VectorStore` interface; repositories isolate SQL |
| Multi-user, RBAC, teams, cloud sync | Every row carries `project_id`; actor field on events and approvals; auth layer is a single dependency (`current_actor`) |
| Voice, mobile, notifications channels | `NotificationSink` interface (in-app today; push/email/Telegram/Slack later) |
| Marketplaces | Agent, workflow and skill definitions are plain, versioned JSON documents |

## 12. Key decisions (short ADRs)

- **One Python service, strict internal boundaries.** Simplicity now, split later.
- **Custom provider adapters over LiteLLM.** Fewer dependencies, exact control over structured output and usage accounting, easier to audit for secret leakage.
- **Structured-step protocol over native tool-calling APIs.** Works identically across all providers; each provider still uses its own native structured-output feature underneath.
- **SQLite (WAL) + JSON columns + SQLAlchemy 2.0 async + Alembic.** Portable to Postgres. Embeddings stored as float arrays in a table behind `VectorStore`; the default embedder is a local hashing embedder (no downloads, deterministic), replaceable by provider/Ollama embeddings.
- **In-process asyncio JobQueue and EventBus** behind interfaces.
- **Bearer token on every API call, loopback bind, Host-header and Origin checks** (defends against DNS rebinding and drive-by requests from web pages to the local API).
- **Tailwind CSS v4 + CSS-variable semantic tokens** so light mode is a token swap.
