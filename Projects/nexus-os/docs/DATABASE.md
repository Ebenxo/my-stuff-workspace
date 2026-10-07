# NEXUS OS — database design

Engine: SQLite (WAL, `foreign_keys=ON`) via SQLAlchemy 2.0 async (`aiosqlite`). Migrations: Alembic, run automatically at startup (`nexus migrate`) and by tests against a fresh database. The schema uses only portable types so a PostgreSQL move is a driver and migration-dialect change, not a redesign.

## Conventions

- **IDs**: prefixed, time-sortable, opaque strings (`proj_…`, `obj_…`, `task_…`, `run_…`, `tc_…`, `appr_…`, `art_…`, `mem_…`, `wf_…`). Generated in `core/ids.py`. The prefix makes logs and the audit trail self-describing.
- **Timestamps**: timezone-aware UTC, stored as ISO-8601 text via a custom `UTCDateTime` type (SQLite has no tz type; the type round-trips tz-aware values).
- **JSON**: SQLAlchemy `JSON` columns (JSONB on Postgres later) for schema-flexible payloads that are validated by Pydantic at the service boundary. Never query on JSON internals in hot paths.
- **Foreign keys**: enforced *within* an aggregate (message→conversation, task→objective, dependency→task, node→workflow, version→artifact). *Across* aggregates the runtime tables carry indexed **soft references** (`project_id`, `objective_id`, `task_id`, `agent_id`), so audit, usage and event rows survive deletion of what they describe. Cascades across aggregates are explicit service code.
- **No secrets in the database.** Provider and integration rows hold a `secret_ref` (a name in the secret store), never a key.
- **Redaction before persistence.** `ToolCall.arguments/result`, `Event.payload` and `Approval.arguments` pass through `core.security.redact()` (known key patterns, `Authorization` headers, private-key blocks) before being written.

## Tables

### Foundation — migration `0001_foundation`

| Table | Columns (key ones) | Notes |
|---|---|---|
| `user_settings` | `id` (=1), `display_name`, `workspace_root`, `default_permission_level` (`cautious`/`balanced`/`permissive`), `onboarding_completed`, `preferences` JSON, `routing_rules` JSON, `budgets` JSON, `search_backend` JSON, `updated_at` | Single row. Typed columns for what the runtime reads on hot paths |
| `projects` | `id`, `name`, `slug` (unique), `description`, `icon`, `root_rel_path`, `settings` JSON, `status` (`active`/`archived`), `is_demo`, `created_at`, `updated_at` | Workspace root = `workspace_root/projects/<id>/` |
| `conversations` | `id`, `project_id` FK, `title`, `created_at`, `updated_at` | |
| `messages` | `id`, `conversation_id` FK, `role` (`user`/`assistant`/`agent`/`system`), `agent_id`, `content`, `meta` JSON (attachments, objective ref), `created_at` | |
| `providers` (ProviderConfiguration) | `id`, `kind` (`anthropic`/`openai`/`gemini`/`ollama`/`lmstudio`/`openai_compatible`/`demo`), `name`, `base_url`, `default_model`, `enabled`, `options` JSON (model overrides, price overrides), `secret_ref`, `last_test_at`, `last_test_ok`, `last_test_error`, timestamps | Key lives in the secret store under `secret_ref` |
| `usage_records` | `id`, `provider_id`, `model`, `agent_id`, `project_id`, `objective_id`, `workflow_id`, `run_id`, `purpose`, `input_tokens`, `output_tokens`, `cost_usd` (nullable), `cost_known`, `latency_ms`, `created_at` | `cost_usd` NULL = price unknown, never 0 by guess |
| `events` | `seq` (autoincrement PK), `id`, `ts`, `type`, `project_id`, `objective_id`, `task_id`, `run_id`, `agent_id`, `actor` (`user`/`system`/agent id), `payload` JSON, `prev_hash`, `hash` | Append-only. Hash = SHA-256 over `prev_hash ‖ canonical(event)`, chained per `project_id` (NULL project = global chain). `GET /api/events/verify` recomputes the chain |
| `notifications` | `id`, `kind`, `title`, `body`, `project_id`, `ref` JSON, `read_at`, `created_at` | |

### Agent runtime — migration `0002_agent_runtime`

| Table | Columns | Notes |
|---|---|---|
| `agents` | `id`, `slug` (unique), `name`, `role`, `description`, `icon`, `color`, `system_prompt`, `preferred_model`, `fallback_models` JSON, `tools` JSON (allow-list), `permissions` JSON (`max_risk`, path scopes), `memory_scope` JSON, `max_steps`, `max_runtime_s`, `max_tool_calls`, `token_budget`, `temperature`, `reasoning_mode`, `status`, `builtin`, `knowledge_sources` JSON, `version`, timestamps | Built-ins are upserted at startup by slug; user edits to a built-in are kept in `overrides` |
| `agent_runs` | `id`, `agent_id`, `project_id`, `objective_id`, `task_id`, `workflow_run_id`, `status` (`RUNNING`/`WAITING_APPROVAL`/`COMPLETED`/`FAILED`/`CANCELLED`/`TIMED_OUT`), `model`, `step_count`, `tool_call_count`, `tokens_in`, `tokens_out`, `attempt`, `result` JSON, `error` JSON (`category`, `message`), `checkpoint` JSON, `started_at`, `finished_at` | `checkpoint` = ordered step records; enough to resume |
| `tools` | `name` (PK), `source` (`builtin`/`mcp:<server>`/`skill:<name>`), `description`, `input_schema` JSON, `output_schema` JSON, `risk_level`, `requires_approval`, `capabilities` JSON, `enabled`, `updated_at` | Mirror of the in-memory registry so the UI can list and toggle tools |
| `tool_calls` | `id`, `run_id`, `task_id`, `project_id`, `tool_name`, `arguments` JSON (redacted), `result` JSON (redacted, size-capped), `status` (`PROPOSED`/`DENIED`/`AWAITING_APPROVAL`/`RUNNING`/`SUCCEEDED`/`FAILED`), `risk_level` (effective), `approval_id`, `provenance` JSON (taint sources), `error` JSON, `duration_ms`, `started_at`, `finished_at` | |
| `approvals` | `id`, `project_id`, `run_id`, `task_id`, `tool_call_id`, `agent_id`, `tool_name`, `arguments` JSON, `edited_arguments` JSON, `reason`, `risk_level`, `impact`, `tainted`, `taint_sources` JSON, `status` (`PENDING`/`APPROVED_ONCE`/`APPROVED_SESSION`/`DENIED`/`EXPIRED`/`CANCELLED`), `decided_by`, `decision_note`, `created_at`, `decided_at` | Source of truth for parked runs |
| `artifacts` | `id`, `project_id`, `objective_id`, `task_id`, `agent_id`, `type` (`document`/`markdown`/`code`/`spreadsheet`/`chart`/`image_ref`/`presentation`/`report`/`json`/`dataset`/`website`), `name`, `path` (relative, current version), `version` (latest int), `meta` JSON, timestamps | Unique `(project_id, path)` |
| `artifact_versions` | `id`, `artifact_id` FK, `version`, `stored_path`, `sha256`, `size`, `created_by`, `note`, `created_at` | Every write keeps the previous content; no silent overwrite |

### Orchestration — migration `0003_orchestration`

| Table | Columns | Notes |
|---|---|---|
| `objectives` | `id`, `project_id`, `conversation_id`, `text`, `status`, `run_mode` (`manual`/`auto_safe`), `strategy`, `plan` JSON (validated `PlanResult`), `attachments` JSON, `result` JSON (final report + verifier verdict), `budget` JSON, `replan_count`, timestamps, `completed_at` | |
| `tasks` | `id`, `objective_id` FK, `project_id`, `key` (plan-local id), `title`, `description`, `kind` (`work`/`review`/`revise`/`verify`/`plan`), `assigned_agent`, `status`, `inputs` JSON, `outputs` JSON, `attempts`, `max_attempts`, `approval_required`, `optional`, `parent_task_id`, `error` JSON, `position` JSON, `started_at`, `completed_at`, `created_at` | |
| `task_dependencies` | `task_id` FK, `depends_on_id` FK (composite PK) | DAG; acyclicity validated in `PlanValidator` and again on insert |

### Memory + search — migration `0004_memory`

| Table | Columns | Notes |
|---|---|---|
| `memory_items` | `id`, `scope` (`working`/`conversation`/`project`/`global`), `project_id`, `conversation_id`, `content`, `summary`, `importance` (0–1), `source` JSON (`kind`, `agent_id`, `task_id`, `origin`), `tags` JSON, `status` (`active`/`pending`/`deleted`), `content_hash`, `access_count`, `created_at`, `last_accessed_at`, `expires_at` | `pending` = awaiting user confirmation (all agent-proposed *global* memory, and anything flagged by the sensitivity guard that the user chose to review) |
| `memory_embeddings` | `item_id` FK, `embedder`, `dim`, `vector` (JSON float array) | Separate table so items can be re-embedded when the embedder changes |
| `search_index` | FTS5 virtual table: `kind`, `ref_id`, `project_id`, `title`, `body` | Falls back to `LIKE` where FTS5 is unavailable |

### Workflows — migration `0005` (built)

| Table | Columns | Notes |
|---|---|---|
| `workflows` | `id`, `project_id`, `name`, `description`, `version`, `enabled`, `definition` JSON (inputs, nodes, edges), `deleted`, timestamps | The graph is stored whole: it is always read and written as one unit. Saving a changed graph bumps `version`; `deleted` keeps run history pointing at it |
| `workflow_versions` | `workflow_id` FK, `version`, `definition` JSON, `created_at` | Every saved graph; a run reads the version it started with |
| `workflow_runs` | `id`, `workflow_id`, `workflow_version`, `project_id`, `status` (`RUNNING`/`WAITING`/`COMPLETED`/`FAILED`/`CANCELLED`), `unattended`, `schedule_id`, `parent_run_id`, `depth`, `inputs` JSON, `outputs` JSON, `node_states` JSON (per step: status, output, error, run_id, child_run_id, approval_id, resume, attempts, times), `error` JSON, `started_at`, `finished_at` | Saved after every step change, so a run can be recovered |
| `schedules` | `id`, `workflow_id`, `cron`, `timezone`, `inputs` JSON, `enabled`, `last_run_at`, `last_run_id`, `last_status`, `next_run_at`, `created_at` | |

(The Phase 0 design split nodes and edges into `workflow_nodes`/`workflow_edges`; one versioned JSON graph proved simpler and atomic.)

### Integrations — migration `0006` (built)

| Table | Columns | Notes |
|---|---|---|
| `integrations` | `id`, `kind` (`mcp` today), `name` (unique per kind), `config` JSON, `enabled`, `last_error`, `last_health` JSON, timestamps | An MCP server's `config` holds the transport (`stdio`/`http`), command, arguments, working folder, plain environment variables and headers, the *names* of its secret variables and headers, its risk level and time limit. Secret values live only in the secret store under `mcp:<id>:env:<name>` / `mcp:<id>:header:<name>`. Whether a server is running is live state, not stored; `last_error` keeps the reason it last failed to start. |
| `tools` (new columns) | `fingerprint`, `note` | For MCP tools: a SHA-256 of the definition as last seen, and why a tool was switched off (changed or suspicious definition). Rows persist while a server is stopped so the person's on/off choices survive; they are removed with the server. |

The plan had `status`, `trust_level` and `secret_ref` columns. As built, status is live state from the running manager, "trust" became the per-server risk level in `config`, and secrets are named per variable instead of one reference.

### Ideas, notes and to-dos — migration `0007` (built, after Phase 10)

| Table | Columns | Notes |
|---|---|---|
| `ideas` | `id`, `project_id` (optional), `kind` (`idea`/`note`/`todo`), `text` (≤ 4000 chars, kept as written), `status` (`open`/`done`), `pinned`, `due_at`, `reminded_at`, `done_at`, `objective_id`, timestamps | The person's own small things, separate from memory (which is what agents know). `due_at` drives the timeline's *Coming up* / *Needs you* and one reminder: the scheduler's tick sends a notification and an `IDEA_DUE` event, then sets `reminded_at`; moving `due_at` clears it so the new time gets its own reminder. `objective_id` is set when the idea is started as an objective (the idea is then done). Indexed on `project_id` and (`status`, `due_at`). In universal search as kind `idea`. Event payloads carry only a redacted first line. |

## Why migrations are split by phase

Each phase ships the tables it needs, so a database created at any phase boundary is valid and the migration history mirrors how the product was built. The aggregate-boundary convention above is what lets earlier tables reference later concepts (`task_id` on `agent_runs`) without a forward foreign key.
