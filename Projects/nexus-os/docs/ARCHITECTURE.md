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
| `tools` | ToolDefinition, registry, built-in tools, sandbox manager, MCP bridge | `permissions`, `files`, `events`, `core` |
| `memory` | MemoryItem service, embedder, vector store, retrieval, context builder | `repositories`, `providers`, `events`, `core` |
| `agents` | AgentDefinition, built-in agents and prompts, AgentRunner (the loop) | `tools`, `permissions`, `memory`, `providers`, `events` |
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
User submits objective (+ attachments, run mode)
  → OBJECTIVE_CREATED                                  status RECEIVED
  → Planner agent run (read-only tools)                status PLANNING
       output: PlanResult (structured, schema-validated)
  → PlanValidator: DAG acyclic, agents exist, tools permitted per agent,
       task cap, complexity/strategy estimate          PLAN_CREATED
  → Tasks + TaskDependency rows created                TASK_CREATED (status WAITING/QUEUED)
  → run_mode == manual → AWAITING_PLAN_APPROVAL  (Run Plan / Edit Plan / Cancel / Auto Run Safe Steps)
    run_mode == auto_safe → proceed (tool approvals still apply)
  → Executor loop                                      status RUNNING
       ready tasks (all deps COMPLETED) dispatched to the JobQueue, bounded concurrency
       each task = one AgentRun (loop in §6)
       TaskResult → outputs stored, artifacts versioned
       review-marked tasks → Critic REVIEW_REQUEST → REVIEW_RESULT
            blocking issues + revision budget left → "Revise" task inserted (visible in graph)
       failure → FailureClassifier → RecoveryPlanner → retry | change model | change tool |
                 delegate | ask human | skip (optional tasks only) | abort
  → Verifier agent run against completion criteria     PASS | PARTIAL | FAIL
       FAIL/PARTIAL with replan budget → follow-up tasks; else finalise
  → Memory proposals (visible, sensitive-data filtered) MEMORY_CREATED
  → OBJECTIVE_COMPLETED | PARTIAL | FAILED             final report + artifact list
```

Task statuses and meaning: `WAITING` dependencies unmet · `QUEUED` ready and in the job queue · `PLANNING` being (re)decomposed · `RUNNING` · `NEEDS_APPROVAL` parked on an approval · `BLOCKED` needs human input or an upstream failure · `COMPLETED` · `FAILED` · `CANCELLED`.

Objective statuses: `RECEIVED, PLANNING, AWAITING_PLAN_APPROVAL, RUNNING, PAUSED, COMPLETED, PARTIAL, FAILED, CANCELLED`.

### Strategy selection ("cheapest effective")

Before dispatching, the Orchestrator's `StrategyEstimator` scores the validated plan: task count, distinct specialisations required, dependency depth, parallel width, estimated tokens/cost. It picks the cheapest strategy that fits: `single_agent` (one specialist, no review), `pipeline` (sequential handoff), `reviewer` (produce → critique → revise), `parallel` (independent branches). `supervisor`, `debate`, `map_reduce` and `swarm` are defined as enum values and documented but rejected as not-yet-implemented. A trivial objective is never fanned out across many agents.

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

## 8. Real-time model

All state changes go through `EventBus.emit(event)`, which (1) persists to the `events` table with a per-project hash chain, then (2) fans out in-process. `GET /api/events/stream` is an SSE endpoint that replays from `Last-Event-ID` (event sequence number) and then tails live events, so the UI can reconnect without gaps. The UI uses a fetch-based SSE reader (so it can send the bearer header) and applies events to TanStack Query caches and Zustand stores.

## 9. Providers and routing

`LLMProvider` (abstract): `generate`, `stream`, `generate_structured`, `count_tokens`, `available_models`. Adapters: Anthropic, OpenAI-compatible (covers OpenAI, LM Studio, vLLM, custom), Ollama (native), Gemini. A scripted `DemoProvider` exists for the demo and tests only and is labelled as such everywhere it appears.

`ModelRouter` picks `[primary, *fallbacks]` for a call from: the agent's `preferred_model`/`fallback_models`; user routing rules (task class → model, privacy: private → local only, context size → long-context model); model profiles (capabilities, context length, cost, latency); and a manual override on the run. Usage (tokens, estimated cost, agent, project, workflow) is recorded per call; budgets are checked before calls and can warn or block.

## 10. Workflows, scheduler, MCP

- **Workflow** = trigger + typed nodes (`trigger, agent, tool, condition, approval, transform, output, delay, loop, subworkflow`) + edges. The engine walks the graph, evaluating conditions with a whitelist-AST expression evaluator (no `eval`). Agent and tool nodes go through the same pipeline as everything else, so workflows can't bypass permissions.
- **Scheduler** persists `Schedule(workflow_id, cron, timezone, enabled, last_run, next_run)`, ticks in-process, and starts workflow runs flagged `unattended=true` (see BRIEF §3.6).
- **MCP**: `MCPServerManager` manages stdio servers (add/remove/start/stop/health), discovers tools/resources/prompts via the official MCP SDK, and registers discovered tools into the `ToolRegistry` with `source="mcp:<server>"`. MCP tools default to HIGH risk and untrusted results; per-server trust can be relaxed by the user.

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
