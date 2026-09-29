"""Event persistence. Append-only; the hash chain is maintained by the EventBus."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.foundation import Event
from app.schemas.events import EventRecord


@dataclass(frozen=True)
class EventFilter:
    """``project_id=None`` means *all projects*. Use ``global_only`` for the project-less chain."""

    project_id: str | None = None
    objective_id: str | None = None
    task_id: str | None = None
    run_id: str | None = None
    types: frozenset[str] | None = None
    global_only: bool = False

    def matches(self, record: EventRecord) -> bool:
        if self.global_only and record.project_id is not None:
            return False
        if self.project_id is not None and record.project_id != self.project_id:
            return False
        if self.objective_id is not None and record.objective_id != self.objective_id:
            return False
        if self.task_id is not None and record.task_id != self.task_id:
            return False
        if self.run_id is not None and record.run_id != self.run_id:
            return False
        return not (self.types is not None and record.type not in self.types)


def to_record(row: Event) -> EventRecord:
    return EventRecord(
        seq=row.seq,
        id=row.id,
        ts=row.ts,
        type=row.type,
        project_id=row.project_id,
        objective_id=row.objective_id,
        task_id=row.task_id,
        run_id=row.run_id,
        agent_id=row.agent_id,
        actor=row.actor,
        payload=row.payload,
        prev_hash=row.prev_hash,
        hash=row.hash,
    )


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def last_hash(self, project_id: str | None) -> str | None:
        stmt = select(Event.hash).order_by(Event.seq.desc()).limit(1)
        stmt = stmt.where(
            Event.project_id.is_(None) if project_id is None else Event.project_id == project_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def insert(self, row: Event) -> Event:
        self.session.add(row)
        await self.session.flush()
        return row

    async def query(
        self, flt: EventFilter, *, after_seq: int = 0, limit: int = 200, newest_first: bool = False
    ) -> list[EventRecord]:
        stmt = select(Event)
        if flt.global_only:
            stmt = stmt.where(Event.project_id.is_(None))
        if flt.project_id is not None:
            stmt = stmt.where(Event.project_id == flt.project_id)
        if flt.objective_id is not None:
            stmt = stmt.where(Event.objective_id == flt.objective_id)
        if flt.task_id is not None:
            stmt = stmt.where(Event.task_id == flt.task_id)
        if flt.run_id is not None:
            stmt = stmt.where(Event.run_id == flt.run_id)
        if flt.types:
            stmt = stmt.where(Event.type.in_(sorted(flt.types)))
        if newest_first:
            stmt = stmt.order_by(Event.seq.desc()).limit(limit)
            if after_seq:
                stmt = stmt.where(Event.seq > after_seq)
        else:
            stmt = stmt.where(Event.seq > after_seq).order_by(Event.seq.asc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [to_record(r) for r in rows]

    async def latest_seq(self) -> int:
        value = (await self.session.execute(select(func.max(Event.seq)))).scalar_one_or_none()
        return int(value or 0)

    async def chain_ids(self) -> Sequence[str | None]:
        rows = (await self.session.execute(select(Event.project_id).distinct())).scalars().all()
        return list(rows)

    async def chain(self, project_id: str | None, *, after_seq: int, limit: int) -> list[Event]:
        stmt = select(Event).where(Event.seq > after_seq)
        stmt = stmt.where(
            Event.project_id.is_(None) if project_id is None else Event.project_id == project_id
        )
        stmt = stmt.order_by(Event.seq.asc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def counts_by_type(self, *, since_seq: int = 0) -> dict[str, int]:
        stmt = select(Event.type, func.count()).where(Event.seq > since_seq).group_by(Event.type)
        return {t: int(c) for t, c in (await self.session.execute(stmt)).all()}
