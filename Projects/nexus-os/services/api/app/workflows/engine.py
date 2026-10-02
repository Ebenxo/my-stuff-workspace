"""WorkflowEngine: walks one workflow run's graph until it finishes, fails, or waits for a person.

Semantics:
- The start step completes at once; its output is the run's inputs.
- A step runs when every step leading into it has settled and at least one of those connections is
  *active*. A connection from a condition follows its 'true'/'false' outcome; from an approval, 'true'
  (or no label) follows approval and 'false' follows rejection. A step none of whose connections is
  active is skipped, and skipping flows on.
- Up to MAX_PARALLEL independent steps run at once. The first failure stops the run (other running
  steps are cancelled) unless the failed step says ``continue_on_error``.
- Agent and tool steps go through the same AgentRunner and ToolExecutor as everything else, so a
  workflow cannot bypass permissions, approvals or the sandbox. Scheduled runs are unattended, which
  never auto-approves high-risk actions: they wait for a person.
- Values from other steps reach an agent only as fenced data (``expr.render_prompt``); a tool step whose
  arguments use other steps' values is treated as tainted.
- Every change of a step's state is saved, so a run can be recovered after a restart.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from app.agents.builtin import task_class_for
from app.agents.prompt import ContextBlock
from app.agents.runner import AgentRunner, RunRequest
from app.core.clock import Clock, SystemClock
from app.core.errors import NexusError
from app.core.risk import RiskLevel
from app.events.bus import EventBus
from app.events.types import EventType
from app.permissions.taint import TaintTracker
from app.repositories.runtime_store import AgentStore, RunStore
from app.repositories.workflow_store import WorkflowRunStore, WorkflowStore
from app.schemas.agents import AgentDefinition, AgentPermissions
from app.schemas.common import PermissionLevel
from app.schemas.runtime import ApprovalOut, RunStatus
from app.schemas.workflows import (
    AgentNodeConfig,
    ApprovalNodeConfig,
    ConditionNodeConfig,
    DelayNodeConfig,
    LoopNodeConfig,
    NodeState,
    SubworkflowNodeConfig,
    ToolNodeConfig,
    ValuesNodeConfig,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowRunOut,
    WorkflowRunStatus,
)
from app.tools.context import ToolContextFactory
from app.tools.executor import ExecContext, ToolExecutor
from app.workflows.expr import (
    ExpressionError,
    evaluate,
    holes,
    render,
    render_prompt,
    render_value,
    root_names,
)

log = logging.getLogger(__name__)

MAX_PARALLEL = 3
SETTLED = frozenset({"COMPLETED", "SKIPPED", "FAILED", "CANCELLED"})
LevelFor = Callable[[str], Awaitable[PermissionLevel]]
NotifyFn = Callable[[str, str, str, dict[str, Any]], Awaitable[Any]]
StartChild = Callable[[WorkflowRunOut, str, dict[str, Any]], Awaitable[WorkflowRunOut]]
Sleep = Callable[[float], Awaitable[None]]


@dataclass
class Result:
    status: str  # COMPLETED | FAILED | WAITING
    output: Any = None
    error: dict[str, Any] | None = None


@dataclass
class _Ctx:
    run: WorkflowRunOut
    name: str
    definition: WorkflowDefinition
    level: PermissionLevel
    nodes: dict[str, WorkflowNode] = field(default_factory=dict)
    incoming: dict[str, list[WorkflowEdge]] = field(default_factory=dict)
    states: dict[str, NodeState] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)

    def variables(self, **extra: Any) -> dict[str, Any]:
        nodes = {
            k: {"output": s.output, "status": s.status}
            for k, s in self.states.items()
            if s.status in ("COMPLETED", "SKIPPED", "FAILED")
        }
        return {"inputs": self.run.inputs, "nodes": nodes, **extra}


def _failed(code: str, message: str) -> Result:
    return Result("FAILED", error={"code": code, "message": message[:1000]})


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def workflow_agent(workflow_id: str, name: str, tool: str) -> AgentDefinition:
    """The identity a workflow's tool step acts under: exactly one tool, and permission to ask."""
    return AgentDefinition(
        id=f"workflow_{workflow_id}",
        slug="workflow",
        name=f"Workflow: {name}"[:80],
        role="Runs a workflow step",
        tools=[tool],
        permissions=AgentPermissions(max_risk=RiskLevel.VERY_HIGH, may_request_approval=True),
    )


class WorkflowEngine:
    def __init__(
        self,
        *,
        workflows: WorkflowStore,
        runs: WorkflowRunStore,
        runner: AgentRunner,
        agents: AgentStore,
        agent_runs: RunStore,
        executor: ToolExecutor,
        tool_contexts: ToolContextFactory,
        bus: EventBus,
        level_for: LevelFor,
        clock: Clock | None = None,
        notify: NotifyFn | None = None,
        sleep: Sleep | None = None,
    ) -> None:
        self._workflows = workflows
        self._runs = runs
        self._runner = runner
        self._agents = agents
        self._agent_runs = agent_runs
        self._executor = executor
        self._tool_contexts = tool_contexts
        self._bus = bus
        self._level_for = level_for
        self._clock = clock or SystemClock()
        self._notify = notify
        self._sleep: Sleep = sleep or asyncio.sleep
        self.start_child: StartChild | None = None  # set by the service (it validates and creates child runs)
        self.shutting_down = False
        self._live: dict[str, tuple[_Ctx, asyncio.Event]] = {}

    def deliver(self, run_id: str, node_id: str, state: NodeState) -> bool:
        """Hand a person's decision to a walk that is still running. False when no walk is live (the
        caller then saves the state and starts a new walk)."""
        live = self._live.get(run_id)
        if live is None:
            return False
        ctx, wake = live
        ctx.states[node_id] = state
        wake.set()
        return True

    # ======================================================================= the walk
    async def execute(self, run_id: str) -> WorkflowRunOut:
        ctx = await self._load(run_id)
        if ctx.run.status.terminal:
            return ctx.run
        running: dict[str, asyncio.Task[Result]] = {}
        wake = asyncio.Event()
        self._live[run_id] = (ctx, wake)
        try:
            await self._set_status(ctx, WorkflowRunStatus.RUNNING)
            while True:
                if wake.is_set():  # a decision arrived for a waiting step
                    wake.clear()
                    await self._save(ctx)
                if self._settle_skips(ctx):
                    await self._save(ctx)
                ready = [k for k in ctx.nodes if ctx.states[k].status == "PENDING" and self._is_ready(ctx, k)]
                for key in ready[: max(0, MAX_PARALLEL - len(running))]:
                    await self._mark_started(ctx, key)
                    running[key] = asyncio.create_task(self._run_node(ctx, ctx.nodes[key]))
                if not running:
                    break
                woken = asyncio.create_task(wake.wait())
                done, _ = await asyncio.wait([*running.values(), woken], return_when=asyncio.FIRST_COMPLETED)
                woken.cancel()
                for key in [k for k, t in running.items() if t in done]:
                    result = running.pop(key).result()
                    await self._apply(ctx, key, result)
                    if result.status == "FAILED" and not ctx.nodes[key].continue_on_error:
                        await self._stop(running, ctx, "CANCELLED")
                        return await self._finish(
                            ctx, WorkflowRunStatus.FAILED, {"node": key, **(result.error or {})}
                        )
            return await self._conclude(ctx)
        except asyncio.CancelledError:
            if self.shutting_down:  # park: recovery continues from the saved states
                for t in running.values():
                    t.cancel()
                await asyncio.gather(*running.values(), return_exceptions=True)
                await self._save(ctx)
            else:
                await asyncio.shield(self._cancelled(ctx, running))
            raise
        finally:
            if self._live.get(run_id, (None,))[0] is ctx:
                del self._live[run_id]

    async def _conclude(self, ctx: _Ctx) -> WorkflowRunOut:
        statuses = {s.status for s in ctx.states.values()}
        if "WAITING" in statuses:
            waiting = [k for k, s in ctx.states.items() if s.status == "WAITING"]
            run = await self._runs.update(
                ctx.run.id, status=WorkflowRunStatus.WAITING, node_states=self._dump(ctx)
            )
            await self._emit(EventType.WORKFLOW_WAITING, ctx, {"nodes": waiting})
            return run
        if "PENDING" in statuses:  # nothing can run (should not happen in a validated graph)
            return await self._finish(
                ctx, WorkflowRunStatus.FAILED, {"code": "stuck", "message": "Some steps could never start."}
            )
        return await self._finish(ctx, WorkflowRunStatus.COMPLETED, None)

    def _is_ready(self, ctx: _Ctx, key: str) -> bool:
        edges = ctx.incoming.get(key, [])
        active = [self._edge_active(ctx, e) for e in edges]
        return all(a is not None for a in active) and any(active)

    def _settle_skips(self, ctx: _Ctx) -> bool:
        changed = False
        again = True
        while again:
            again = False
            for key, state in ctx.states.items():
                if state.status != "PENDING" or ctx.nodes[key].type == "trigger":
                    continue
                active = [self._edge_active(ctx, e) for e in ctx.incoming.get(key, [])]
                if active and all(a is False for a in active):
                    state.status = "SKIPPED"
                    state.finished_at = self._clock.now()
                    changed = again = True
        return changed

    def _edge_active(self, ctx: _Ctx, edge: WorkflowEdge) -> bool | None:
        src = ctx.states[edge.source]
        if src.status not in SETTLED:
            return None
        if src.status != "COMPLETED":
            return False
        kind = ctx.nodes[edge.source].type
        out = src.output if isinstance(src.output, dict) else {}
        if kind == "condition":
            return (edge.branch == "true") == bool(out.get("value"))
        if kind == "approval":
            approved = bool(out.get("approved"))
            return approved if edge.branch in (None, "true") else not approved
        return True

    # ======================================================================= one step
    async def _run_node(self, ctx: _Ctx, node: WorkflowNode) -> Result:
        try:
            handler = getattr(self, f"_node_{node.type}")
            result: Result = await handler(ctx, node)
            return result
        except asyncio.CancelledError:
            raise
        except ExpressionError as exc:
            return _failed("expression", str(exc))
        except NexusError as exc:
            return _failed(exc.code, exc.message)
        except Exception as exc:
            log.exception("workflow step %s crashed", node.id)
            return _failed("internal_error", f"This step failed unexpectedly ({type(exc).__name__}).")

    async def _node_trigger(self, ctx: _Ctx, node: WorkflowNode) -> Result:
        return Result("COMPLETED", dict(ctx.run.inputs))

    async def _node_condition(self, ctx: _Ctx, node: WorkflowNode) -> Result:
        cfg = ConditionNodeConfig.model_validate(node.config)
        return Result("COMPLETED", {"value": bool(evaluate(cfg.expression, ctx.variables()))})

    async def _node_transform(self, ctx: _Ctx, node: WorkflowNode) -> Result:
        cfg = ValuesNodeConfig.model_validate(node.config)
        return Result("COMPLETED", {k: evaluate(v, ctx.variables()) for k, v in cfg.values.items()})

    async def _node_output(self, ctx: _Ctx, node: WorkflowNode) -> Result:
        cfg = ValuesNodeConfig.model_validate(node.config)
        values = {k: evaluate(v, ctx.variables()) for k, v in cfg.values.items()}
        ctx.outputs.update(values)
        return Result("COMPLETED", values)

    async def _node_delay(self, ctx: _Ctx, node: WorkflowNode) -> Result:
        cfg = DelayNodeConfig.model_validate(node.config)
        started = ctx.states[node.id].started_at or self._clock.now()
        remaining = cfg.seconds - (self._clock.now() - started).total_seconds()
        if remaining > 0:
            await self._sleep(remaining)
        return Result("COMPLETED", {"waited_s": cfg.seconds})

    async def _node_approval(self, ctx: _Ctx, node: WorkflowNode) -> Result:
        cfg = ApprovalNodeConfig.model_validate(node.config)
        message = render(cfg.message, ctx.variables())
        if self._notify is not None:
            await self._notify(
                "workflow",
                f"{ctx.name} is waiting for your approval",
                message[:300],
                {"workflow_run_id": ctx.run.id, "node": node.id},
            )
        return Result("WAITING", {"message": message})

    async def _node_agent(self, ctx: _Ctx, node: WorkflowNode) -> Result:
        return await self._agent_step(ctx, node, AgentNodeConfig.model_validate(node.config), ctx.variables())

    async def _node_tool(self, ctx: _Ctx, node: WorkflowNode) -> Result:
        return await self._tool_step(ctx, node, ToolNodeConfig.model_validate(node.config), ctx.variables())

    async def _node_loop(self, ctx: _Ctx, node: WorkflowNode) -> Result:
        cfg = LoopNodeConfig.model_validate(node.config)
        items = evaluate(cfg.items, ctx.variables())
        if not isinstance(items, list):
            return _failed("not_a_list", f"'{cfg.items}' did not give a list (got {type(items).__name__}).")
        if len(items) > cfg.max_items:
            return _failed(
                "too_many_items", f"{len(items)} items, but this loop allows at most {cfg.max_items}."
            )
        results: list[Any] = []
        for index, item in enumerate(items):
            variables = ctx.variables(item=item, index=index)
            if cfg.body.type == "agent":
                step = await self._agent_step(
                    ctx, node, AgentNodeConfig.model_validate(cfg.body.config), variables, fresh=True
                )
            else:
                step = await self._tool_step(
                    ctx, node, ToolNodeConfig.model_validate(cfg.body.config), variables
                )
            if step.status != "COMPLETED":
                if step.status == "WAITING":
                    return _failed(
                        "needs_input", "A loop step asked a question; loops cannot wait for answers."
                    )
                return Result("FAILED", {"items": results}, {**(step.error or {}), "item": index})
            results.append(step.output)
        return Result("COMPLETED", {"items": results, "count": len(results)})

    async def _node_subworkflow(self, ctx: _Ctx, node: WorkflowNode) -> Result:
        cfg = SubworkflowNodeConfig.model_validate(node.config)
        state = ctx.states[node.id]
        if state.child_run_id is None:
            if self.start_child is None:
                return _failed("unavailable", "Sub-workflows are not available.")
            inputs = {k: evaluate(v, ctx.variables()) for k, v in cfg.inputs.items()}
            child = await self.start_child(ctx.run, cfg.workflow_id, inputs)
            state.child_run_id = child.id
            await self._save(ctx)
        child = await self._runs.get(state.child_run_id)
        if not child.status.terminal and child.status is not WorkflowRunStatus.WAITING:
            child = await self.execute(child.id)
        if child.status is WorkflowRunStatus.WAITING:
            return Result("WAITING", {"child_run_id": child.id})
        if child.status is WorkflowRunStatus.COMPLETED:
            return Result("COMPLETED", dict(child.outputs))
        return _failed("subworkflow_failed", f"The sub-workflow ended {child.status.value.lower()}.")

    # ---- steps that act through the runtime -------------------------------------------------
    async def _agent_step(
        self,
        ctx: _Ctx,
        node: WorkflowNode,
        cfg: AgentNodeConfig,
        variables: dict[str, Any],
        *,
        fresh: bool = False,
    ) -> Result:
        agent = await self._agents.get(cfg.agent)
        if agent.status == "disabled":
            return _failed("agent_disabled", f"The {agent.name} agent is disabled.")
        state = ctx.states[node.id]

        async def on_status(status: RunStatus) -> None:
            state.status = "WAITING" if status is RunStatus.WAITING_APPROVAL else "RUNNING"
            await self._save(ctx)
            await self._set_status(
                ctx, WorkflowRunStatus.WAITING if state.status == "WAITING" else WorkflowRunStatus.RUNNING
            )

        if state.resume and state.run_id and not fresh:
            state.resume = False
            run = await self._agent_runs.get(state.run_id)
            if run.status in (RunStatus.INTERRUPTED, RunStatus.FAILED, RunStatus.TIMED_OUT):
                await self._runner.prepare_resume(state.run_id, agent=agent)
            outcome = await self._runner.execute(state.run_id, agent=agent, on_status=on_status)
        else:
            prompt = render_prompt(cfg.prompt, variables)
            blocks = [ContextBlock(f"workflow:{label}", value) for label, value in prompt.data]
            req = RunRequest(
                agent=agent,
                project_id=ctx.run.project_id,
                prompt=prompt.text,
                context=blocks,
                model=cfg.model,
                permission_level=ctx.level,
                unattended=ctx.run.unattended,
                task_class=task_class_for(agent),
                title=f"{ctx.name} · {node.label or node.id}"[:200],
                taint=[f"workflow:{label}" for label, _ in prompt.data],
            )
            run = await self._runner.create(req)
            if not fresh:
                state.run_id = run.id
                await self._save(ctx)
            outcome = await self._runner.execute(run.id, agent=agent, on_status=on_status)

        if outcome.status is RunStatus.WAITING_INPUT:
            state.error = {
                "code": "needs_input",
                "message": outcome.question or "",
                "options": outcome.options,
            }
            return Result("WAITING", None, state.error)
        if not outcome.ok:
            err = outcome.run.error or {}
            return _failed(
                str(err.get("code") or outcome.status.value.lower()),
                str(err.get("message") or "The agent did not finish."),
            )
        output = _jsonable(outcome.result) or {"summary": outcome.summary}
        if isinstance(output, dict) and output.get("status") == "failed":
            return Result(
                "FAILED",
                output,
                {"code": "agent_reported_failure", "message": str(output.get("summary", ""))},
            )
        return Result("COMPLETED", output)

    async def _tool_step(
        self, ctx: _Ctx, node: WorkflowNode, cfg: ToolNodeConfig, variables: dict[str, Any]
    ) -> Result:
        args = render_value(cfg.arguments, variables)
        if not isinstance(args, dict):
            return _failed("invalid_arguments", "Tool arguments must be a set of named values.")
        workflow = await self._workflows.get(ctx.run.workflow_id, include_deleted=True)
        agent = workflow_agent(workflow.id, workflow.name, cfg.tool)
        tctx = await self._tool_contexts.build(
            project_id=ctx.run.project_id,
            run_id=None,
            agent_id=agent.id,
            unattended=ctx.run.unattended,
            agent_slug=agent.slug,
        )
        # Arguments built from other steps' results may carry text from outside: treat them as tainted.
        taint = [f"workflow:{s}" for s in _step_refs(cfg.arguments)]
        state = ctx.states[node.id]

        async def on_wait(approval: ApprovalOut | None) -> None:
            # Called with the approval when parking and with None when the wait ends (also on cancel),
            # so the approval id is kept until the step returns normally.
            state.status = "WAITING" if approval is not None else "RUNNING"
            if approval is not None:
                state.approval_id = approval.id
                state.error = {"code": "needs_approval", "approval_id": approval.id}
            await self._save(ctx)
            await self._set_status(
                ctx, WorkflowRunStatus.WAITING if approval is not None else WorkflowRunStatus.RUNNING
            )

        ectx = ExecContext(
            project_id=ctx.run.project_id,
            run_id=None,
            task_id=None,
            objective_id=None,
            agent=agent,
            permission_level=ctx.level,
            tool_context=tctx,
            taint=TaintTracker.from_list(taint),
            unattended=ctx.run.unattended,
            on_wait=on_wait,
        )
        outcome = await self._executor.execute(
            ectx, cfg.tool, args, summary=f"{ctx.name}: {node.label or node.id}"
        )
        state.error, state.approval_id = None, None
        if outcome.status != "ok":
            return _failed(outcome.error_code or outcome.status, outcome.text)
        data = outcome.data if outcome.data is not None else outcome.text
        return Result("COMPLETED", _jsonable(data))

    # ======================================================================= bookkeeping
    async def _load(self, run_id: str) -> _Ctx:
        run = await self._runs.get(run_id)
        workflow = await self._workflows.get(run.workflow_id, include_deleted=True)
        definition = await self._workflows.definition_at(run.workflow_id, run.workflow_version)
        ctx = _Ctx(
            run=run, name=workflow.name, definition=definition, level=await self._level_for(run.project_id)
        )
        ctx.nodes = {n.id: n for n in definition.nodes}
        for e in definition.edges:
            ctx.incoming.setdefault(e.target, []).append(e)
        ctx.states = {k: run.node_states.get(k) or NodeState() for k in ctx.nodes}
        ctx.outputs = dict(run.outputs)
        for key, state in ctx.states.items():
            # A sub-workflow that finished (or changed) while this run waited: look again.
            if state.status == "WAITING" and state.child_run_id:
                child = await self._runs.get(state.child_run_id)
                if child.status is not WorkflowRunStatus.WAITING:
                    state.status = "PENDING"
            if ctx.nodes[key].type == "trigger" and state.status == "PENDING":
                state.status, state.output = "COMPLETED", dict(run.inputs)
                state.started_at = state.finished_at = self._clock.now()
        return ctx

    async def _mark_started(self, ctx: _Ctx, key: str) -> None:
        state = ctx.states[key]
        state.status = "RUNNING"
        state.started_at = state.started_at or self._clock.now()
        state.attempts += 1
        state.error = None
        await self._save(ctx)
        node = ctx.nodes[key]
        await self._emit(
            EventType.WORKFLOW_NODE_STARTED, ctx, {"node": key, "type": node.type, "label": node.label}
        )

    async def _apply(self, ctx: _Ctx, key: str, result: Result) -> None:
        state = ctx.states[key]
        node = ctx.nodes[key]
        state.output = result.output
        state.error = result.error
        if result.status == "WAITING":
            state.status = "WAITING"
        elif result.status == "FAILED" and node.continue_on_error:
            state.status = "COMPLETED"
            state.output = {
                "error": result.error,
                **(result.output if isinstance(result.output, dict) else {}),
            }
            state.finished_at = self._clock.now()
        else:
            state.status = "COMPLETED" if result.status == "COMPLETED" else "FAILED"
            state.finished_at = self._clock.now()
        await self._save(ctx)
        base = {"node": key, "type": node.type, "label": node.label}
        if state.status == "COMPLETED":
            await self._emit(EventType.WORKFLOW_NODE_COMPLETED, ctx, base)
        elif state.status == "FAILED":
            await self._emit(
                EventType.WORKFLOW_NODE_FAILED,
                ctx,
                {**base, "message": (result.error or {}).get("message", "")},
            )

    async def _stop(self, running: dict[str, asyncio.Task[Result]], ctx: _Ctx, status: str) -> None:
        for t in running.values():
            t.cancel()
        await asyncio.gather(*running.values(), return_exceptions=True)
        for key in running:
            ctx.states[key].status = status  # type: ignore[assignment]
            ctx.states[key].finished_at = self._clock.now()
        running.clear()
        await self._save(ctx)

    async def _cancelled(self, ctx: _Ctx, running: dict[str, asyncio.Task[Result]]) -> None:
        await self._stop(running, ctx, "CANCELLED")
        for state in ctx.states.values():
            if state.status in ("PENDING", "WAITING"):
                state.status = "CANCELLED"
        await self._finish(
            ctx, WorkflowRunStatus.CANCELLED, {"code": "cancelled", "message": "Cancelled by you."}
        )

    async def _finish(
        self, ctx: _Ctx, status: WorkflowRunStatus, error: dict[str, Any] | None
    ) -> WorkflowRunOut:
        run = await self._runs.update(
            ctx.run.id,
            status=status,
            node_states=self._dump(ctx),
            outputs=ctx.outputs,
            error=error,
            finished_at=self._clock.now(),
        )
        ctx.run = run
        event = {
            WorkflowRunStatus.COMPLETED: EventType.WORKFLOW_COMPLETED,
            WorkflowRunStatus.FAILED: EventType.WORKFLOW_FAILED,
            WorkflowRunStatus.CANCELLED: EventType.WORKFLOW_CANCELLED,
        }[status]
        await self._emit(
            event,
            ctx,
            {"outputs": list(ctx.outputs)[:20], **({"message": error.get("message", "")} if error else {})},
        )
        return run

    async def _set_status(self, ctx: _Ctx, status: WorkflowRunStatus) -> None:
        if ctx.run.status is not status:
            ctx.run = await self._runs.update(ctx.run.id, status=status)

    async def _save(self, ctx: _Ctx) -> None:
        ctx.run = await self._runs.update(ctx.run.id, node_states=self._dump(ctx), outputs=ctx.outputs)

    @staticmethod
    def _dump(ctx: _Ctx) -> dict[str, Any]:
        return {k: s.model_dump(mode="json") for k, s in ctx.states.items()}

    async def _emit(self, type_: EventType, ctx: _Ctx, payload: dict[str, Any]) -> None:
        await self._bus.emit(
            type_,
            project_id=ctx.run.project_id,
            actor="scheduler" if ctx.run.unattended else "workflow",
            payload={
                "workflow_id": ctx.run.workflow_id,
                "workflow_run_id": ctx.run.id,
                "name": ctx.name,
                **payload,
            },
        )


def _step_refs(value: Any) -> set[str]:
    """The expressions in a tool step's argument templates that read anything but the run's inputs."""
    found: set[str] = set()
    if isinstance(value, str):
        for hole in holes(value):
            if root_names(hole) - {"inputs"}:
                found.add(hole.strip()[:80])
    elif isinstance(value, list):
        for v in value:
            found |= _step_refs(v)
    elif isinstance(value, dict):
        for v in value.values():
            found |= _step_refs(v)
    return found
