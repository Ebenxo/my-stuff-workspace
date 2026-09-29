"""ObjectiveService: the lifecycle of objectives and the decisions a person makes about them.

Each objective runs as one supervised asyncio task (plan, then execute). A person can run or edit the
plan, cancel, resume after a pause, and unblock a task by retrying it, skipping it or answering it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from app.agents.runner import AgentRunner
from app.core.clock import Clock, SystemClock
from app.core.errors import ConflictError, InvalidRequestError
from app.core.security import redact_text
from app.events.bus import EventBus
from app.events.types import EventType
from app.orchestration.graph import TaskGraph
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.strategy import estimate
from app.orchestration.validator import PlanInvalid, validate_plan
from app.repositories.events import EventFilter
from app.repositories.orchestration_store import NewTask, ObjectiveStore, TaskStore
from app.repositories.runtime_store import AgentStore, RunStore, ToolRowStore
from app.schemas.orchestration import (
    AgentMessage,
    ObjectiveCreate,
    ObjectiveDetail,
    ObjectiveOut,
    ObjectiveRun,
    ObjectiveStatus,
    PlanEdit,
    PlanResult,
    TaskOut,
    TaskStatus,
)
from app.schemas.runtime import RunStatus
from app.services.notifications import NotificationService
from app.services.projects import ProjectService
from app.tools.registry import ToolRegistry

log = logging.getLogger(__name__)
MAX_ACTIVE_OBJECTIVES = 3

_STATUS_NOTES = {
    ObjectiveStatus.AWAITING_PLAN_APPROVAL: "plan is ready for your review",
    ObjectiveStatus.COMPLETED: "is complete",
    ObjectiveStatus.PARTIAL: "finished partly",
    ObjectiveStatus.FAILED: "could not be completed",
    ObjectiveStatus.PAUSED: "needs you",
}


class ObjectiveService:
    def __init__(
        self,
        *,
        objectives: ObjectiveStore,
        tasks: TaskStore,
        orchestrator: Orchestrator,
        runner: AgentRunner,
        runs: RunStore,
        agents: AgentStore,
        registry: ToolRegistry,
        tool_rows: ToolRowStore,
        projects: ProjectService,
        notifications: NotificationService,
        bus: EventBus,
        clock: Clock | None = None,
    ) -> None:
        self._objectives = objectives
        self._tasks = tasks
        self._orch = orchestrator
        self._runner = runner
        self._runs = runs
        self._agents = agents
        self._registry = registry
        self._rows = tool_rows
        self._projects = projects
        self._notifications = notifications
        self._bus = bus
        self._clock = clock or SystemClock()
        self._active: dict[str, asyncio.Task[Any]] = {}

    # ---- background execution ---------------------------------------------------------------
    def active_ids(self) -> list[str]:
        return [oid for oid, t in self._active.items() if not t.done()]

    def _spawn(self, objective_id: str, coro: Coroutine[Any, Any, ObjectiveOut]) -> None:
        if objective_id in self.active_ids():
            coro.close()
            return  # already running: it will pick up the change on its next pass
        if len(self.active_ids()) >= MAX_ACTIVE_OBJECTIVES:
            coro.close()
            raise ConflictError(
                f"{MAX_ACTIVE_OBJECTIVES} objectives are already in progress. Wait for one to finish, or cancel one."
            )
        task = asyncio.create_task(self._supervise(objective_id, coro), name=f"objective-{objective_id}")
        self._active[objective_id] = task

        def forget(t: asyncio.Task[Any]) -> None:
            if self._active.get(objective_id) is t:
                del self._active[objective_id]

        task.add_done_callback(forget)

    async def _supervise(self, objective_id: str, coro: Coroutine[Any, Any, ObjectiveOut]) -> None:
        try:
            obj = await coro
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("objective %s failed outside the orchestrator", objective_id)
            obj = await self._objectives.update(
                objective_id,
                status=ObjectiveStatus.FAILED,
                error={"code": "internal_error", "message": "An internal error stopped this objective."},
                completed_at=self._clock.now(),
            )
            await self._bus.emit(
                EventType.OBJECTIVE_FAILED,
                project_id=obj.project_id,
                objective_id=obj.id,
                payload={"code": "internal_error"},
            )
        await self._notify(obj)

    async def _notify(self, obj: ObjectiveOut) -> None:
        note = _STATUS_NOTES.get(obj.status)
        if note is None:
            return
        detail = (obj.result or {}).get("summary") or (obj.error or {}).get("message") or ""
        try:
            await self._notifications.notify(
                "objective",
                f"Objective {note}",
                f"{obj.text[:80]}{': ' + str(detail)[:160] if detail else ''}",
                project_id=obj.project_id,
                ref={"objective_id": obj.id},
            )
        except Exception:
            log.exception("could not notify about objective %s", obj.id)

    async def _plan_then_maybe_run(self, objective_id: str) -> ObjectiveOut:
        obj = await self._orch.plan(objective_id)
        if obj.status is ObjectiveStatus.AWAITING_PLAN_APPROVAL and obj.run_mode == "auto":
            return await self._orch.execute(objective_id)
        return obj

    async def wait_for(self, objective_id: str, timeout_s: float = 30.0) -> ObjectiveOut:
        """Block until the objective's background work stops (finishes, pauses or awaits a plan decision)."""
        task = self._active.get(objective_id)
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), timeout_s)
        return await self._objectives.get(objective_id)

    # ---- objectives ---------------------------------------------------------------------------
    async def create(self, data: ObjectiveCreate) -> ObjectiveOut:
        project = await self._projects.get(data.project_id)
        if project.status == "archived":
            raise ConflictError("This project is archived. Restore it before giving it objectives.")
        if len(self.active_ids()) >= MAX_ACTIVE_OBJECTIVES:
            raise ConflictError(
                f"{MAX_ACTIVE_OBJECTIVES} objectives are already in progress. Wait for one to finish, or cancel one."
            )
        obj = await self._objectives.create(
            project_id=project.id,
            text=redact_text(data.text.strip()),
            run_mode=data.run_mode,
            execution_mode="normal",
            model=data.model,
            private=data.private,
            attachments=[],
            budget={},
            replan_count=0,
        )
        await self._bus.emit(
            EventType.OBJECTIVE_CREATED,
            project_id=obj.project_id,
            objective_id=obj.id,
            actor="user",
            payload={"text": obj.text[:300], "run_mode": obj.run_mode, "private": obj.private},
        )
        self._spawn(obj.id, self._plan_then_maybe_run(obj.id))
        return obj

    async def get(self, objective_id: str) -> ObjectiveOut:
        return await self._objectives.get(objective_id)

    async def list_objectives(
        self, *, project_id: str | None = None, status: str | None = None, limit: int = 50
    ) -> list[ObjectiveOut]:
        return await self._objectives.list_objectives(project_id=project_id, status=status, limit=limit)

    async def detail(self, objective_id: str) -> ObjectiveDetail:
        obj = await self._objectives.get(objective_id)
        tasks = await self._tasks.list_for_objective(objective_id)
        events = await self._bus.query(
            EventFilter(objective_id=objective_id, types=frozenset({EventType.AGENT_MESSAGE.value})),
            limit=500,
        )
        messages: list[AgentMessage] = []
        for e in events:
            if "sender" in e.payload:
                try:
                    messages.append(AgentMessage.model_validate(e.payload))
                except ValueError:
                    continue
        return ObjectiveDetail(objective=obj, tasks=tasks, messages=messages)

    async def run(self, objective_id: str, body: ObjectiveRun) -> ObjectiveOut:
        obj = await self._objectives.get(objective_id)
        if obj.status is not ObjectiveStatus.AWAITING_PLAN_APPROVAL:
            raise ConflictError(
                f"Only a plan waiting for review can be started (this objective is {_label(obj.status)})."
            )
        obj = await self._objectives.update(objective_id, execution_mode=body.mode)
        await self._bus.emit(
            EventType.PLAN_APPROVED,
            project_id=obj.project_id,
            objective_id=obj.id,
            actor="user",
            payload={"mode": body.mode},
        )
        self._spawn(objective_id, self._orch.execute(objective_id))
        return obj

    async def edit_plan(self, objective_id: str, edit: PlanEdit) -> ObjectiveDetail:
        obj = await self._objectives.get(objective_id)
        if obj.status is not ObjectiveStatus.AWAITING_PLAN_APPROVAL or obj.plan is None:
            raise ConflictError("The plan can only be edited before it runs.")
        current = PlanResult.model_validate(
            {k: v for k, v in obj.plan.items() if k in PlanResult.model_fields}
        )
        proposed = current.model_copy(
            update={
                "tasks": edit.tasks,
                "completion_criteria": edit.completion_criteria or current.completion_criteria,
                "complexity": "large",  # a person's plan is not capped by the planner's own size estimate
            }
        )
        try:
            validated = validate_plan(
                proposed,
                await self._agents.list_all(),
                self._registry,
                disabled_tools=await self._rows.disabled_names(),
            )
        except PlanInvalid as exc:
            raise InvalidRequestError("The edited plan cannot run: " + "; ".join(exc.issues)) from exc
        await self._tasks.delete_for_objective(objective_id)
        await self._tasks.add(
            objective_id,
            obj.project_id,
            [
                NewTask(
                    key=t.key,
                    title=t.title,
                    description=t.description,
                    kind="work",
                    assigned_agent=t.agent,
                    depends_on=t.depends_on,
                    inputs={
                        "root_key": t.key,
                        "tools": t.tools,
                        "expected_outputs": t.expected_outputs,
                        "complexity": t.complexity,
                    },
                    approval_required=t.approval_required,
                    optional=t.optional,
                    review=t.review,
                )
                for t in validated.plan.tasks
            ],
        )
        plan_json = validated.plan.model_dump(mode="json")
        plan_json["complexity"] = current.complexity
        plan_json["warnings"] = validated.warnings
        plan_json["edited"] = True
        strategy = estimate(validated.plan)
        obj = await self._objectives.update(objective_id, plan=plan_json, strategy=strategy.to_json())
        await self._bus.emit(
            EventType.PLAN_EDITED,
            project_id=obj.project_id,
            objective_id=obj.id,
            actor="user",
            payload={"tasks": len(validated.plan.tasks), "strategy": strategy.name},
        )
        return await self.detail(objective_id)

    async def cancel(self, objective_id: str) -> ObjectiveOut:
        obj = await self._objectives.get(objective_id)
        if obj.status.terminal:
            return obj
        task = self._active.get(objective_id)
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            obj = await self._objectives.get(objective_id)
            if obj.status.terminal:
                return obj
        # Nothing is executing it (a plan awaiting review, or paused): close it and any parked runs.
        for t in await self._tasks.list_for_objective(objective_id):
            if t.run_id and not t.status.settled:
                run = await self._runs.get(t.run_id)
                if not run.status.terminal:
                    await self._runner.abandon(t.run_id)
        live = [
            TaskStatus.WAITING,
            TaskStatus.QUEUED,
            TaskStatus.RUNNING,
            TaskStatus.NEEDS_APPROVAL,
            TaskStatus.BLOCKED,
        ]
        await self._tasks.set_status_where(
            objective_id, live, TaskStatus.CANCELLED, completed_at=self._clock.now()
        )
        obj = await self._objectives.update(
            objective_id, status=ObjectiveStatus.CANCELLED, completed_at=self._clock.now()
        )
        await self._bus.emit(
            EventType.OBJECTIVE_CANCELLED,
            project_id=obj.project_id,
            objective_id=obj.id,
            actor="user",
            payload={},
        )
        return obj

    async def resume(self, objective_id: str) -> ObjectiveOut:
        obj = await self._objectives.get(objective_id)
        if obj.status is ObjectiveStatus.PAUSED:
            self._spawn(objective_id, self._orch.execute(objective_id))
        elif obj.status is ObjectiveStatus.RECEIVED:  # planning was interrupted
            self._spawn(objective_id, self._plan_then_maybe_run(objective_id))
        else:
            raise ConflictError(f"Only a paused objective can be resumed (this one is {_label(obj.status)}).")
        return obj

    # ---- tasks ----------------------------------------------------------------------------------
    async def get_task(self, task_id: str) -> TaskOut:
        return await self._tasks.get(task_id)

    async def _continue_after_task_change(self, task: TaskOut) -> None:
        obj = await self._objectives.get(task.objective_id)
        if obj.status in (ObjectiveStatus.PAUSED, ObjectiveStatus.RUNNING, ObjectiveStatus.VERIFYING):
            self._spawn(obj.id, self._orch.execute(obj.id))

    async def _reopen_dependents(self, task: TaskOut) -> None:
        tasks = await self._tasks.list_for_objective(task.objective_id)
        graph = TaskGraph.build(
            {t.id: [d for d in t.depends_on if d in {x.id for x in tasks}] for t in tasks}
        )
        by_id = {t.id: t for t in tasks}
        for tid in graph.descendants(task.id):
            t = by_id[tid]
            if t.status is TaskStatus.CANCELLED and (t.error or {}).get("code") == "dependency_failed":
                await self._tasks.update(tid, status=TaskStatus.WAITING, error=None, completed_at=None)

    def _require_open(self, obj: ObjectiveOut) -> None:
        if obj.status.terminal:
            raise ConflictError(f"This objective is already {_label(obj.status)}.")

    async def retry_task(self, task_id: str) -> TaskOut:
        task = await self._tasks.get(task_id)
        self._require_open(await self._objectives.get(task.objective_id))
        if task.status not in (TaskStatus.BLOCKED, TaskStatus.FAILED):
            raise ConflictError("Only a blocked or failed task can be retried.")
        if task.run_id:
            run = await self._runs.get(task.run_id)
            if not run.status.terminal and run.status is not RunStatus.INTERRUPTED:
                await self._runner.abandon(task.run_id)  # e.g. a question nobody will answer now
        task = await self._tasks.update(
            task_id, status=TaskStatus.QUEUED, attempts=0, resume=False, error=None, completed_at=None
        )
        await self._reopen_dependents(task)
        await self._bus.emit(
            EventType.TASK_RETRIED,
            project_id=task.project_id,
            objective_id=task.objective_id,
            task_id=task.id,
            actor="user",
            payload={"key": task.key, "by": "user"},
        )
        await self._continue_after_task_change(task)
        return task

    async def skip_task(self, task_id: str) -> TaskOut:
        task = await self._tasks.get(task_id)
        self._require_open(await self._objectives.get(task.objective_id))
        if task.status not in (TaskStatus.BLOCKED, TaskStatus.FAILED):
            raise ConflictError("Only a blocked or failed task can be skipped.")
        if task.run_id:
            run = await self._runs.get(task.run_id)
            if not run.status.terminal:
                await self._runner.abandon(task.run_id)
        task = await self._tasks.update(task_id, status=TaskStatus.SKIPPED, completed_at=self._clock.now())
        await self._reopen_dependents(task)
        await self._bus.emit(
            EventType.TASK_STATUS_CHANGED,
            project_id=task.project_id,
            objective_id=task.objective_id,
            task_id=task.id,
            actor="user",
            payload={"key": task.key, "status": "SKIPPED", "by": "user"},
        )
        await self._continue_after_task_change(task)
        return task

    async def answer_task(self, task_id: str, text: str) -> TaskOut:
        task = await self._tasks.get(task_id)
        self._require_open(await self._objectives.get(task.objective_id))
        if (
            task.status is not TaskStatus.BLOCKED
            or (task.error or {}).get("code") != "needs_input"
            or not task.run_id
        ):
            raise ConflictError("This task is not waiting for an answer.")
        try:
            await self._runner.prepare_resume(task.run_id, answer=text)
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        task = await self._tasks.update(task_id, status=TaskStatus.QUEUED, resume=True, error=None)
        await self._continue_after_task_change(task)
        return task

    # ---- startup and shutdown ------------------------------------------------------------------
    async def recover(self) -> list[ObjectiveOut]:
        """After a restart: in-flight tasks continue from their checkpoints once the person resumes."""
        for t in await self._tasks.running_anywhere():
            await self._tasks.update(t.id, status=TaskStatus.QUEUED, resume=bool(t.run_id))
        interrupted: list[ObjectiveOut] = []
        note = {
            "code": "interrupted",
            "message": "NEXUS stopped while this was running. Resume it to continue.",
        }
        for obj in await self._objectives.in_states(
            [ObjectiveStatus.RUNNING, ObjectiveStatus.VERIFYING, ObjectiveStatus.PLANNING]
        ):
            status = (
                ObjectiveStatus.RECEIVED if obj.status is ObjectiveStatus.PLANNING else ObjectiveStatus.PAUSED
            )
            if status is ObjectiveStatus.RECEIVED:
                await self._tasks.delete_for_objective(obj.id)  # a half-made plan is discarded, never run
            interrupted.append(await self._objectives.update(obj.id, status=status, error=note))
            await self._bus.emit(
                EventType.OBJECTIVE_PAUSED,
                project_id=obj.project_id,
                objective_id=obj.id,
                payload={"reason": "interrupted"},
            )
        if interrupted:
            await self._notifications.notify(
                "objective",
                "Objectives were interrupted",
                f"{len(interrupted)} objective(s) stopped when NEXUS restarted. Open them and press Resume.",
                ref={"objective_ids": [o.id for o in interrupted]},
            )
        return interrupted

    async def shutdown(self) -> None:
        self._orch.shutting_down = True
        self._runner.shutting_down = True
        tasks = list(self._active.values())
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def _label(status: ObjectiveStatus) -> str:
    return status.value.lower().replace("_", " ")
