"""Stored ideas, notes and to-dos. Returns DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from app.core.clock import Clock, SystemClock
from app.core.errors import NotFoundError
from app.core.ids import new_id
from app.models.database import Database
from app.models.ideas import Idea
from app.schemas.ideas import IdeaOut


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class IdeaStore:
    def __init__(self, db: Database, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()

    async def create(self, **fields: Any) -> IdeaOut:
        now = self._clock.now()
        async with self._db.session() as s:
            row = Idea(id=new_id("idea"), status="open", created_at=now, updated_at=now, **fields)
            s.add(row)
            await s.flush()
            return IdeaOut.model_validate(row)

    async def get(self, idea_id: str) -> IdeaOut:
        async with self._db.session() as s:
            row = await s.get(Idea, idea_id)
            if row is None:
                raise NotFoundError("That idea does not exist.")
            return IdeaOut.model_validate(row)

    async def update(self, idea_id: str, **fields: Any) -> IdeaOut:
        async with self._db.session() as s:
            row = await s.get(Idea, idea_id)
            if row is None:
                raise NotFoundError("That idea does not exist.")
            for k, v in fields.items():
                setattr(row, k, v)
            row.updated_at = self._clock.now()
            await s.flush()
            return IdeaOut.model_validate(row)

    async def delete(self, idea_id: str) -> IdeaOut:
        async with self._db.session() as s:
            row = await s.get(Idea, idea_id)
            if row is None:
                raise NotFoundError("That idea does not exist.")
            out = IdeaOut.model_validate(row)
            await s.delete(row)
            return out

    async def list_ideas(
        self,
        *,
        status: str | None = None,
        kind: str | None = None,
        project_id: str | None = None,
        pinned: bool | None = None,
        q: str | None = None,
        limit: int = 200,
    ) -> list[IdeaOut]:
        """Pinned first, then by due date (soonest first, undated last), then newest."""
        stmt = (
            select(Idea)
            .order_by(
                Idea.pinned.desc(),
                Idea.due_at.is_(None),
                Idea.due_at.asc(),
                Idea.created_at.desc(),
                Idea.id.desc(),
            )
            .limit(limit)
        )
        if status:
            stmt = stmt.where(Idea.status == status)
        if kind:
            stmt = stmt.where(Idea.kind == kind)
        if project_id:
            stmt = stmt.where(Idea.project_id == project_id)
        if pinned is not None:
            stmt = stmt.where(Idea.pinned.is_(pinned))
        if q and q.strip():
            stmt = stmt.where(Idea.text.ilike(f"%{_escape_like(q.strip())}%", escape="\\"))
        async with self._db.session() as s:
            return [IdeaOut.model_validate(r) for r in (await s.execute(stmt)).scalars()]

    async def due_unreminded(self, now: datetime) -> list[IdeaOut]:
        """Open items whose due time has come and that have not been reminded about yet."""
        stmt = (
            select(Idea)
            .where(
                Idea.status == "open",
                Idea.due_at.is_not(None),
                Idea.due_at <= now,
                Idea.reminded_at.is_(None),
            )
            .order_by(Idea.due_at)
        )
        async with self._db.session() as s:
            return [IdeaOut.model_validate(r) for r in (await s.execute(stmt)).scalars()]

    async def count_due(self, now: datetime) -> int:
        """Open items that are due (or overdue) now."""
        stmt = select(func.count()).where(Idea.status == "open", Idea.due_at.is_not(None), Idea.due_at <= now)
        async with self._db.session() as s:
            return int((await s.execute(stmt)).scalar_one())
