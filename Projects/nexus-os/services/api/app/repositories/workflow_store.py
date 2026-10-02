"""Stores for workflows, their runs and schedules. They own their sessions and return DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.core.clock import Clock, SystemClock
from app.core.errors import NotFoundError
from app.core.ids import new_id
from app.models.database import Database
from app.models.workflows import Schedule, Workflow, WorkflowRun, WorkflowVersion
from app.schemas.workflows import (
    ScheduleOut,
    WorkflowDefinition,
    WorkflowOut,
    WorkflowRunOut,
    WorkflowRunStatus,
    WorkflowVersionOut,
)


class WorkflowStore:
    def __init__(self, db: Database, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()

    async def create(
        self, *, project_id: str, name: str, description: str, definition: WorkflowDefinition
    ) -> WorkflowOut:
        now = self._clock.now()
        data = definition.model_dump(mode="json")
        async with self._db.session() as s:
            row = Workflow(
                id=new_id("wf"),
                project_id=project_id,
                name=name,
                description=description,
                version=1,
                enabled=True,
                definition=data,
                deleted=False,
                created_at=now,
                updated_at=now,
            )
            s.add(row)
            s.add(WorkflowVersion(workflow_id=row.id, version=1, definition=data, created_at=now))
            await s.flush()
            return WorkflowOut.model_validate(row)

    async def get(self, workflow_id: str, *, include_deleted: bool = False) -> WorkflowOut:
        async with self._db.session() as s:
            row = await s.get(Workflow, workflow_id)
            if row is None or (row.deleted and not include_deleted):
                raise NotFoundError("That workflow does not exist.")
            return WorkflowOut.model_validate(row)

    async def list_workflows(self, *, project_id: str | None = None) -> list[WorkflowOut]:
        q = select(Workflow).where(Workflow.deleted.is_(False)).order_by(Workflow.updated_at.desc())
        if project_id:
            q = q.where(Workflow.project_id == project_id)
        async with self._db.session() as s:
            return [WorkflowOut.model_validate(r) for r in (await s.execute(q)).scalars()]

    async def update(
        self, workflow_id: str, *, definition: WorkflowDefinition | None = None, **fields: Any
    ) -> WorkflowOut:
        """Change fields; a changed definition becomes a new version (the old one is kept)."""
        now = self._clock.now()
        async with self._db.session() as s:
            row = await s.get(Workflow, workflow_id)
            if row is None or row.deleted:
                raise NotFoundError("That workflow does not exist.")
            for k, v in fields.items():
                setattr(row, k, v)
            if definition is not None:
                data = definition.model_dump(mode="json")
                if data != row.definition:
                    row.version += 1
                    row.definition = data
                    s.add(
                        WorkflowVersion(
                            workflow_id=row.id, version=row.version, definition=data, created_at=now
                        )
                    )
            row.updated_at = now
            await s.flush()
            return WorkflowOut.model_validate(row)

    async def versions(self, workflow_id: str) -> list[WorkflowVersionOut]:
        q = (
            select(WorkflowVersion)
            .where(WorkflowVersion.workflow_id == workflow_id)
            .order_by(WorkflowVersion.version.desc())
        )
        async with self._db.session() as s:
            return [WorkflowVersionOut.model_validate(r) for r in (await s.execute(q)).scalars()]

    async def definition_at(self, workflow_id: str, version: int) -> WorkflowDefinition:
        async with self._db.session() as s:
            row = await s.get(WorkflowVersion, (workflow_id, version))
            if row is None:
                raise NotFoundError(f"Version {version} of this workflow does not exist.")
            return WorkflowDefinition.model_validate(row.definition)


class WorkflowRunStore:
    def __init__(self, db: Database, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()

    async def create(self, **fields: Any) -> WorkflowRunOut:
        async with self._db.session() as s:
            row = WorkflowRun(
                id=new_id("wfr"),
                status=WorkflowRunStatus.RUNNING.value,
                started_at=self._clock.now(),
                outputs={},
                error=None,
                **fields,
            )
            s.add(row)
            await s.flush()
            return WorkflowRunOut.model_validate(row)

    async def get(self, run_id: str) -> WorkflowRunOut:
        async with self._db.session() as s:
            row = await s.get(WorkflowRun, run_id)
            if row is None:
                raise NotFoundError("That workflow run does not exist.")
            return WorkflowRunOut.model_validate(row)

    async def update(self, run_id: str, **fields: Any) -> WorkflowRunOut:
        async with self._db.session() as s:
            row = await s.get(WorkflowRun, run_id)
            if row is None:
                raise NotFoundError("That workflow run does not exist.")
            for k, v in fields.items():
                setattr(row, k, v.value if isinstance(v, WorkflowRunStatus) else v)
            await s.flush()
            return WorkflowRunOut.model_validate(row)

    async def list_runs(
        self,
        *,
        workflow_id: str | None = None,
        project_id: str | None = None,
        statuses: tuple[str, ...] = (),
        limit: int = 50,
    ) -> list[WorkflowRunOut]:
        q = select(WorkflowRun).order_by(WorkflowRun.started_at.desc(), WorkflowRun.id.desc()).limit(limit)
        if workflow_id:
            q = q.where(WorkflowRun.workflow_id == workflow_id)
        if project_id:
            q = q.where(WorkflowRun.project_id == project_id)
        if statuses:
            q = q.where(WorkflowRun.status.in_(statuses))
        async with self._db.session() as s:
            return [WorkflowRunOut.model_validate(r) for r in (await s.execute(q)).scalars()]


class ScheduleStore:
    def __init__(self, db: Database, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()

    async def create(self, **fields: Any) -> ScheduleOut:
        async with self._db.session() as s:
            row = Schedule(id=new_id("sch"), created_at=self._clock.now(), **fields)
            s.add(row)
            await s.flush()
            return ScheduleOut.model_validate(row)

    async def get(self, schedule_id: str) -> ScheduleOut:
        async with self._db.session() as s:
            row = await s.get(Schedule, schedule_id)
            if row is None:
                raise NotFoundError("That schedule does not exist.")
            return ScheduleOut.model_validate(row)

    async def update(self, schedule_id: str, **fields: Any) -> ScheduleOut:
        async with self._db.session() as s:
            row = await s.get(Schedule, schedule_id)
            if row is None:
                raise NotFoundError("That schedule does not exist.")
            for k, v in fields.items():
                setattr(row, k, v)
            await s.flush()
            return ScheduleOut.model_validate(row)

    async def delete(self, schedule_id: str) -> None:
        async with self._db.session() as s:
            row = await s.get(Schedule, schedule_id)
            if row is None:
                raise NotFoundError("That schedule does not exist.")
            await s.delete(row)

    async def list_schedules(self, *, workflow_id: str | None = None) -> list[ScheduleOut]:
        q = select(Schedule).order_by(Schedule.created_at)
        if workflow_id:
            q = q.where(Schedule.workflow_id == workflow_id)
        async with self._db.session() as s:
            return [ScheduleOut.model_validate(r) for r in (await s.execute(q)).scalars()]

    async def due(self, now: datetime) -> list[ScheduleOut]:
        q = (
            select(Schedule)
            .where(Schedule.enabled.is_(True), Schedule.next_run_at <= now)
            .order_by(Schedule.next_run_at)
        )
        async with self._db.session() as s:
            return [ScheduleOut.model_validate(r) for r in (await s.execute(q)).scalars()]
