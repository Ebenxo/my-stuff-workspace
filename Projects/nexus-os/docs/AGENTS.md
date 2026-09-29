# NEXUS OS — agents

## AgentDefinition

```python
class AgentDefinition(BaseModel):
    id: str; slug: str                  # slug is stable ("planner"), id is opaque
    name: str                           # team-member name ("Compass")
    role: str                           # "Planning"
    description: str
    system_prompt: str
    preferred_model: str | None         # "provider_id:model"; None = router decides
    fallback_models: list[str]
    tools: list[str]                    # allow-list of tool names (exact names or "prefix*" patterns, e.g. "mcp__github__*")
    permissions: AgentPermissions       # max_risk, path scopes, may_request_approval
    memory_scope: MemoryScope           # which scopes it may read / propose to
    max_steps: int; max_runtime_s: int; max_tool_calls: int; token_budget: int
    temperature: float
    reasoning_mode: Literal["off","light","deep"]   # provider thinking budget only; output discarded
    status: Literal["idle","busy","disabled"]
    builtin: bool
```

An agent can only call tools that are both on its allow-list **and** permitted by the policy engine for the project. `permissions.max_risk` caps what it may even *request*: a Critic with `max_risk=SAFE` cannot propose a write, so a prompt-injected Critic cannot be talked into one.

## Built-in team

Defined in code (`app/agents/builtin.py`), synced to the `agents` table at every startup, ids `agent_builtin_<slug>`. "Read" = `list_directory`, `read_file`, `search_files`. Memory tools (`search_memory`, `remember`) join the allow-lists in Phase 7.

| Slug | Name | Tools (allow-list) | Max risk | Limits (steps / tool calls) | Notes |
|---|---|---|---|---|---|
| `orchestrator` | Orchestrator | Read | SAFE | 12 / 40 | Coordinates; its delegation/recovery decisions are deterministic code in `orchestration/` (Phase 5), with the model consulted for merge/summary and ambiguous cases. Does not do specialist work |
| `planner` | Planner | Read | SAFE | 10 / 40 | Emits `PlanResult` (DAG) |
| `researcher` | Researcher | Read, `web_search`, `http_request`, `create_document`, `create_markdown`, `calculator`, `datetime` | MODERATE | 25 / 40 | Every claim carries a source; separates fact from inference; flags contradictions. Non-GET `http_request` is HIGH, so beyond its ceiling |
| `coder` | Coder | Read, `write_file`, `create_directory`, `move_file`, `run_python`, `run_command`, `git_status`, `git_diff`, `git_log`, `create_document`, `create_markdown` | HIGH | 30 / 60, 600 s | Reads repository context first; runs what it writes. `run_command` always asks |
| `data_analyst` | Data Analyst | Read, `parse_csv`, `parse_json`, `calculator`, `datetime`, `database_query`, `run_python`, `write_file`, `create_document`, `create_markdown` | MODERATE | 25 / 40 | Computes with tools, never estimates numbers |
| `writer` | Writer | Read, `write_file`, `create_document`, `create_markdown` | MODERATE | 15 / 40 | |
| `designer` | Designer | Read, `write_file`, `create_document`, `create_markdown` | MODERATE | 15 / 40 | Self-contained HTML/CSS or SVG; contrast and 390 px checks in its brief |
| `file_manager` | File Manager | Read, `write_file`, `create_directory`, `move_file`, `delete_file` | HIGH | 25 / 40 | `delete_file` always asks, even under the permissive level |
| `critic` | Critic | Read | SAFE | 12 / 40 | Reviews another agent's output; cannot modify anything |
| `verifier` | Verifier | Read, `parse_csv`, `parse_json`, `calculator`, `datetime`, `database_query`, `git_status`, `git_diff`, `git_log` | SAFE | 15 / 40 | Returns `PASS`/`PARTIAL`/`FAIL`; read-only checks only |

Invariants enforced by tests (`tests/test_agent_definitions.py`): every allow-list entry names a registered tool; no agent is given a tool its own ceiling would always refuse; planning and reviewing agents are SAFE-only and cannot write memory; only the Coder and File Manager reach HIGH; no built-in reaches VERY_HIGH; no prompt asks for step-by-step reasoning.

Custom agents are created from the same schema (Agents → New agent) and default to MODERATE. On a **built-in**, a person may change only the tuning fields (`BUILTIN_OVERRIDABLE`: models, limits, temperature, tools, permissions, status); its role, name and instructions stay as shipped, and each change is an `AGENT_UPDATED` event. Overrides survive the startup refresh of the built-ins.

## The agent loop (built, Phase 3)

`AgentRunner` (`app/agents/runner.py`) runs one agent on one task:

1. Build the prompt: the agent's role prompt + the shared step protocol + `UNTRUSTED_RULES` + the tool catalogue (only tools it can actually use) as the system prompt; the task as the first user message; any context blocks fenced as untrusted data.
2. Ask the gateway for one `AgentStep` (structured output with bounded repair). Only the public `summary` is kept; providers discard thinking.
3. Persist the proposed step **before** acting (checkpoint), emit `AGENT_STEP`.
4. `tool_call` → `ToolExecutor` (allow-list, private-run check, validation, risk, policy, approval wait, sandbox, redaction, taint, injection scan). The result goes back fenced as untrusted, with a security notice when instruction-like text was found. `finish` → reconcile artifacts (only ones this run created) and end. `ask_human` → park as `WAITING_INPUT`.
5. Guards after every step: step cap (last-step warning), tool-call cap (one refusal, then stop), token budget (warning at 85 %), working-time limit (time waiting for a person is excluded), and loop detection (identical call nudged at 3 repeats, stopped at 5).

Endings map to run statuses and failure categories: `COMPLETED`; `FAILED` (`step_limit`, `tool_call_limit`, `token_budget`, `loop_detected`, `agent_reported_failure`, model errors with the gateway's category); `TIMED_OUT`; `CANCELLED` (open approvals cancelled, in-flight tool call closed); `WAITING_INPUT`; `INTERRUPTED` (app stopped or restarted; resumable).

**Recovery.** At startup every open run is marked `INTERRUPTED`, its approvals cancelled and its in-flight tool calls closed. Resuming reloads the checkpoint; an action that was in flight when the process died is **never silently re-run**: the agent is told it may or may not have happened and to check first. The run's taint set is rebuilt from the checkpoint, so a resumed run keeps its "has read untrusted content" status. Only one API may use a data folder at a time (`InstanceLock`), so recovery can never interrupt another live instance's runs.

## Structured contracts

All inter-agent and agent↔orchestrator data is a Pydantic model; free text appears only inside declared string fields.

```python
class PlanTask(BaseModel):
    key: str                            # "t1"
    title: str; description: str
    agent: str                          # slug
    depends_on: list[str]               # keys
    tools: list[str]                    # expected tools (validated against the agent's allow-list)
    expected_outputs: list[str]
    approval_required: bool = False
    optional: bool = False
    review: bool = False                # send output to the Critic
    complexity: Literal["trivial","small","medium","large"]

class PlanResult(BaseModel):
    objective: str
    assumptions: list[str]; constraints: list[str]
    tasks: list[PlanTask]
    risks: list[str]
    required_approvals: list[str]
    completion_criteria: list[str]
    complexity: Literal["trivial","small","medium","large"]

class TaskResult(BaseModel):
    status: Literal["completed","partial","failed","needs_input"]
    summary: str
    outputs: list[OutputRef]            # text / data / artifact references
    artifacts: list[ArtifactRef]
    errors: list[str]
    recommendations: list[str]

class ReviewResult(BaseModel):
    verdict: Literal["approve","revise"]
    issues: list[ReviewIssue]           # severity blocker|major|minor|nit, category, location, suggestion
    checks: dict[str, bool]             # correctness, completeness, consistency, assumptions, requirements, security, formatting, quality

class VerificationResult(BaseModel):
    verdict: Literal["PASS","PARTIAL","FAIL"]
    reasoning: str
    criteria: list[CriterionCheck]      # criterion, met, evidence
    missing_requirements: list[str]
```

## AgentMessage

```python
class AgentMessage(BaseModel):
    id: str; sender: str; recipient: str; task_id: str | None
    type: Literal["TASK_REQUEST","TASK_RESULT","QUESTION","ERROR","STATUS",
                  "REVIEW_REQUEST","REVIEW_RESULT","APPROVAL_REQUIRED"]
    payload: dict            # validated against the model that matches `type`
    timestamp: datetime
```

Messages are persisted as events (`AGENT_MESSAGE`), so the Activity panel can render the collaboration ("Compass → Nexus: PLAN, 6 tasks").

## Task graph

`TaskNode` = the `tasks` row: `id, title, description, assigned_agent, status, dependencies, inputs, outputs, attempts, max_attempts, started_at, completed_at, error, approval_required`. Statuses: `QUEUED, PLANNING, WAITING, RUNNING, BLOCKED, NEEDS_APPROVAL, FAILED, COMPLETED, CANCELLED`. `TaskGraph` (in `orchestration/graph.py`) is a pure in-memory structure with topological ordering, ready-set computation, cycle detection, and downstream-cancel propagation, used by both the validator and the executor.

## Review loop

```
work task ──(review=true)──► Critic REVIEW_REQUEST ──► REVIEW_RESULT
      ▲                                                   │ blocker/major issues and revisions < limit
      └────────────── "Revise: …" task (original agent) ◄─┘
```

A revision is a real task in the graph, depending on the review task, assigned to the original agent, carrying the issues as input. Revision limit default: 2 per task. When it is exhausted with blocking issues open, the task completes as `partial` and the Verifier sees the open issues.

## Verification and replanning

After all tasks settle, the Verifier receives the completion criteria, task summaries, and artifact references (never trusting agents' self-reports: it must read the artifacts). `PASS` → finalise. `PARTIAL`/`FAIL` with `missing_requirements` and replan budget (default 1) → Orchestrator asks the Planner for follow-up tasks covering only the missing requirements. Otherwise the objective ends `PARTIAL` or `FAILED` with an honest report.

## Failure handling

Categories: `MODEL_FAILURE, TOOL_FAILURE, PERMISSION_DENIED, INVALID_OUTPUT, TIMEOUT, DEPENDENCY_FAILURE, CONTEXT_FAILURE, UNKNOWN`.

| Category | Default recovery (in order) |
|---|---|
| `MODEL_FAILURE` | retry with backoff → next fallback model → request human help |
| `INVALID_OUTPUT` | repair prompt (bounded) → different model → retry task → request human help |
| `TOOL_FAILURE` | retry if transient → alternative tool from the agent's allow-list (declared per tool, e.g. `web_search` → `http_request`) → delegate to a more capable agent → skip if `optional` → request human help |
| `PERMISSION_DENIED` | never retried automatically; the agent is told and may choose an approved alternative once; otherwise task `BLOCKED` and the human is asked |
| `TIMEOUT` | resume from checkpoint once → split/delegate → request human help |
| `DEPENDENCY_FAILURE` | mark `BLOCKED`; if the upstream is `optional`-skipped, unblock with a missing-input note; else cancel downstream |
| `CONTEXT_FAILURE` | rebuild with a smaller budget / drop lowest-ranked segments → retry |
| `UNKNOWN` | one retry → request human help |

Recovery decisions are deterministic code (`orchestration/recovery.py`), unit-tested per row, and each decision is recorded as an event with the reason.

## Strategies

Implemented: `single_agent`, `pipeline`, `reviewer`, `parallel`. Defined but explicitly unsupported (raise `NotImplementedError` with a clear message if selected by a plan): `supervisor`, `debate`, `map_reduce`, `swarm`. `StrategyEstimator` chooses the cheapest that satisfies the plan's shape and the user's cost limits; the rationale is stored on the objective and shown in the plan preview.

## Human-in-the-loop triggers

An agent step of type `ask_human` (ambiguous requirement, conflicting information, architectural decision), an approval request (dangerous, destructive or external action), or a recovery decision that needs the user, all park the task (`BLOCKED` or `NEEDS_APPROVAL`) and create a notification. The user answers from the approvals/questions panel; the answer is delivered to the parked run as a trusted user message.
