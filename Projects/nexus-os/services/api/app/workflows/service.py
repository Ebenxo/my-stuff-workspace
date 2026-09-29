"""WorkflowService: workflows (with versions), their runs, and the person's decisions within them.

Runs execute as supervised asyncio tasks (like objectives: a run may wait a day for an approval). The
service validates before anything runs, starts and resumes runs, relays approvals, answers and retries,
and recovers runs after a restart: agent steps continue from their checkpoints; a tool step that was in
flight is marked failed (it may or may not have happened) so the person decides whether to retry.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from app.agents.runner import AgentRunner
from app.core.clock import Clock, SystemClock
from app.core.errors import ConflictError, InvalidRequestError
from app.events.bus import EventBus
from app.events.types import EventType
from app.permissions.approvals import ApprovalService
from app.repositories.runtime_store import AgentStore, ToolRowStore
from app.repositories.workflow_store import WorkflowRunStore, WorkflowStore
from app.schemas.runtime import ApprovalDecision
from app.schemas.workflows import (
    NodeState,
    ValidationReport,
    WorkflowCreate,
    WorkflowDefinition,
    WorkflowOut,
    WorkflowRunDetail,
    WorkflowRunOut,
    WorkflowRunStatus,
    WorkflowUpdate,
    WorkflowVersionOut,
)
from app.tools.registry import ToolRegistry
from app.workflows.engine import WorkflowEngine
from app.workflows.validate import starter_definition, validate_definition

log = logging.getLogger(__name__)

MAX_DEPTH = 3
PROJECT_EXISTS = Callable[[str], Coroutine[Any, Any, Any]]


class WorkflowService:
    def __init__(
        self,
        *,
        workflows: WorkflowStore,
        runs: WorkflowRunStore,
        engine: WorkflowEngine,
        runner: AgentRunner,
        agents: AgentStore,
        registry: ToolRegistry,
        tool_rows: ToolRowStore,
        approvals: ApprovalService,
        bus: EventBus,
        project_exists: PROJECT_EXISTS,
        clock: Clock | None = None,
    ) -> None:
        self._workflows = workflows
        self._runs = runs
        self._engine = engine
        self._runner = runner
        self._agents = agents
        self._registry = registry
        self._rows = tool_rows
        self._approvals = approvals
        self._bus = bus
        self._project_exists = project_exists
        self._clock = clock or SystemClock()
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        engine.start_child = self._start_child

    # ======================================================================= definitions
    async def create(self, body: WorkflowCreate) -> WorkflowOut:
        await self._project_exists(body.project_id)
        wf = await self._workflows.create(
            project_id=body.project_id,
            name=body.name.strip(),
            description=body.description.strip(),
            definition=body.definition or starter_definition(),
        )
        await self._emit(EventType.WORKFLOW_CREATED, wf.project_id, {"workflow_id": wf.id, "name": wf.name})
        return wf

    async def get(self, workflow_id: str) -> WorkflowOut:
        return await self._workflows.get(workflow_id)

    async def list_workflows(self, project_id: str | None = None) -> list[WorkflowOut]:
        return await self._workflows.list_workflows(project_id=project_id)

    async def update(self, workflow_id: str, body: WorkflowUpdate) -> WorkflowOut:
        fields: dict[str, Any] = {}
        if body.name is not None:
            fields["name"] = body.name.strip()
        if body.description is not None:
            fields["description"] = body.description.strip()
        if body.enabled is not None:
            fields["enabled"] = body.enabled
        before = await self._workflows.get(workflow_id)
        wf = await self._workflows.update(workflow_id, definition=body.definition, **fields)
        await self._emit(
            EventType.WORKFLOW_UPDATED,
            wf.project_id,
            {
                "workflow_id": wf.id,
                "name": wf.name,
                "version": wf.version,
                "new_version": wf.version != before.version,
            },
        )
        return wf

    async def delete(self, workflow_id: str) -> None:
        wf = await self._workflows.get(workflow_id)
        await self._workflows.update(workflow_id, deleted=True, enabled=False)
        await self._emit(EventType.WORKFLOW_DELETED, wf.project_id, {"workflow_id": wf.id, "name": wf.name})

    async def versions(self, workflow_id: str) -> list[WorkflowVersionOut]:
        await self._workflows.get(workflow_id)
        return await self._workflows.versions(workflow_id)

    async def validate(
        self, definition: WorkflowDefinition, *, project_id: str, self_id: str | None = None
    ) -> ValidationReport:
        agents = {
            a.slug
            for a in await self._agents.list_all()
            if a.status != "disabled" and a.slug not in ("orchestrator",)
        }
        disabled = await self._rows.disabled_names()
        tools = {t.name for t in self._registry.all() if t.name not in disabled}
        workflows = {w.id for w in await self._workflows.list_workflows(project_id=project_id)}
        return validate_definition(
            definition, agents=agents, tools=tools, workflows=workflows, self_id=self_id
        )

    # ======================================================================= runs
    async def start(
        self,
        workflow_id: str,
        inputs: dict[str, Any],
        *,
        unattended: bool = False,
        schedule_id: str | None = None,
    ) -> WorkflowRunOut:
        wf = await self._workflows.get(workflow_id)
        if not wf.enabled:
            raise ConflictError("This workflow is turned off. Turn it on to run it.")
        run = await self._create_run(wf, inputs, unattended=unattended, schedule_id=schedule_id)
        self._spawn(run.id)
        return run

    async def _create_run(
        self,
        wf: WorkflowOut,
        inputs: dict[str, Any],
        *,
        unattended: bool,
        schedule_id: str | None = None,
        parent: WorkflowRunOut | None = None,
    ) -> WorkflowRunOut:
        report = await self.validate(wf.definition, project_id=wf.project_id, self_id=wf.id)
        if not report.ok:
            raise InvalidRequestError(
                "This workflow cannot run yet: " + "; ".join(i.message for i in report.issues[:5])
            )
        clean = coerce_inputs(wf.definition, inputs)
        run = await self._runs.create(
            workflow_id=wf.id,
            workflow_version=wf.version,
            project_id=wf.project_id,
            unattended=unattended if parent is None else parent.unattended,
            schedule_id=schedule_id,
            parent_run_id=parent.id if parent else None,
            depth=(parent_depth(parent) + 1) if parent else 0,
            inputs=clean,
            node_states={n.id: NodeState().model_dump(mode="json") for n in wf.definition.nodes},
        )
        await self._emit(
            EventType.WORKFLOW_STARTED,
            wf.project_id,
            {
                "workflow_id": wf.id,
                "workflow_run_id": run.id,
                "name": wf.name,
                "version": wf.version,
                "unattended": run.unattended,
                "scheduled": schedule_id is not None,
            },
            actor="scheduler" if schedule_id else "user",
        )
        return run

    async def _start_child(
        self, parent: WorkflowRunOut, workflow_id: str, inputs: dict[str, Any]
    ) -> WorkflowRunOut:
        if parent_depth(parent) + 1 > MAX_DEPTH:
            raise InvalidRequestError(f"Sub-workflows can nest at most {MAX_DEPTH} deep.")
        wf = await self._workflows.get(workflow_id)
        if wf.project_id != parent.project_id:
            raise InvalidRequestError("A sub-workflow must belong to the same project.")
        return await self._create_run(wf, inputs, unattended=parent.unattended, parent=parent)

    async def detail(self, run_id: str) -> WorkflowRunDetail:
        run = await self._runs.get(run_id)
        wf = await self._workflows.get(run.workflow_id, include_deleted=True)
        definition = await self._workflows.definition_at(run.workflow_id, run.workflow_version)
        return WorkflowRunDetail(run=run, definition=definition, name=wf.name)

    async def list_runs(
        self, *, workflow_id: str | None = None, project_id: str | None = None, limit: int = 50
    ) -> list[WorkflowRunOut]:
        return await self._runs.list_runs(workflow_id=workflow_id, project_id=project_id, limit=limit)

    async def cancel(self, run_id: str) -> WorkflowRunOut:
        run = await self._runs.get(run_id)
        if run.status.terminal:
            raise ConflictError(f"This run already {run.status.value.lower()}.")
        task = self._tasks.get(run_id)
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
            # A tool step's approval is not tied to an agent run: close it here.
            for s in (await self._runs.get(run_id)).node_states.values():
                if s.approval_id:
                    await self._deny_quietly(s.approval_id, "The workflow run was cancelled.")
        else:
            # Waiting with nothing in flight: settle it here.
            states = {k: NodeState.model_validate(v) for k, v in run.node_states.items()}
            for s in states.values():
                if s.status in ("PENDING", "WAITING", "RUNNING"):
                    s.status = "CANCELLED"
                    if s.error and s.error.get("approval_id"):
                        await self._deny_quietly(
                            str(s.error["approval_id"]), "The workflow run was cancelled."
                        )
            await self._runs.update(
                run_id,
                status=WorkflowRunStatus.CANCELLED,
                node_states={k: s.model_dump(mode="json") for k, s in states.items()},
                error={"code": "cancelled", "message": "Cancelled by you."},
                finished_at=self._clock.now(),
            )
            await self._emit(
                EventType.WORKFLOW_CANCELLED,
                run.project_id,
                {"workflow_id": run.workflow_id, "workflow_run_id": run_id},
            )
        for child in await self._runs.list_runs(project_id=run.project_id, statuses=("RUNNING", "WAITING")):
            if child.parent_run_id == run_id:
                with contextlib.suppress(ConflictError):
                    await self.cancel(child.id)
        return await self._runs.get(run_id)

    async def decide(self, run_id: str, node_id: str, *, approved: bool, note: str = "") -> WorkflowRunOut:
        run, state = await self._waiting_node(run_id, node_id)
        detail = await self.detail(run_id)
        node = next(n for n in detail.definition.nodes if n.id == node_id)
        if node.type != "approval":
            raise ConflictError(
                "Only an approval step is decided here. Tool and agent approvals are on the Approvals page."
            )
        message = state.output.get("message", "") if isinstance(state.output, dict) else ""
        state.status = "COMPLETED"
        state.output = {"approved": approved, "note": note, "message": message, "by": "user"}
        state.finished_at = self._clock.now()
        await self._emit(
            EventType.WORKFLOW_NODE_COMPLETED,
            run.project_id,
            {
                "workflow_id": run.workflow_id,
                "workflow_run_id": run_id,
                "node": node_id,
                "type": "approval",
                "approved": approved,
            },
            actor="user",
        )
        await self._deliver(run, node_id, state)
        return await self._runs.get(run_id)

    async def answer(self, run_id: str, node_id: str, text: str) -> WorkflowRunOut:
        run, state = await self._waiting_node(run_id, node_id)
        if not state.error or state.error.get("code") != "needs_input" or not state.run_id:
            raise ConflictError("This step is not waiting for an answer.")
        await self._engine_runner_answer(state.run_id, text)
        state.status, state.resume, state.error = "PENDING", True, None
        await self._deliver(run, node_id, state)
        return await self._runs.get(run_id)

    async def retry(self, run_id: str) -> WorkflowRunOut:
        run = await self._runs.get(run_id)
        if run.status is not WorkflowRunStatus.FAILED:
            raise ConflictError("Only a failed run can be retried.")
        states = {k: NodeState.model_validate(v) for k, v in run.node_states.items()}
        for s in states.values():
            if s.status in ("FAILED", "CANCELLED"):
                s.status, s.error, s.output, s.finished_at = "PENDING", None, None, None
                s.run_id, s.child_run_id, s.resume = None, None, False
        await self._runs.update(
            run_id,
            status=WorkflowRunStatus.RUNNING,
            node_states={k: s.model_dump(mode="json") for k, s in states.items()},
            error=None,
            finished_at=None,
        )
        self._spawn(run_id)
        return await self._runs.get(run_id)

    # ======================================================================= supervision
    def _spawn(self, run_id: str) -> None:
        existing = self._tasks.get(run_id)
        if existing is not None and not existing.done():
            return  # the live walk picks up the change on its own
        task = asyncio.create_task(self._drive(run_id), name=f"workflow:{run_id}")
        self._tasks[run_id] = task
        task.add_done_callback(
            lambda _t: self._tasks.pop(run_id, None) if self._tasks.get(run_id) is _t else None
        )

    async def _drive(self, run_id: str) -> None:
        try:
            run = await self._engine.execute(run_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("workflow run %s crashed", run_id)
            run = await self._runs.update(
                run_id,
                status=WorkflowRunStatus.FAILED,
                error={"code": "internal_error", "message": "An internal error stopped this run."},
                finished_at=self._clock.now(),
            )
        # A sub-workflow that just settled lets its parent continue.
        if run.parent_run_id and run.status is not WorkflowRunStatus.RUNNING:
            parent = await self._runs.get(run.parent_run_id)
            if parent.status is WorkflowRunStatus.WAITING:
                self._spawn(parent.id)

    async def wait_for(self, run_id: str, timeout: float = 30) -> WorkflowRunOut:  # noqa: ASYNC109
        """Tests and callers: block until the run's current walk ends (finished, failed or waiting)."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            task = self._tasks.get(run_id)
            if task is None or task.done():
                return await self._runs.get(run_id)
            await asyncio.wait({task}, timeout=max(0.01, deadline - loop.time()))
        raise TimeoutError(f"workflow run {run_id} did not settle")

    async def recover(self) -> list[WorkflowRunOut]:
        """After a restart: continue what can continue; fail what may have half-happened."""
        resumed: list[WorkflowRunOut] = []
        for run in await self._runs.list_runs(statuses=("RUNNING", "WAITING"), limit=10_000):
            detail = await self._workflows.definition_at(run.workflow_id, run.workflow_version)
            types = {n.id: n.type for n in detail.nodes}
            states = {k: NodeState.model_validate(v) for k, v in run.node_states.items()}
            interrupted: list[str] = []
            for key, s in states.items():
                kind = types.get(key)
                needs_input = bool(s.error and s.error.get("code") == "needs_input")
                if s.status == "RUNNING" or (
                    s.status == "WAITING" and kind in ("agent", "tool") and not needs_input
                ):
                    if kind == "agent" and s.run_id:
                        s.status, s.resume = "PENDING", True
                    elif kind in ("tool", "loop"):
                        if s.error and s.error.get("approval_id"):
                            await self._deny_quietly(
                                str(s.error["approval_id"]), "NEXUS restarted while this waited."
                            )
                        s.status = "FAILED"
                        s.error = {
                            "code": "interrupted",
                            "message": "NEXUS restarted while this step was running. It may or may not have finished: check, then retry.",
                        }
                        s.finished_at = self._clock.now()
                        interrupted.append(key)
                    else:
                        s.status = "PENDING"
            dumped = {k: s.model_dump(mode="json") for k, s in states.items()}
            if interrupted:
                run = await self._runs.update(
                    run.id,
                    status=WorkflowRunStatus.FAILED,
                    node_states=dumped,
                    error={
                        "node": interrupted[0],
                        "code": "interrupted",
                        "message": "Interrupted by a restart.",
                    },
                    finished_at=self._clock.now(),
                )
                await self._emit(
                    EventType.WORKFLOW_FAILED,
                    run.project_id,
                    {
                        "workflow_id": run.workflow_id,
                        "workflow_run_id": run.id,
                        "message": "Interrupted by a restart.",
                    },
                )
                continue
            run = await self._runs.update(run.id, node_states=dumped)
            if any(s.status == "PENDING" for s in states.values()):
                self._spawn(run.id)
                resumed.append(run)
        return resumed

    async def shutdown(self) -> None:
        # Flag both before cancelling: the runner must park its runs as interrupted, not cancelled.
        self._engine.shutting_down = True
        self._runner.shutting_down = True
        tasks = [t for t in self._tasks.values() if not t.done()]
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    # ======================================================================= helpers
    async def _waiting_node(self, run_id: str, node_id: str) -> tuple[WorkflowRunOut, NodeState]:
        run = await self._runs.get(run_id)
        if run.status.terminal:
            raise ConflictError(f"This run already {run.status.value.lower()}.")
        raw = run.node_states.get(node_id)
        if raw is None:
            raise InvalidRequestError(f"This run has no step '{node_id}'.")
        state = NodeState.model_validate(raw)
        if state.status != "WAITING":
            raise ConflictError("That step is not waiting for you.")
        return run, state

    async def _deliver(self, run: WorkflowRunOut, node_id: str, state: NodeState) -> None:
        """Give a decision to the live walk, or save it and start a walk that continues from it."""
        if self._engine.deliver(run.id, node_id, state):
            return
        latest = await self._runs.get(run.id)
        states = {k: v.model_dump(mode="json") for k, v in latest.node_states.items()}
        states[node_id] = state.model_dump(mode="json")
        await self._runs.update(run.id, node_states=states)
        self._spawn(run.id)

    async def _engine_runner_answer(self, agent_run_id: str, text: str) -> None:
        try:
            await self._runner.prepare_resume(agent_run_id, answer=text)
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc

    async def _deny_quietly(self, approval_id: str, note: str) -> None:
        with contextlib.suppress(Exception):
            await self._approvals.decide(
                approval_id, ApprovalDecision(decision="deny", note=note), actor="system"
            )

    async def _emit(
        self, type_: EventType, project_id: str | None, payload: dict[str, Any], *, actor: str = "user"
    ) -> None:
        await self._bus.emit(type_, project_id=project_id, actor=actor, payload=payload)


def parent_depth(run: WorkflowRunOut | None) -> int:
    return 0 if run is None else run.depth


def coerce_inputs(definition: WorkflowDefinition, given: dict[str, Any]) -> dict[str, Any]:
    """Check the run's inputs against the workflow's declared inputs; fill defaults; convert types."""
    declared = {i.name: i for i in definition.inputs}
    unknown = sorted(set(given) - set(declared))
    if unknown:
        raise InvalidRequestError(f"This workflow has no input called {', '.join(unknown)}.")
    out: dict[str, Any] = {}
    for spec in definition.inputs:
        value = given.get(spec.name, spec.default)
        if value is None or value == "":
            if spec.required:
                raise InvalidRequestError(f"The input '{spec.name}' is required.")
            out[spec.name] = None
            continue
        try:
            if spec.type == "number":
                out[spec.name] = float(value) if not isinstance(value, bool) else float(int(value))
                if out[spec.name].is_integer():
                    out[spec.name] = int(out[spec.name])
            elif spec.type == "boolean":
                out[spec.name] = (
                    value
                    if isinstance(value, bool)
                    else str(value).strip().lower() in ("true", "yes", "1", "on")
                )
            else:
                text = str(value)
                if len(text) > 20_000:
                    raise InvalidRequestError(f"The input '{spec.name}' is too long.")
                out[spec.name] = text
        except (TypeError, ValueError):
            raise InvalidRequestError(f"The input '{spec.name}' must be a {spec.type}.") from None
    return out
