"""AgentService: agent CRUD and the lifecycle of runs (start, answer, resume, cancel, recover).

Runs execute as plain asyncio tasks owned here. They are not put on the bounded job queue because a
run parked on an approval can wait for a day and must not hold a worker slot.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.agents.builtin import BUILTIN_AGENTS
from app.agents.runner import AgentRunner, RunRequest
from app.core.clock import Clock, SystemClock
from app.core.errors import ConflictError, NotFoundError
from app.events.bus import EventBus
from app.events.types import EventType
from app.permissions.approvals import ApprovalService
from app.providers.router import TaskClass
from app.repositories.runtime_store import AgentStore, RunStore, ToolCallStore
from app.schemas.agents import AgentCreate, AgentDefinition, AgentUpdate
from app.schemas.runtime import AgentRunOut, AgentRunRequest, RunStatus, ToolCallOut
from app.services.notifications import NotificationService
from app.services.projects import ProjectService
from app.services.settings import SettingsService

log = logging.getLogger(__name__)
MAX_ACTIVE_RUNS = 8
CODING_AGENTS = frozenset({"coder"})
PLANNING_AGENTS = frozenset({"planner", "orchestrator"})
DOCUMENT_AGENTS = frozenset({"writer", "researcher"})


def task_class_for(agent: AgentDefinition) -> TaskClass:
    """Which tier of model suits this agent's work (the router turns it into a model)."""
    if agent.slug in CODING_AGENTS:
        return TaskClass.CODING
    if agent.slug in PLANNING_AGENTS:
        return TaskClass.PLANNING
    if agent.slug in DOCUMENT_AGENTS:
        return TaskClass.LONG_DOCUMENT
    return TaskClass.GENERAL


class AgentService:
    def __init__(
        self,
        *,
        agents: AgentStore,
        runs: RunStore,
        tool_calls: ToolCallStore,
        runner: AgentRunner,
        approvals: ApprovalService,
        projects: ProjectService,
        settings: SettingsService,
        notifications: NotificationService,
        bus: EventBus,
        clock: Clock | None = None,
    ) -> None:
        self._agents = agents
        self._runs = runs
        self._tool_calls = tool_calls
        self._runner = runner
        self._approvals = approvals
        self._projects = projects
        self._settings = settings
        self._notifications = notifications
        self._bus = bus
        self._clock = clock or SystemClock()
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    # ---- agents ------------------------------------------------------------------------
    async def sync_builtins(self) -> None:
        for agent in BUILTIN_AGENTS:
            await self._agents.upsert_builtin(agent)

    async def list_agents(self) -> list[AgentDefinition]:
        return await self._agents.list_all()

    async def get_agent(self, id_or_slug: str) -> AgentDefinition:
        return await self._agents.get(id_or_slug)

    async def create_agent(self, data: AgentCreate) -> AgentDefinition:
        agent = await self._agents.create(data)
        await self._bus.emit(
            EventType.AGENT_CREATED,
            agent_id=agent.id,
            actor="user",
            payload={"slug": agent.slug, "name": agent.name},
        )
        return agent

    async def update_agent(self, id_or_slug: str, patch: AgentUpdate) -> AgentDefinition:
        agent = await self._agents.update(id_or_slug, patch)
        await self._bus.emit(
            EventType.AGENT_UPDATED,
            agent_id=agent.id,
            actor="user",
            payload={"slug": agent.slug, "changed": sorted(patch.model_dump(exclude_unset=True))},
        )
        return agent

    async def delete_agent(self, id_or_slug: str) -> None:
        agent = await self._agents.get(id_or_slug)
        await self._agents.delete(id_or_slug)
        await self._bus.emit(
            EventType.AGENT_UPDATED,
            agent_id=agent.id,
            actor="user",
            payload={"slug": agent.slug, "deleted": True},
        )

    # ---- runs --------------------------------------------------------------------------
    def active_run_ids(self) -> list[str]:
        return [rid for rid, t in self._tasks.items() if not t.done()]

    def _spawn(self, run_id: str, coro: Any) -> None:
        if len(self.active_run_ids()) >= MAX_ACTIVE_RUNS:
            coro.close()
            raise ConflictError(
                f"{MAX_ACTIVE_RUNS} agent runs are already in progress. Wait for one to finish, or cancel one."
            )
        task = asyncio.create_task(self._supervise(run_id, coro), name=f"agent-run-{run_id}")
        self._tasks[run_id] = task
        task.add_done_callback(self._forget(run_id))

    def _forget(self, run_id: str) -> Any:
        def done(task: asyncio.Task[Any]) -> None:
            if self._tasks.get(run_id) is task:
                del self._tasks[run_id]

        return done

    async def _supervise(self, run_id: str, coro: Any) -> None:
        try:
            outcome = await coro
        except asyncio.CancelledError:
            raise
        except Exception:  # the runner already records failures; this is the last line of defence
            log.exception("run %s failed outside the runner", run_id)
            await self._runs.finish(
                run_id,
                RunStatus.FAILED,
                error={"category": "UNKNOWN", "code": "internal_error", "message": "The run crashed."},
            )
            return
        if outcome.status is RunStatus.COMPLETED:
            await self._notify(
                outcome.run, "finished", (outcome.result.summary if outcome.result else "")[:200]
            )
        elif outcome.status is RunStatus.WAITING_INPUT:
            await self._notify(outcome.run, "has a question", (outcome.question or "")[:200])
        elif outcome.status in (RunStatus.FAILED, RunStatus.TIMED_OUT):
            message = (outcome.run.error or {}).get("message", "The run did not finish.")
            await self._notify(outcome.run, "stopped", str(message)[:200])

    async def _notify(self, run: AgentRunOut, title: str, body: str) -> None:
        try:
            agent = await self._agents.get(run.agent_id)
            await self._notifications.notify(
                "agent",
                f"{agent.name} {title}",
                body,
                project_id=run.project_id,
                ref={"run_id": run.id, "agent_id": agent.id},
            )
        except Exception:
            log.exception("could not create a notification for run %s", run.id)

    async def start_run(self, req: AgentRunRequest) -> AgentRunOut:
        project = await self._projects.get(req.project_id)
        if project.status == "archived":
            raise ConflictError("This project is archived. Restore it before running agents.")
        agent = await self._agents.get(req.agent)
        if agent.status == "disabled":
            raise ConflictError(f"{agent.name} is disabled. Enable it in Agents first.")
        level = project.settings.permission_level or await self._settings.default_permission_level()
        run = await self._runner.create(
            RunRequest(
                agent=agent,
                project_id=project.id,
                prompt=req.prompt,
                model=req.model,
                private=req.private,
                permission_level=level,
                task_class=task_class_for(agent),
            )
        )
        try:
            self._spawn(run.id, self._runner.execute(run.id, agent=agent))
        except ConflictError:
            await self._runs.finish(
                run.id,
                RunStatus.CANCELLED,
                error={"code": "not_started", "message": "Too many runs in progress."},
            )
            raise
        return run

    async def answer(self, run_id: str, text: str) -> AgentRunOut:
        run = await self._runs.get(run_id)
        if run.status is not RunStatus.WAITING_INPUT:
            raise ConflictError("This run is not waiting for an answer.")
        if run_id in self.active_run_ids():
            raise ConflictError("This run is still working.")
        return await self._continue(run_id, answer=text)

    async def resume(self, run_id: str) -> AgentRunOut:
        run = await self._runs.get(run_id)
        if run.status not in (RunStatus.INTERRUPTED, RunStatus.FAILED, RunStatus.TIMED_OUT):
            raise ConflictError(
                f"A run that is {run.status.value.lower().replace('_', ' ')} cannot be resumed."
            )
        if run_id in self.active_run_ids():
            raise ConflictError("This run is still working.")
        return await self._continue(run_id)

    async def _continue(self, run_id: str, *, answer: str | None = None) -> AgentRunOut:
        if len(self.active_run_ids()) >= MAX_ACTIVE_RUNS:
            raise ConflictError(
                f"{MAX_ACTIVE_RUNS} agent runs are already in progress. Wait for one to finish, or cancel one."
            )
        try:
            reopened = await self._runner.prepare_resume(run_id, answer=answer)
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        self._spawn(run_id, self._runner.execute(run_id))
        return reopened

    async def cancel(self, run_id: str) -> AgentRunOut:
        run = await self._runs.get(run_id)
        if run.status.terminal:
            return run
        task = self._tasks.get(run_id)
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            return await self._runs.get(run_id)
        return await self._runner.abandon(run_id)  # nothing is executing it: close it directly

    async def get_run(self, run_id: str) -> AgentRunOut:
        return await self._runs.get(run_id)

    async def list_runs(
        self,
        *,
        project_id: str | None = None,
        agent_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[AgentRunOut]:
        if agent_id:
            agent_id = (await self._agents.get(agent_id)).id
        return await self._runs.list_runs(
            project_id=project_id, agent_id=agent_id, status=status, limit=limit
        )

    async def run_detail(self, run_id: str) -> tuple[AgentRunOut, list[dict[str, Any]], list[ToolCallOut]]:
        run = await self._runs.get(run_id)
        _, steps = await self._runs.snapshot(run_id)
        calls = await self._tool_calls.list_calls(run_id=run_id, limit=200)
        return run, steps, list(reversed(calls))

    async def wait_for(self, run_id: str, timeout_s: float = 30.0) -> AgentRunOut:
        """Testing and orchestration helper: block until the run's task ends (a parked run keeps waiting)."""
        task = self._tasks.get(run_id)
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), timeout_s)
        return await self._runs.get(run_id)

    # ---- startup and shutdown ----------------------------------------------------------
    async def recover(self) -> list[AgentRunOut]:
        """After a restart nothing is executing: mark open runs interrupted and clear what cannot resume."""
        interrupted = await self._runs.mark_interrupted()
        ids = [r.id for r in interrupted]
        if ids:
            await self._approvals.cancel_for_runs(ids, "The app restarted before this was answered")
            await self._tool_calls.close_open(
                ids, "interrupted", "The app restarted while this was in flight."
            )
        for run in interrupted:
            await self._bus.emit(
                EventType.AGENT_INTERRUPTED,
                project_id=run.project_id,
                run_id=run.id,
                agent_id=run.agent_id,
                payload={"steps": run.step_count, "resumable": True},
            )
        if interrupted:
            await self._notifications.notify(
                "agent",
                "Agent runs were interrupted",
                f"{len(interrupted)} run(s) were cut off by a restart. Resume them from Agents.",
                ref={"run_ids": ids},
            )
        return interrupted

    async def shutdown(self) -> None:
        """Stop cleanly: running runs are parked as INTERRUPTED (resumable), not cancelled."""
        self._runner.shutting_down = True
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


__all__ = ["AgentService", "NotFoundError", "task_class_for"]
