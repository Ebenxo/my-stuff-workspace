# NEXUS OS — roadmap

**Status (2026-09-29): phases 0–10 are built and verified; see `BUILD_STATE.md` for the evidence and what remains.**

Each phase ends with the same gate: **lint · typecheck · tests · build · run the app · fix · update `BUILD_STATE.md` · commit**. A phase is not finished until its exit criteria hold. Later phases do not start before earlier ones are green.

| Phase | Scope | Exit criteria |
|---|---|---|
| **0 Architecture** | Docs, schemas, boundaries, security model, roadmap, BUILD_STATE | Docs consistent with each other; module boundaries and lifecycle defined |
| **1 Foundation** | pnpm + uv monorepo, FastAPI app factory, settings, SQLite + Alembic (`0001`), auth token + Host/Origin checks + rate limit, EventBus + hash-chained event log + SSE, health API, secret store, project + conversation CRUD, React shell (tokens, layout, dashboard, projects), OpenAPI→TS types, Tauri scaffold | API tests green incl. auth/DNS-rebinding cases; migration up/down test; web builds; dashboard renders real data from the API; SSE reconnect test |
| **2 Providers** | `LLMProvider` interface; Anthropic, OpenAI-compatible (OpenAI, LM Studio, custom), Ollama, Gemini adapters; structured output with repair; model catalog + router; usage + cost + budgets; Providers settings UI with Test Connection | Adapter tests against mock upstreams (request shape, streaming, errors, structured output); router rule tests; usage/budget tests; keys never in responses or logs |
| **3 Single agent** | `AgentDefinition`, `AgentRunner` loop with all guards, checkpointing, `AgentRun`/`ToolCall` persistence, execution log stream, basic memory hook, scripted provider for tests | One agent completes a tool-using task end-to-end; loop-detection, timeout, step-cap, budget, retry and repair tests |
| **4 Tools + permissions** | `ToolRegistry`, filesystem/python/command/git/http/data tools, `WorkspaceFS`, `SandboxManager`, `PolicyEngine`, approvals (once/session/deny/edit), taint tracking, artifact store with versions | Traversal/symlink/SSRF/denylist tests; approval flow tests; artifact versioning; nothing executes without passing the pipeline (test asserts unregistered/bypass paths don't exist) |
| **5 Planner + Orchestrator** | `PlanResult` DAG, validator, `TaskGraph`, executor with bounded concurrency, delegation, run state, retry logic, failure classification + recovery, strategy estimator, plan preview API | Objective → plan → tasks → completion with scripted agents; dependency, cancel, retry, recovery tests |
| **6 Multi-agent** | All built-in agents with prompts; agent messages; review→revise loop; verifier + replanning; Agent Creator | ≥3 distinct agents in one objective; critic-caught issue gets repaired; verifier PASS/PARTIAL/FAIL paths; demo project runs |
| **7 Memory + context** | `MemoryService`, sensitivity guard, embedder + `VectorStore`, retrieval scoring, dedup, compression, `ContextBuilder` + trust fences, Memory browser, universal search | Retrieval ranking tests; dedup; sensitive-data refusal; context budget/trust-fence tests; injection-fence neutralisation test |
| **8 Workflows** | Schemas, expression evaluator, engine (all node types), run history, React Flow editor, scheduler + cron | Workflow re-runs; conditions/approval/loop/subworkflow tests; unattended runs park on approval; schedule tick tests |
| **9 MCP** | `MCPServerManager`, tool/resource/prompt discovery, health, MCP tools → registry with HIGH default, Settings → Integrations → MCP Servers | Tests against an in-repo fixture MCP server; discovered tools pass through the same pipeline |
| **10 Desktop polish** | Command palette, shortcuts, terminal panel, notifications, onboarding, system health, usage dashboard, animations, empty/error states, Playwright E2E, screenshots | E2E: onboarding → project → objective → plan → agents → tool → approval → artifact → verifier → complete; visual check at 1440 and 390 widths; accessibility pass |

## After the MVP (designed for, not built)

Skills packages · browser agent · computer-use agent (`ComputerActionProposal` → policy → executor) · voice · mobile companion · remote execution nodes and workers · Docker sandbox backend · Redis/Celery queue · Postgres/pgvector/Qdrant · multi-user, RBAC, cloud sync · agent/workflow/skill marketplaces · supervisor/debate/map-reduce/swarm strategies · knowledge graph / Graph RAG · proactive background agents · desktop push / email / Telegram / Slack notification sinks · integrations (Gmail, Drive, Calendar, Notion, Slack, GitHub, Figma, Supabase, Spotify, Telegram, WhatsApp).

## Known risks to schedule around

| Risk | Mitigation |
|---|---|
| Live provider behaviour differs from mocks | Adapters are small and isolated; contract tests record exact request shapes; a `nexus providers doctor` command for the user to verify with real keys |
| Structured output quality varies by model | Validate → bounded repair → fallback model; `INVALID_OUTPUT` is a first-class failure category |
| Sandbox limits differ per OS | `SandboxResult.enforced` reports reality; System Health shows it |
| Scope | Phases are independent; every phase leaves the product working |
