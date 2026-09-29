"""Stores for the objective aggregate. They own their sessions and return DTOs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, select, update

from app.core.clock import Clock, SystemClock
from app.core.errors import NotFoundError
from app.core.ids import new_id
from app.models.database import Database
from app.models.orchestration import Objective, Task, TaskDependency
from app.schemas.orchestration import ObjectiveOut, ObjectiveStatus, TaskOut, TaskStatus


@dataclass
class NewTask:
    """A task to insert. ``depends_on`` holds keys of tasks in the same objective (new or existing)."""

    key: str
    title: str
    description: str
    kind: str
    assigned_agent: str
    status: TaskStatus = TaskStatus.WAITING
    depends_on: list[str] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)
    approval_required: bool = False
    optional: bool = False
    review: bool = False
    round: int = 0
    parent_task_id: str | None = None
    max_attempts: int = 2


class ObjectiveStore:
    def __init__(self, db: Database, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()

    async def create(self, **fields: Any) -> ObjectiveOut:
        now = self._clock.now()
        async with self._db.session() as s:
            row = Objective(
                id=new_id("obj"),
                status=ObjectiveStatus.RECEIVED.value,
                created_at=now,
                updated_at=now,
                **fields,
            )
            s.add(row)
            await s.flush()
            return ObjectiveOut.model_validate(row)

    async def get(self, objective_id: str) -> ObjectiveOut:
        async with self._db.session() as s:
            row = await s.get(Objective, objective_id)
            if row is None:
                raise NotFoundError(f"Objective {objective_id} not found")
            return ObjectiveOut.model_validate(row)

    async def update(self, objective_id: str, **fields: Any) -> ObjectiveOut:
        async with self._db.session() as s:
            row = await s.get(Objective, objective_id)
            if row is None:
                raise NotFoundError(f"Objective {objective_id} not found")
            for k, v in fields.items():
                setattr(row, k, v.value if isinstance(v, ObjectiveStatus) else v)
            row.updated_at = self._clock.now()
            await s.flush()
            return ObjectiveOut.model_validate(row)

    async def list_objectives(
        self, *, project_id: str | None = None, status: str | None = None, limit: int = 50
    ) -> list[ObjectiveOut]:
        stmt = select(Objective).order_by(Objective.created_at.desc(), Objective.id.desc()).limit(limit)
        if project_id:
            stmt = stmt.where(Objective.project_id == project_id)
        if status:
            stmt = stmt.where(Objective.status == status)
        async with self._db.session() as s:
            return [ObjectiveOut.model_validate(r) for r in (await s.execute(stmt)).scalars().all()]

    async def in_states(self, states: Sequence[ObjectiveStatus]) -> list[ObjectiveOut]:
        async with self._db.session() as s:
            rows = (
                (await s.execute(select(Objective).where(Objective.status.in_([x.value for x in states]))))
                .scalars()
                .all()
            )
            return [ObjectiveOut.model_validate(r) for r in rows]


def _task_out(row: Task, deps: list[str]) -> TaskOut:
    out = TaskOut.model_validate(row)
    return out.model_copy(update={"depends_on": deps})


class TaskStore:
    def __init__(self, db: Database, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()

    async def add(self, objective_id: str, project_id: str, tasks: Sequence[NewTask]) -> list[TaskOut]:
        """Insert tasks and their dependencies in one transaction. Keys may refer to existing tasks."""
        now = self._clock.now()
        async with self._db.session() as s:
            existing = {
                r.key: r.id
                for r in (await s.execute(select(Task).where(Task.objective_id == objective_id)))
                .scalars()
                .all()
            }
            ids = dict(existing)
            rows: list[Task] = []
            for t in tasks:
                if t.key in ids:
                    raise ValueError(f"task key {t.key!r} already exists in this objective")
                row = Task(
                    id=new_id("task"),
                    objective_id=objective_id,
                    project_id=project_id,
                    key=t.key,
                    title=t.title,
                    description=t.description,
                    kind=t.kind,
                    assigned_agent=t.assigned_agent,
                    status=t.status.value,
                    inputs=t.inputs,
                    attempts=0,
                    max_attempts=t.max_attempts,
                    approval_required=t.approval_required,
                    optional=t.optional,
                    review=t.review,
                    round=t.round,
                    parent_task_id=t.parent_task_id,
                    resume=False,
                    created_at=now,
                )
                ids[t.key] = row.id
                rows.append(row)
                s.add(row)
            await s.flush()
            for t, row in zip(tasks, rows, strict=True):
                for key in dict.fromkeys(t.depends_on):
                    if key not in ids:
                        raise ValueError(f"task {t.key!r} depends on unknown task {key!r}")
                    s.add(TaskDependency(task_id=row.id, depends_on_id=ids[key]))
            await s.flush()
            return [
                _task_out(r, [ids[k] for k in dict.fromkeys(t.depends_on)])
                for t, r in zip(tasks, rows, strict=True)
            ]

    async def list_for_objective(self, objective_id: str) -> list[TaskOut]:
        async with self._db.session() as s:
            rows = (
                (
                    await s.execute(
                        select(Task)
                        .where(Task.objective_id == objective_id)
                        .order_by(Task.created_at, Task.id)
                    )
                )
                .scalars()
                .all()
            )
            ids = [r.id for r in rows]
            deps: dict[str, list[str]] = {i: [] for i in ids}
            if ids:
                for d in (
                    await s.execute(select(TaskDependency).where(TaskDependency.task_id.in_(ids)))
                ).scalars():
                    deps[d.task_id].append(d.depends_on_id)
            return [_task_out(r, sorted(deps[r.id])) for r in rows]

    async def get(self, task_id: str) -> TaskOut:
        async with self._db.session() as s:
            row = await s.get(Task, task_id)
            if row is None:
                raise NotFoundError(f"Task {task_id} not found")
            deps = [
                d.depends_on_id
                for d in (
                    await s.execute(select(TaskDependency).where(TaskDependency.task_id == task_id))
                ).scalars()
            ]
            return _task_out(row, sorted(deps))

    async def update(self, task_id: str, **fields: Any) -> TaskOut:
        async with self._db.session() as s:
            row = await s.get(Task, task_id)
            if row is None:
                raise NotFoundError(f"Task {task_id} not found")
            for k, v in fields.items():
                setattr(row, k, v.value if isinstance(v, TaskStatus) else v)
            await s.flush()
        return await self.get(task_id)

    async def rewire(
        self, *, objective_id: str, old_dep: str, new_dep: str, only_waiting: bool = True
    ) -> int:
        """Point every (waiting) task that depended on ``old_dep`` at ``new_dep`` instead."""
        async with self._db.session() as s:
            q = (
                select(TaskDependency)
                .join(Task, Task.id == TaskDependency.task_id)
                .where(
                    TaskDependency.depends_on_id == old_dep,
                    Task.objective_id == objective_id,
                    Task.id != new_dep,
                )
            )
            if only_waiting:
                q = q.where(Task.status.in_([TaskStatus.WAITING.value, TaskStatus.QUEUED.value]))
            moved = 0
            for d in list((await s.execute(q)).scalars()):
                task_id = d.task_id
                await s.delete(d)
                await s.flush()
                exists = await s.get(TaskDependency, (task_id, new_dep))
                if exists is None:
                    s.add(TaskDependency(task_id=task_id, depends_on_id=new_dep))
                moved += 1
            await s.flush()
            return moved

    async def set_status_where(
        self, objective_id: str, from_states: Sequence[TaskStatus], to: TaskStatus, **fields: Any
    ) -> int:
        async with self._db.session() as s:
            result = await s.execute(
                update(Task)
                .where(Task.objective_id == objective_id, Task.status.in_([x.value for x in from_states]))
                .values(status=to.value, **fields)
            )
            return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def delete_for_objective(self, objective_id: str) -> None:
        async with self._db.session() as s:
            ids = [
                r
                for r in (await s.execute(select(Task.id).where(Task.objective_id == objective_id))).scalars()
            ]
            if ids:
                await s.execute(delete(TaskDependency).where(TaskDependency.task_id.in_(ids)))
                await s.execute(delete(Task).where(Task.id.in_(ids)))

    async def running_anywhere(self) -> list[TaskOut]:
        """Tasks that were in flight (for startup recovery)."""
        live = [TaskStatus.RUNNING.value, TaskStatus.NEEDS_APPROVAL.value]
        async with self._db.session() as s:
            rows = (await s.execute(select(Task).where(Task.status.in_(live)))).scalars().all()
            return [_task_out(r, []) for r in rows]
