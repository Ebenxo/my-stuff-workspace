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

| Slug | Team name | Role | Tools (allow-list) | Max risk | Notes |
|---|---|---|---|---|---|
| `orchestrator` | Nexus | Orchestration | `search_memory`, `list_directory`, `read_file`, `datetime` | SAFE | Coordinates; its delegation/recovery decisions are made by deterministic code in `orchestration/` with the model consulted only for merge/summary and ambiguous cases. Does not do specialist work |
| `planner` | Compass | Planning | `list_directory`, `read_file`, `search_files`, `search_memory`, `datetime` | SAFE | Emits `PlanResult` (DAG) |
| `researcher` | Atlas | Research | `list_directory`, `read_file`, `search_files`, `web_search`, `http_request` (GET), `search_memory`, `parse_json`, `parse_csv`, `create_markdown` | MODERATE | Every claim carries a source; separates fact from assumption; flags contradictions |
| `coder` | Forge | Engineering | `list_directory`, `read_file`, `search_files`, `write_file`, `create_directory`, `move_file`, `run_python`, `run_command`, `git_status`, `git_diff`, `git_log`, `search_memory`, `create_document` | HIGH | Reads repository context first; runs tests before finishing |
| `analyst` | Cipher | Data | `read_file`, `parse_csv`, `parse_json`, `database_query`, `calculator`, `run_python`, `create_document` | MODERATE | |
| `writer` | Scribe | Writing | `read_file`, `list_directory`, `write_file`, `create_document`, `create_markdown`, `search_memory` | MODERATE | |
| `designer` | Nova | Design | `read_file`, `list_directory`, `write_file`, `create_document`, `create_markdown` | MODERATE | Specs, wireframe definitions, critiques |
| `file_manager` | Archive | Files | `list_directory`, `search_files`, `read_file`, `write_file`, `create_directory`, `move_file`, `delete_file` | HIGH | `delete_file` always requires approval, even under the permissive policy |
| `critic` | Sentinel | Quality | `read_file`, `list_directory`, `parse_json`, `parse_csv` | SAFE | Reviews another agent's output; cannot modify anything |
| `verifier` | Warden | Verification | `read_file`, `list_directory`, `parse_json`, `parse_csv` | SAFE | Returns `PASS`/`PARTIAL`/`FAIL` |

Custom agents are created from the same schema through the Agent Creator. A custom agent can never be granted more than the project policy allows; a builtin's safety-relevant fields (`max_risk`, tool allow-list expansion) can be edited only by the user and the edit is an audited event.

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
