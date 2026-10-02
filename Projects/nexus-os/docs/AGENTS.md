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

Defined in code (`app/agents/builtin.py`), synced to the `agents` table at every startup, ids `agent_builtin_<slug>`. "Read" = `list_directory`, `read_file`, `search_files`. Every agent also has `search_memory`; agents that may write project memory (all except the Orchestrator, Planner, Critic and Verifier) also have `remember`. The ContextBuilder gives each run the relevant memories before it starts (see `docs/MEMORY.md`).

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

Messages are persisted as events (`AGENT_MESSAGE`) and returned with the objective, so the UI can render the collaboration ("NEXUS assigned writer: Write the comparison report", "Critic reviewed: Verdict: revise (1 to fix)"). Payloads carry structured fields and short summaries (title, summary, question, verdict, counts), never reasoning. Built in Phase 5: `TASK_REQUEST`, `TASK_RESULT`, `QUESTION`, `ERROR`, `REVIEW_REQUEST`, `REVIEW_RESULT`.

## Task graph

`TaskNode` = the `tasks` row (plus `task_dependencies`): `id, key, title, description, kind (work | review | revise | verify), assigned_agent, status, depends_on, inputs, outputs, attempts, max_attempts, approval_required, optional, review, round, parent_task_id, run_id, error, started_at, completed_at`. Statuses: `WAITING, QUEUED, RUNNING, NEEDS_APPROVAL, BLOCKED, COMPLETED, SKIPPED, FAILED, CANCELLED`. `TaskGraph` (in `orchestration/graph.py`) is pure: topological ordering, ready set, cycle detection and downstream cancellation, used by the validator, the orchestrator and (mirrored in TypeScript) the plan editor. A `SKIPPED` dependency counts as settled; the dependent is told the input is missing.

## Review loop

```
work task ──(review=true)──► Critic REVIEW_REQUEST ──► REVIEW_RESULT
      ▲                                                   │ blocker/major issues and rounds < 2
      └────────────── "Revise: …" task (original agent) ◄─┘
```

A review and a revision are real tasks in the graph (`t2-review1`, `t2-rev1`, `t2-review2`, …) with their own runs. The revision depends on the review, goes to the original agent with the issues and the previous output as input, and is reviewed again while rounds remain. Tasks that depended on the original are rewired to the latest revision. When the limit (2) is reached with blocking issues open, the last review is marked `open_issues` and the Verifier sees it.

## Verification and replanning

After all tasks settle, the Verifier receives the completion criteria, task summaries and artifact references, and must read the deliverables itself (never trusting agents' self-reports). It returns a `VerificationResult`: `PASS | PARTIAL | FAIL`, each criterion with `met` and evidence, and `missing_requirements`. `PASS` completes the objective. `PARTIAL`/`FAIL` with missing requirements and replan budget left (1) → the Planner is asked for at most 4 follow-up tasks covering only what is missing, validated like any plan, then verified again. Otherwise the objective ends `PARTIAL` or `FAILED` with the Verifier's honest report.

## Failure handling

Categories: `MODEL_FAILURE, TOOL_FAILURE, PERMISSION_DENIED, INVALID_OUTPUT, TIMEOUT, DEPENDENCY_FAILURE, CONTEXT_FAILURE, UNKNOWN`. Within a run, the gateway already retries model calls with backoff and tries fallback models, and structured output gets bounded repair. When a run still fails, `orchestration/recovery.py` decides (pure, unit-tested per row):

| Failure | Decision |
|---|---|
| `PERMISSION_DENIED` | never retried: skip if optional, else block for the person |
| the agent reports it cannot do the task | skip if optional, else block |
| step, tool-call, token or working-time limit; interrupted | resume from the checkpoint with a fresh allowance while attempts remain; then skip/block |
| loop detected | retry fresh while attempts remain; then skip/block |
| model failure or invalid output that no retry can fix (budget stop, no route, refusal, bad key or model, bad request) | skip/block at once |
| other model failure, invalid output, tool failure, unknown | retry while attempts remain (default 2); then skip/block |

A blocked task shows the reason and offers **Retry** and **Skip** (or an answer box for a question); the objective pauses only when nothing else can run. Each decision is recorded as a `RECOVERY_DECISION` event with its reason. Not built yet: switching model or tool, or delegating to another agent, as a recovery step.

## Strategies

Implemented: `single_agent`, `pipeline`, `reviewer`, `parallel`, chosen by `orchestration/strategy.py` from the validated plan's shape (task count, distinct agents, dependency depth, width, reviews) with a rationale and a token estimate, shown in the plan preview. Not built: `supervisor`, `debate`, `map_reduce`, `swarm`.

## Human-in-the-loop triggers

An agent step of type `ask_human` (ambiguous requirement, conflicting information, architectural decision), an approval request (dangerous, destructive or external action), or a recovery decision that needs the user, all park the task (`BLOCKED` or `NEEDS_APPROVAL`) and create a notification. The user answers on the objective page (or approves from the approvals panel); the answer is delivered to the parked run as a trusted user message and the run continues from its checkpoint.
