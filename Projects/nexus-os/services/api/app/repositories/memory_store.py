"""Store for memory items and their embeddings. Owns its sessions and returns DTOs."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, delete, func, or_, select, update

from app.core.clock import Clock, SystemClock
from app.core.errors import NotFoundError
from app.core.ids import new_id
from app.models.database import Database
from app.models.memory import MemoryEmbedding, MemoryItem
from app.schemas.memory import MemoryItemOut, MemoryStats


@dataclass(frozen=True)
class Candidate:
    item: MemoryItemOut
    vector: list[float] | None
    embedder: str | None


@dataclass(frozen=True)
class MemoryFilter:
    scopes: Sequence[str] = ()
    project_id: str | None = None  # restricts project/conversation scope; global items always match
    statuses: Sequence[str] = ("active",)
    tag: str | None = None
    source_kind: str | None = None
    text: str | None = None  # plain substring filter for the browser (search uses the retriever)


class MemoryStore:
    def __init__(self, db: Database, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()

    # ---- rows ------------------------------------------------------------------------------
    async def add(self, **fields: Any) -> MemoryItemOut:
        now = self._clock.now()
        async with self._db.session() as s:
            row = MemoryItem(id=new_id("mem"), created_at=now, updated_at=now, access_count=0, **fields)
            s.add(row)
            await s.flush()
            return MemoryItemOut.model_validate(row)

    async def get(self, item_id: str) -> MemoryItemOut:
        async with self._db.session() as s:
            row = await s.get(MemoryItem, item_id)
            if row is None:
                raise NotFoundError("That memory does not exist.")
            return MemoryItemOut.model_validate(row)

    async def update(self, item_id: str, **fields: Any) -> MemoryItemOut:
        async with self._db.session() as s:
            row = await s.get(MemoryItem, item_id)
            if row is None:
                raise NotFoundError("That memory does not exist.")
            for k, v in fields.items():
                setattr(row, k, v)
            row.updated_at = self._clock.now()
            await s.flush()
            return MemoryItemOut.model_validate(row)

    async def purge(self, item_id: str) -> None:
        async with self._db.session() as s:
            await s.execute(delete(MemoryEmbedding).where(MemoryEmbedding.item_id == item_id))
            await s.execute(delete(MemoryItem).where(MemoryItem.id == item_id))

    async def find_by_hash(
        self, content_hash: str, scope: str, project_id: str | None
    ) -> MemoryItemOut | None:
        """An existing live item with exactly this content in the same place, if any."""
        async with self._db.session() as s:
            q = select(MemoryItem).where(
                MemoryItem.content_hash == content_hash,
                MemoryItem.scope == scope,
                MemoryItem.status.in_(("active", "pending")),
            )
            q = (
                q.where(MemoryItem.project_id == project_id)
                if project_id
                else q.where(MemoryItem.project_id.is_(None))
            )
            row = (await s.execute(q.limit(1))).scalar_one_or_none()
            return MemoryItemOut.model_validate(row) if row else None

    def _filtered(self, f: MemoryFilter) -> Select[MemoryItem]:
        q = select(MemoryItem)
        if f.statuses:
            q = q.where(MemoryItem.status.in_(tuple(f.statuses)))
        if f.scopes:
            q = q.where(MemoryItem.scope.in_(tuple(f.scopes)))
        if f.project_id is not None:
            q = q.where(or_(MemoryItem.scope == "global", MemoryItem.project_id == f.project_id))
        if f.source_kind:
            q = q.where(func.json_extract(MemoryItem.source, "$.kind") == f.source_kind)
        if f.text:
            q = q.where(MemoryItem.content.ilike(f"%{_escape_like(f.text)}%", escape="\\"))
        return q

    async def list_items(self, f: MemoryFilter, *, limit: int = 100, offset: int = 0) -> list[MemoryItemOut]:
        q = self._filtered(f).order_by(MemoryItem.importance.desc(), MemoryItem.updated_at.desc())
        async with self._db.session() as s:
            rows = (
                await s.execute(q.limit(max(limit * 4, 200) if f.tag else limit).offset(offset))
            ).scalars()
            items = [MemoryItemOut.model_validate(r) for r in rows]
        if f.tag:  # JSON array membership is filtered here to stay portable
            items = [i for i in items if f.tag in i.tags][:limit]
        return items

    async def candidates(self, f: MemoryFilter, *, limit: int = 2000) -> list[Candidate]:
        """Live items with their vectors, newest and most important first (the retriever ranks them)."""
        q = (
            self._filtered(f)
            .add_columns(MemoryEmbedding.vector, MemoryEmbedding.embedder)
            .outerjoin(MemoryEmbedding, MemoryEmbedding.item_id == MemoryItem.id)
            .order_by(MemoryItem.importance.desc(), MemoryItem.updated_at.desc())
            .limit(limit)
        )
        async with self._db.session() as s:
            return [
                Candidate(MemoryItemOut.model_validate(row), vector, embedder)
                for row, vector, embedder in (await s.execute(q)).all()
            ]

    async def stats(self, project_id: str | None = None) -> MemoryStats:
        q = select(MemoryItem.status, func.count()).group_by(MemoryItem.status)
        if project_id:
            q = q.where(or_(MemoryItem.scope == "global", MemoryItem.project_id == project_id))
        async with self._db.session() as s:
            counts = {status: n for status, n in (await s.execute(q)).all()}
        return MemoryStats(
            active=counts.get("active", 0), pending=counts.get("pending", 0), deleted=counts.get("deleted", 0)
        )

    async def touch(self, item_ids: Iterable[str], at: datetime) -> None:
        ids = list(item_ids)
        if not ids:
            return
        async with self._db.session() as s:
            await s.execute(
                update(MemoryItem)
                .where(MemoryItem.id.in_(ids))
                .values(access_count=MemoryItem.access_count + 1, last_accessed_at=at)
            )

    async def compression_candidates(
        self, project_id: str, *, before: datetime, max_importance: float, max_access: int
    ) -> list[Candidate]:
        q = (
            select(MemoryItem, MemoryEmbedding.vector, MemoryEmbedding.embedder)
            .outerjoin(MemoryEmbedding, MemoryEmbedding.item_id == MemoryItem.id)
            .where(
                MemoryItem.project_id == project_id,
                MemoryItem.scope == "project",
                MemoryItem.status == "active",
                MemoryItem.importance <= max_importance,
                MemoryItem.access_count <= max_access,
                MemoryItem.created_at < before,
                func.json_extract(MemoryItem.source, "$.kind") != "summary",
            )
            .order_by(MemoryItem.created_at)
        )
        async with self._db.session() as s:
            return [
                Candidate(MemoryItemOut.model_validate(r), v, e) for r, v, e in (await s.execute(q)).all()
            ]

    async def merged_into(self, summary_id: str) -> list[MemoryItemOut]:
        async with self._db.session() as s:
            rows = (await s.execute(select(MemoryItem).where(MemoryItem.merged_into == summary_id))).scalars()
            return [MemoryItemOut.model_validate(r) for r in rows]

    # ---- embeddings ------------------------------------------------------------------------
    async def set_embedding(self, item_id: str, embedder: str, vector: list[float]) -> None:
        async with self._db.session() as s:
            row = await s.get(MemoryEmbedding, item_id)
            if row is None:
                s.add(MemoryEmbedding(item_id=item_id, embedder=embedder, dim=len(vector), vector=vector))
            else:
                row.embedder, row.dim, row.vector = embedder, len(vector), vector

    async def delete_embedding(self, item_id: str) -> None:
        async with self._db.session() as s:
            await s.execute(delete(MemoryEmbedding).where(MemoryEmbedding.item_id == item_id))

    async def stale_embeddings(self, embedder: str, limit: int = 500) -> list[MemoryItemOut]:
        """Live items with no vector, or one from a different embedder (re-embedded in the background)."""
        q = (
            select(MemoryItem)
            .outerjoin(MemoryEmbedding, MemoryEmbedding.item_id == MemoryItem.id)
            .where(
                MemoryItem.status.in_(("active", "pending")),
                or_(MemoryEmbedding.item_id.is_(None), MemoryEmbedding.embedder != embedder),
            )
            .limit(limit)
        )
        async with self._db.session() as s:
            return [MemoryItemOut.model_validate(r) for r in (await s.execute(q)).scalars()]


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
