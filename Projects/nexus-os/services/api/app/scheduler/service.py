"""Scheduler: starts workflow runs on cron schedules, unattended.

- Ticks in-process (every ``tick_s``); ``tick(now)`` is callable directly, so tests need no waiting.
- Runs it starts are *unattended*: high-risk actions are never auto-approved; they wait for a person.
- Missed times (the app was closed) collapse into one catch-up run, then the schedule moves on.
- A firing is skipped while the schedule's previous run is still going, so runs never pile up.
- Every firing or skip is an event, with the reason.
- Other time-based jobs (to-do reminders) ride on the same tick through ``also_on_tick``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime

from app.core.clock import Clock, SystemClock
from app.core.errors import InvalidRequestError, NexusError, NotFoundError
from app.events.bus import EventBus
from app.events.types import EventType
from app.repositories.workflow_store import ScheduleStore, WorkflowRunStore
from app.scheduler import cron
from app.schemas.workflows import CronPreview, ScheduleCreate, ScheduleOut, ScheduleUpdate
from app.workflows.service import WorkflowService, coerce_inputs

log = logging.getLogger(__name__)

TICK_S = 30.0


class Scheduler:
    def __init__(
        self,
        *,
        schedules: ScheduleStore,
        runs: WorkflowRunStore,
        workflows: WorkflowService,
        bus: EventBus,
        clock: Clock | None = None,
        tick_s: float = TICK_S,
        also_on_tick: Sequence[Callable[[datetime], Awaitable[object]]] = (),
    ) -> None:
        self._schedules = schedules
        self._runs = runs
        self._workflows = workflows
        self._bus = bus
        self._clock = clock or SystemClock()
        self._tick_s = tick_s
        self._also_on_tick = list(also_on_tick)
        self._task: asyncio.Task[None] | None = None

    # ======================================================================= schedules
    @staticmethod
    def _spec(expression: str, tz: str) -> cron.CronSpec:
        try:
            spec = cron.parse(expression)
            cron.zone(tz)
            return spec
        except cron.CronError as exc:
            raise InvalidRequestError(str(exc)) from None

    def preview(self, expression: str, tz: str = "UTC", count: int = 5) -> CronPreview:
        spec = self._spec(expression, tz)
        try:
            runs = cron.upcoming(spec, self._clock.now(), tz, count)
        except cron.CronError as exc:
            raise InvalidRequestError(str(exc)) from None
        return CronPreview(description=cron.describe(spec), next_runs=runs)

    async def create(self, body: ScheduleCreate) -> ScheduleOut:
        wf = await self._workflows.get(body.workflow_id)
        spec = self._spec(body.cron, body.timezone)
        inputs = coerce_inputs(wf.definition, body.inputs)
        row = await self._schedules.create(
            workflow_id=wf.id,
            cron=body.cron.strip(),
            timezone=body.timezone,
            inputs=inputs,
            enabled=body.enabled,
            next_run_at=cron.next_after(spec, self._clock.now(), body.timezone) if body.enabled else None,
        )
        await self._emit(EventType.SCHEDULE_CREATED, wf.project_id, row, {"description": cron.describe(spec)})
        return await self._enrich(row)

    async def update(self, schedule_id: str, body: ScheduleUpdate) -> ScheduleOut:
        current = await self._schedules.get(schedule_id)
        wf = await self._workflows.get(current.workflow_id)
        expression = body.cron.strip() if body.cron is not None else current.cron
        tz = body.timezone if body.timezone is not None else current.timezone
        spec = self._spec(expression, tz)
        enabled = body.enabled if body.enabled is not None else current.enabled
        fields: dict[str, object] = {
            "cron": expression,
            "timezone": tz,
            "enabled": enabled,
            "next_run_at": cron.next_after(spec, self._clock.now(), tz) if enabled else None,
        }
        if body.inputs is not None:
            fields["inputs"] = coerce_inputs(wf.definition, body.inputs)
        row = await self._schedules.update(schedule_id, **fields)
        await self._emit(EventType.SCHEDULE_UPDATED, wf.project_id, row, {"enabled": enabled})
        return await self._enrich(row)

    async def delete(self, schedule_id: str) -> None:
        row = await self._schedules.get(schedule_id)
        await self._schedules.delete(schedule_id)
        project_id = None
        with contextlib.suppress(NotFoundError):
            project_id = (await self._workflows.get(row.workflow_id)).project_id
        await self._emit(EventType.SCHEDULE_DELETED, project_id, row, {})

    async def list_schedules(self, workflow_id: str | None = None) -> list[ScheduleOut]:
        return [await self._enrich(s) for s in await self._schedules.list_schedules(workflow_id=workflow_id)]

    async def run_now(self, schedule_id: str) -> ScheduleOut:
        row = await self._schedules.get(schedule_id)
        await self._fire(row, self._clock.now(), manual=True)
        return await self._enrich(await self._schedules.get(schedule_id))

    # ======================================================================= ticking
    async def tick(self, now: datetime | None = None) -> list[str]:
        """Start every due schedule once. Returns the ids of the runs started."""
        now = now or self._clock.now()
        started: list[str] = []
        for row in await self._schedules.due(now):
            run_id = await self._fire(row, now)
            if run_id:
                started.append(run_id)
        for job in self._also_on_tick:
            try:
                await job(now)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("scheduled job %s failed", getattr(job, "__qualname__", job))
        return started

    async def _fire(self, row: ScheduleOut, now: datetime, *, manual: bool = False) -> str | None:
        spec = cron.parse(row.cron)
        next_at = cron.next_after(spec, now, row.timezone) if row.enabled else None
        project_id: str | None = None
        try:
            wf = await self._workflows.get(row.workflow_id)
            project_id = wf.project_id
            if row.last_run_id and not manual:
                previous = await self._runs.get(row.last_run_id)
                if not previous.status.terminal:
                    return await self._skip(row, project_id, next_at, "the previous run is still going")
            if not wf.enabled:
                return await self._skip(row, project_id, next_at, "the workflow is turned off")
            run = await self._workflows.start(wf.id, dict(row.inputs), unattended=True, schedule_id=row.id)
        except NotFoundError:
            return await self._skip(
                row,
                project_id,
                None,
                "the workflow no longer exists; the schedule was turned off",
                status="WORKFLOW_GONE",
                disable=True,
            )
        except NexusError as exc:
            return await self._skip(row, project_id, next_at, exc.message)
        await self._schedules.update(
            row.id, last_run_at=now, last_run_id=run.id, last_status="STARTED", next_run_at=next_at
        )
        await self._emit(
            EventType.SCHEDULE_FIRED,
            project_id,
            row,
            {
                "workflow_run_id": run.id,
                "manual": manual,
                "late_by_s": int((now - row.next_run_at).total_seconds())
                if row.next_run_at and not manual
                else 0,
            },
        )
        return run.id

    async def _skip(
        self,
        row: ScheduleOut,
        project_id: str | None,
        next_at: datetime | None,
        reason: str,
        *,
        status: str = "SKIPPED",
        disable: bool = False,
    ) -> str | None:
        """Record a skipped firing. Returns None (no run was started), so callers can return it."""
        extra = {"enabled": False} if disable else {}
        await self._schedules.update(row.id, next_run_at=next_at, last_status=status, **extra)
        await self._emit(EventType.SCHEDULE_SKIPPED, project_id, row, {"reason": reason})
        return None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="scheduler")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("scheduler tick failed")
            await asyncio.sleep(self._tick_s)

    # ======================================================================= helpers
    async def _enrich(self, row: ScheduleOut) -> ScheduleOut:
        description = cron.describe(cron.parse(row.cron))
        status = row.last_status
        if row.last_run_id and status == "STARTED":
            with contextlib.suppress(NotFoundError):
                status = (await self._runs.get(row.last_run_id)).status.value
        return row.model_copy(update={"description": description, "last_status": status})

    async def _emit(
        self, type_: EventType, project_id: str | None, row: ScheduleOut, extra: dict[str, object]
    ) -> None:
        await self._bus.emit(
            type_,
            project_id=project_id,
            actor="scheduler",
            payload={"schedule_id": row.id, "workflow_id": row.workflow_id, "cron": row.cron, **extra},
        )
