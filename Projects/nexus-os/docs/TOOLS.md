# NEXUS OS — tools

## ToolDefinition

```python
class ToolDefinition:
    name: str                       # snake_case; MCP tools: "mcp__<server>__<tool>"
    description: str                # shown to the model and the user
    input_schema: type[BaseModel]   # validated before policy evaluation
    output_schema: type[BaseModel] | None
    risk_level: RiskLevel           # static floor: SAFE | MODERATE | HIGH | VERY_HIGH
    requires_approval: bool         # static: always ask regardless of policy level
    permissions: set[Capability]    # fs.read, fs.write, fs.delete, proc.exec, net.http, net.search, db.read, memory.write, ui.clipboard …
    handler: Callable[[ToolContext, BaseModel], Awaitable[Any]]
    # extensions
    assess_risk: Callable[[BaseModel], RiskAssessment] | None   # dynamic escalation / denial from arguments
    returns_untrusted: bool         # result is external content (taints the run)
    alternatives: list[str]         # tools the recovery planner may try on TOOL_FAILURE
    timeout_s: float; max_output_chars: int
    source: str                     # "builtin" | "mcp:<server>" | "skill:<name>"
```

`ToolContext` gives a handler exactly what it may use and nothing else: the project's `WorkspaceFS` (path-guarded), `SandboxManager`, an SSRF-guarded HTTP client, `ArtifactStore`, `MemoryService` façade, the event emitter, and run/task identity. Handlers never receive the database session, the secret store, or the process environment.

## Effective risk

`effective = max(static risk_level, assess_risk(args).level)`. `assess_risk` may also return `DENY` (never executable, e.g. a path outside the workspace, a `run_command` that matches the hard denylist). Denials are recorded as `ToolCall(status=DENIED)` and returned to the agent as `PERMISSION_DENIED` so it can pick another route.

## Built-in tools

| Tool | Static risk | Always asks | What it does | Key controls |
|---|---|---|---|---|
| `list_directory` | SAFE | | List entries in a workspace directory | path guard |
| `read_file` | SAFE | | Read a text file (size-capped, binary refused) | path guard; result **untrusted** |
| `search_files` | SAFE | | Keyword/regex search across workspace files | path guard, result caps; result untrusted |
| `write_file` | MODERATE | | Write/overwrite a text file under `files/` or `temp/` | path guard; overwrite keeps the prior content in `.history/`; writes into a git repo's `.git/` refused |
| `create_directory` | MODERATE | | `mkdir -p` inside the workspace | path guard |
| `move_file` | MODERATE → HIGH if it overwrites | | Move/rename inside the workspace | path guard; overwrite escalates |
| `delete_file` | HIGH | **yes** | Soft-delete: moves the file into the project `.trash/` (recoverable), never `unlink` | path guard; approval even under the permissive policy |
| `run_python` | MODERATE → HIGH if the code touches process/network/native APIs (AST scan) | | Run Python in the sandbox with a temp cwd | `SandboxManager` limits (below) |
| `run_command` | HIGH (VERY_HIGH with `network=true`) | **yes, always** (never session-grantable) | Run an executable with an argument list (no shell), or `shell=true` with command text reviewed as a shell command | denylist and shell-launchers-in-argv → DENY before anyone is asked; a working folder outside `files/`/`temp/` or missing → DENY; timeout; env scrubbed; network off unless asked for |
| `git_status` `git_diff` `git_log` | SAFE | | Read-only git inspection of a repo inside the workspace | fixed argument lists; `--no-pager`; no config/hooks execution (`-c core.fsmonitor=false`, `GIT_CONFIG_NOSYSTEM`) |
| `http_request` | MODERATE for GET/HEAD; HIGH for other methods | non-GET | HTTP(S) request | SSRF guard, redirect re-validation, size/time caps, optional domain allow-list; result untrusted |
| `web_search` | MODERATE | | Search via a configured backend (SearXNG, Brave); no backend configured → clear `TOOL_FAILURE` | query leaves the machine (shown in the approval/activity); result untrusted |
| `database_query` | SAFE | | Read-only SQL against a SQLite file **inside the project workspace** | read-only connection plus an authorizer that allows only SELECT/READ/FUNCTION/RECURSIVE (no `ATTACH`, `PRAGMA`, writes, extensions); progress-handler time limit (stops runaway recursive queries); row cap; NEXUS's own DB is outside the workspace and unreachable |
| `create_document` | MODERATE | | Create/version an artifact of any type (`report`, `json`, `dataset`, `website`, …) | goes through `ArtifactStore`; names sanitised; versioned |
| `create_markdown` | MODERATE | | Create/version a Markdown artifact | same |
| `parse_csv` | SAFE | | Column names, inferred types, row count, sample, basic statistics | stdlib only; row cap |
| `parse_json` | SAFE | | Parse/validate a JSON file or string, optional JSON-pointer | size cap |
| `calculator` | SAFE | | Arithmetic via a whitelist-AST evaluator | no names, no calls except a math whitelist |
| `datetime` | SAFE | | Current time/zone conversions | |
| `search_memory` *(Phase 7)* | SAFE | | Semantic + keyword recall from project/global memory | scope-limited by the agent's `memory_scope`; results labelled DATA |
| `remember` *(Phase 7)* | MODERATE | | Propose a memory item | passes the sensitivity guard; visible in the Memory browser; global scope lands as `pending` |
| `clipboard_write` | MODERATE | | Ask the UI to offer a "copy" action | UI-mediated: a toast with a Copy button; nothing is copied without the person's click; there is intentionally **no** `clipboard_read` |

22 tools are built and registered today (everything above except the two Phase 7 memory tools).

**Private runs.** A run started with "Keep on this device" only uses local models (router), and tools that can send data off the machine (`Capability.NET_HTTP`, `NET_SEARCH`, `MCP`: `http_request`, `web_search`, every MCP tool) are neither shown to the model nor executable (`ToolExecutor` refuses them with `private_run`). `run_command` with `network=true` is refused in a private run.

Deliberately not built-in yet (registered later through the same interface): Gmail, Drive, Calendar, Notion, Slack, GitHub, Figma, Supabase, browser automation, Spotify, Telegram, WhatsApp. Anything that sends data to a third party is HIGH and always asks.

## Sandbox (`SandboxManager`)

Interface: `run(spec: SandboxSpec) -> SandboxResult` with pluggable backends.

**Backend: local subprocess (built).** Each run gets a fresh temp directory under the project's `temp/`; scrubbed environment (`PATH`, `LANG`, `HOME`=temp dir; nothing inherited — no API keys, no `NEXUS_*`); wall-clock timeout with whole-process-group kill; output capped; on POSIX `RLIMIT_CPU`, `RLIMIT_AS`, `RLIMIT_FSIZE`, `RLIMIT_NPROC` and `RLIMIT_NOFILE`; Python runs with `-I -B` (isolated mode); network isolation through `unshare --net` where the OS permits it. `SandboxResult.enforced` lists exactly which limits were applied on this machine (Windows enforces timeout, env scrubbing and cwd only) and the UI shows it in System Health. **A subprocess sandbox is defence in depth, not a security boundary against hostile code**; the AST scan, approval flow and taint tracking exist because of that.

**Backend: Docker (interface only).** `SandboxSpec` already carries image, mounts and network mode so a `DockerSandbox` can be added without touching tools.

## Registry behaviour

- `ToolRegistry.register(tool)` rejects duplicate names and invalid schemas; unregister removes a source's tools atomically (used when an MCP server stops).
- `allowed_for(agent.tools, disabled=…)` returns the intersection of the agent's allow-list and the tools the user has not switched off (Settings → Tools & approvals), minus outside-reaching tools for private runs. That list is exactly what the model is shown, so it never sees a tool it cannot call; the executor re-checks every call anyway.
- Built-ins are mirrored to the `tools` table at startup so the UI can list them and users can disable individual tools.
- MCP-discovered tools register as `mcp__<server>__<tool>`, default `risk_level=HIGH`, `returns_untrusted=True`; tool annotations from the server (e.g. read-only hints) are treated as *hints shown to the user*, not as permission.

## Tool results

Results are size-capped, redacted for known secret patterns, stored on the `ToolCall`, emitted as `TOOL_COMPLETED`, and returned to the agent wrapped in an **untrusted** fence. A tool with `returns_untrusted=True` also adds its source (URL, file path, MCP server) to the run's **taint set**, which the policy engine and the approval card use (see SECURITY.md §6).
