"""Workflow validation. Pure: a definition (and what exists) in, a list of plain-language issues out.

A workflow is saved even with issues (so work in progress is never lost) but cannot run until the list
is empty. Checks: one trigger; unique node ids; edges between existing nodes; a graph without cycles in
which every node is reachable from the trigger; branch labels only where they mean something; each
node's configuration; every expression and template parses; agents, tools and sub-workflows exist.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable

from pydantic import ValidationError

from app.schemas.workflows import (
    CONFIG_MODELS,
    AgentNodeConfig,
    LoopNodeConfig,
    ToolNodeConfig,
    ValidationIssue,
    ValidationReport,
    WorkflowDefinition,
    WorkflowNode,
)
from app.workflows.expr import ExpressionError, holes, parse

BRANCHING = frozenset({"condition", "approval"})


def _config_errors(model: type, config: dict[str, object]) -> list[str]:
    try:
        model.model_validate(config)  # type: ignore[attr-defined]
    except ValidationError as exc:
        out = []
        for e in exc.errors():
            where = ".".join(str(p) for p in e["loc"]) or "config"
            out.append(f"{where}: {e['msg']}")
        return out
    return []


def _templates(node: WorkflowNode) -> Iterable[str]:
    c = node.config
    if node.type == "agent" and isinstance(c.get("prompt"), str):
        yield c["prompt"]
    if node.type == "approval" and isinstance(c.get("message"), str):
        yield c["message"]
    if node.type == "tool":
        yield from _strings(c.get("arguments"))
    if node.type == "loop" and isinstance(c.get("body"), dict):
        body = c["body"].get("config") or {}
        if isinstance(body.get("prompt"), str):
            yield body["prompt"]
        yield from _strings(body.get("arguments"))


def _strings(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)


def _expressions(node: WorkflowNode) -> Iterable[str]:
    c = node.config
    if node.type == "condition" and isinstance(c.get("expression"), str):
        yield c["expression"]
    if node.type in ("transform", "output") and isinstance(c.get("values"), dict):
        yield from (v for v in c["values"].values() if isinstance(v, str))
    if node.type == "loop" and isinstance(c.get("items"), str):
        yield c["items"]
    if node.type == "subworkflow" and isinstance(c.get("inputs"), dict):
        yield from (v for v in c["inputs"].values() if isinstance(v, str))


def validate_definition(
    d: WorkflowDefinition,
    *,
    agents: set[str] | None = None,
    tools: set[str] | None = None,
    workflows: set[str] | None = None,
    self_id: str | None = None,
) -> ValidationReport:
    issues: list[ValidationIssue] = []

    def add(message: str, node: str | None = None) -> None:
        issues.append(ValidationIssue(node=node, message=message))

    nodes = {n.id: n for n in d.nodes}
    if len(nodes) != len(d.nodes):
        seen: set[str] = set()
        for n in d.nodes:
            if n.id in seen:
                add(f"The id '{n.id}' is used by more than one step.", n.id)
            seen.add(n.id)
    triggers = [n for n in d.nodes if n.type == "trigger"]
    if len(triggers) != 1:
        add(
            "A workflow needs exactly one start (trigger) step."
            if not triggers
            else "Only one start (trigger) step is allowed."
        )
    names = [i.name for i in d.inputs]
    if len(set(names)) != len(names):
        add("Input names must be unique.")

    out_edges: dict[str, list[str]] = defaultdict(list)
    in_count: dict[str, int] = {k: 0 for k in nodes}
    pairs: set[tuple[str, str, str | None]] = set()
    for e in d.edges:
        if e.source not in nodes or e.target not in nodes:
            add(f"A connection points to a step that does not exist ({e.source} → {e.target}).")
            continue
        if e.source == e.target:
            add("A step cannot connect to itself.", e.source)
            continue
        key = (e.source, e.target, e.branch)
        if key in pairs:
            add(f"{e.source} → {e.target} is connected twice.", e.source)
        pairs.add(key)
        src = nodes[e.source]
        if nodes[e.target].type == "trigger":
            add("Nothing can lead into the start step.", e.target)
        if e.branch is not None and src.type not in BRANCHING:
            add(
                f"Only conditions and approvals have yes/no outcomes; {e.source} is a {src.type} step.",
                e.source,
            )
        if src.type == "condition" and e.branch is None:
            add(f"Say whether {e.source} → {e.target} follows the 'true' or the 'false' outcome.", e.source)
        out_edges[e.source].append(e.target)
        in_count[e.target] += 1

    # Cycles (Kahn): whatever cannot be ordered sits on a cycle.
    order_in = dict(in_count)
    queue = deque(k for k, c in order_in.items() if c == 0)
    ordered = 0
    while queue:
        k = queue.popleft()
        ordered += 1
        for t in out_edges[k]:
            order_in[t] -= 1
            if order_in[t] == 0:
                queue.append(t)
    if ordered < len(nodes):
        stuck = sorted(k for k, c in order_in.items() if c > 0)
        add(f"The steps {', '.join(stuck)} form a loop. Use a loop step to repeat work instead.")

    if len(triggers) == 1:
        reach = {triggers[0].id}
        frontier = [triggers[0].id]
        while frontier:
            for t in out_edges[frontier.pop()]:
                if t not in reach:
                    reach.add(t)
                    frontier.append(t)
        for k in nodes:
            if k not in reach:
                add(f"{k} is not connected to the start, so it would never run.", k)

    for n in d.nodes:
        model = CONFIG_MODELS[n.type]
        if model is not None:
            for msg in _config_errors(model, n.config):
                add(msg, n.id)
        if n.type == "loop":
            try:
                loop = LoopNodeConfig.model_validate(n.config)
                body_model = AgentNodeConfig if loop.body.type == "agent" else ToolNodeConfig
                for msg in _config_errors(body_model, loop.body.config):
                    add(f"body.{msg}", n.id)
            except ValidationError:
                pass  # already reported above
        for template in _templates(n):
            for hole in holes(template):
                try:
                    parse(hole)
                except ExpressionError as exc:
                    add(f"{{{{ {hole} }}}}: {exc}", n.id)
        for expr in _expressions(n):
            try:
                parse(expr)
            except ExpressionError as exc:
                add(f"{expr}: {exc}", n.id)
        agent = _agent_of(n)
        if agents is not None and agent and agent not in agents:
            add(f"There is no available agent called '{agent}'.", n.id)
        tool = _tool_of(n)
        if tools is not None and tool and tool not in tools:
            add(f"There is no enabled tool called '{tool}'.", n.id)
        if n.type == "subworkflow":
            wid = n.config.get("workflow_id")
            if self_id and wid == self_id:
                add("A workflow cannot run itself as a sub-workflow.", n.id)
            elif workflows is not None and isinstance(wid, str) and wid not in workflows:
                add(f"The sub-workflow '{wid}' does not exist in this project.", n.id)

    return ValidationReport(ok=not issues, issues=issues)


def _agent_of(n: WorkflowNode) -> str | None:
    if n.type == "agent":
        v = n.config.get("agent")
        return v if isinstance(v, str) else None
    if (
        n.type == "loop"
        and isinstance(n.config.get("body"), dict)
        and n.config["body"].get("type") == "agent"
    ):
        v = (n.config["body"].get("config") or {}).get("agent")
        return v if isinstance(v, str) else None
    return None


def _tool_of(n: WorkflowNode) -> str | None:
    if n.type == "tool":
        v = n.config.get("tool")
        return v if isinstance(v, str) else None
    if n.type == "loop" and isinstance(n.config.get("body"), dict) and n.config["body"].get("type") == "tool":
        v = (n.config["body"].get("config") or {}).get("tool")
        return v if isinstance(v, str) else None
    return None


def starter_definition() -> WorkflowDefinition:
    """What a new workflow starts with: a start step connected to one agent step and an output."""
    return WorkflowDefinition.model_validate(
        {
            "inputs": [{"name": "topic", "type": "text", "required": True, "description": "What to work on"}],
            "nodes": [
                {
                    "id": "start",
                    "type": "trigger",
                    "label": "Start",
                    "position": {"x": 0, "y": 0},
                },  # flows downwards
                {
                    "id": "draft",
                    "type": "agent",
                    "label": "Draft",
                    "config": {"agent": "writer", "prompt": "Write a short brief about {{ inputs.topic }}."},
                    "position": {"x": 0, "y": 150},
                },
                {
                    "id": "result",
                    "type": "output",
                    "label": "Result",
                    "config": {"values": {"summary": "nodes.draft.output.summary"}},
                    "position": {"x": 0, "y": 300},
                },
            ],
            "edges": [
                {"id": "start-draft", "source": "start", "target": "draft"},
                {"id": "draft-result", "source": "draft", "target": "result"},
            ],
        }
    )
