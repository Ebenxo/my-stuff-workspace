"""MemoryService: the only way anything is remembered, recalled, changed or forgotten.

Write path (never silent, never sensitive): normalise → sensitivity guard (refuse, report the category
only) → exact duplicate (reuse) → near duplicate (merge, never into a person's own words) → pending for
agent-proposed global memory and objective suggestions → embed, store, index → event. Every item is
visible, editable and deletable, and every change is an event.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Literal

from app.core.clock import Clock, SystemClock
from app.core.errors import ConflictError, InvalidRequestError
from app.events.bus import EventBus
from app.events.types import EventType
from app.memory import compressor, sensitivity
from app.memory.embedder import Embedder, HashingEmbedder, cosine
from app.memory.scoring import importance_for, rank
from app.repositories.memory_store import MemoryFilter, MemoryStore
from app.repositories.search_index import SearchIndex
from app.schemas.memory import (
    CompressionReport,
    MemoryCreate,
    MemoryHit,
    MemoryItemOut,
    MemorySource,
    MemoryStats,
    MemoryUpdate,
)

NEAR_DUPLICATE = 0.92
COMPRESS_AFTER_DAYS = 30
COMPRESS_MAX_IMPORTANCE = 0.5
COMPRESS_MAX_ACCESS = 1
PREVIEW = 160
_SPACE = re.compile(r"[ \t]+")


@dataclass(frozen=True)
class Proposal:
    action: Literal["created", "duplicate", "merged", "rejected"]
    item: MemoryItemOut | None
    categories: list[str] = field(default_factory=list)
    message: str = ""


def normalise(text: str) -> str:
    lines = [_SPACE.sub(" ", line).strip() for line in text.strip().splitlines()]
    return "\n".join(line for line in lines if line)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.lower().encode()).hexdigest()


class MemoryService:
    def __init__(
        self,
        store: MemoryStore,
        index: SearchIndex,
        bus: EventBus,
        embedder: Embedder | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._store = store
        self._index = index
        self._bus = bus
        self._embedder: Embedder = embedder or HashingEmbedder()
        self._clock = clock or SystemClock()

    @property
    def embedder(self) -> Embedder:
        return self._embedder

    # ======================================================================= writing
    async def propose(
        self,
        content: str,
        *,
        scope: str,
        project_id: str | None,
        source: MemorySource,
        tags: Sequence[str] = (),
        importance: float | None = None,
        pending: bool = False,
    ) -> Proposal:
        text = normalise(content)
        if len(text) < 3:
            raise InvalidRequestError("A memory needs some content.")
        if scope in ("project", "conversation") and not project_id:
            raise InvalidRequestError("Project memory needs a project.")
        if scope == "global":
            project_id = None
        tags = list(dict.fromkeys(t.strip().lower() for t in tags if t.strip()))[:12]

        categories = sensitivity.scan(text)
        if categories:
            await self._emit(
                EventType.MEMORY_REJECTED,
                project_id,
                {"categories": categories, "scope": scope, "source": source.kind, "agent": source.agent},
                source,
            )
            return Proposal("rejected", None, categories, sensitivity.explain(categories))

        imp = importance_for(source.kind, importance, tainted=source.tainted)
        digest = content_hash(text)
        same = await self._store.find_by_hash(digest, scope, project_id)
        if same is not None:
            item = await self._store.update(
                same.id,
                importance=max(same.importance, imp),
                tags=list(dict.fromkeys([*same.tags, *tags]))[:12],
                last_accessed_at=self._clock.now(),
            )
            return Proposal("duplicate", item, message="Already remembered.")

        vector = self._embedder.embed(text)
        near = await self._nearest(vector, scope, project_id, private=source.private)
        if near is not None:
            if near.source.kind == "user" and source.kind != "user":
                # A person's own words are never rewritten by an agent; the agent's note adds nothing new.
                return Proposal("duplicate", near, message="Already remembered (in the person's words).")
            item = await self._store.update(
                near.id,
                content=text,
                content_hash=digest,
                importance=max(near.importance, imp),
                tags=list(dict.fromkeys([*near.tags, *tags]))[:12],
            )
            await self._embed_and_index(item, vector)
            await self._emit(
                EventType.MEMORY_UPDATED,
                project_id,
                {"id": item.id, "change": "merged", **_preview(item)},
                source,
            )
            return Proposal("merged", item, message="Merged with a very similar memory.")

        status = "pending" if pending or (scope == "global" and source.kind != "user") else "active"
        item = await self._store.add(
            scope=scope,
            project_id=project_id,
            content=text,
            summary="",
            importance=imp,
            source=source.model_dump(),
            tags=tags,
            status=status,
            content_hash=digest,
        )
        await self._embed_and_index(item, vector)
        await self._emit(
            EventType.MEMORY_CREATED,
            project_id,
            {
                "id": item.id,
                "scope": scope,
                "status": status,
                "source": source.kind,
                "agent": source.agent,
                **_preview(item),
            },
            source,
        )
        message = (
            "Saved as a suggestion; the person decides whether to keep it."
            if status == "pending"
            else "Remembered."
        )
        return Proposal("created", item, message=message)

    async def create_by_user(self, body: MemoryCreate) -> MemoryItemOut:
        result = await self.propose(
            body.content,
            scope=body.scope,
            project_id=body.project_id,
            source=MemorySource(kind="user"),
            tags=body.tags,
        )
        if result.action == "rejected" or result.item is None:
            raise InvalidRequestError(result.message)
        if body.pinned and result.item.importance < 1.0:
            return await self._store.update(result.item.id, importance=1.0)
        return result.item

    async def update(self, item_id: str, body: MemoryUpdate) -> MemoryItemOut:
        item = await self._store.get(item_id)
        if item.status == "deleted":
            raise ConflictError("Restore this memory before editing it.")
        fields: dict[str, Any] = {}
        vector: list[float] | None = None
        if body.content is not None and normalise(body.content) != item.content:
            text = normalise(body.content)
            categories = sensitivity.scan(text)
            if categories:
                raise InvalidRequestError(sensitivity.explain(categories))
            fields.update(content=text, content_hash=content_hash(text))
            vector = self._embedder.embed(text)
        if body.tags is not None:
            fields["tags"] = list(dict.fromkeys(t.lower() for t in body.tags))[:12]
        if body.pinned is not None:
            fields["importance"] = (
                1.0 if body.pinned else importance_for(item.source.kind, tainted=item.source.tainted)
            )
        if not fields:
            return item
        item = await self._store.update(item_id, **fields)
        if vector is not None:
            await self._embed_and_index(item, vector)
        else:
            await self._index_item(item)
        await self._emit(
            EventType.MEMORY_UPDATED, item.project_id, {"id": item.id, "change": "edited", **_preview(item)}
        )
        return item

    async def confirm(self, item_id: str) -> MemoryItemOut:
        item = await self._store.get(item_id)
        if item.status != "pending":
            raise ConflictError("Only a suggested memory can be confirmed.")
        item = await self._store.update(item_id, status="active")
        await self._emit(
            EventType.MEMORY_UPDATED,
            item.project_id,
            {"id": item.id, "change": "confirmed", **_preview(item)},
        )
        return item

    async def delete(self, item_id: str, *, reason: str = "deleted") -> MemoryItemOut:
        item = await self._store.get(item_id)
        if item.status == "deleted":
            return item
        item = await self._store.update(item_id, status="deleted")
        await self._store.delete_embedding(item_id)
        await self._index.delete("memory", item_id)
        await self._emit(EventType.MEMORY_DELETED, item.project_id, {"id": item.id, "reason": reason})
        return item

    async def reject(self, item_id: str) -> MemoryItemOut:
        item = await self._store.get(item_id)
        if item.status != "pending":
            raise ConflictError("Only a suggested memory can be dismissed.")
        return await self.delete(item_id, reason="dismissed")

    async def restore(self, item_id: str) -> MemoryItemOut:
        item = await self._store.get(item_id)
        if item.status != "deleted":
            raise ConflictError("Only a deleted memory can be restored.")
        item = await self._store.update(item_id, status="active", merged_into=None)
        await self._embed_and_index(item, None)
        await self._emit(
            EventType.MEMORY_UPDATED, item.project_id, {"id": item.id, "change": "restored", **_preview(item)}
        )
        return item

    async def purge(self, item_id: str) -> None:
        item = await self._store.get(item_id)
        await self._store.purge(item_id)
        await self._index.delete("memory", item_id)
        await self._emit(EventType.MEMORY_DELETED, item.project_id, {"id": item_id, "reason": "purged"})

    # ======================================================================= reading
    async def get(self, item_id: str) -> MemoryItemOut:
        return await self._store.get(item_id)

    async def list_items(self, f: MemoryFilter, *, limit: int = 100, offset: int = 0) -> list[MemoryItemOut]:
        return await self._store.list_items(f, limit=limit, offset=offset)

    async def stats(self, project_id: str | None = None) -> MemoryStats:
        return await self._store.stats(project_id)

    async def search(
        self,
        query: str,
        *,
        scopes: Sequence[str] = ("project", "global"),
        project_id: str | None = None,
        k: int = 8,
        objective_id: str | None = None,
        touch: bool = True,
        include_private: bool = False,
    ) -> list[MemoryHit]:
        """Rank live memories for ``query``. Recalled items are marked as used (recency reinforcement).

        Memories written by private runs are only returned when ``include_private`` is set (the caller
        is a private run, or the person), so they can never reach a cloud model."""
        if not query.strip() or not scopes:
            return []
        cands = await self._store.candidates(MemoryFilter(scopes=scopes, project_id=project_id))
        name = self._embedder.name
        pairs = [
            (c.item, c.vector if c.embedder == name else None)
            for c in cands
            if include_private or not c.item.source.private
        ]
        ranked = rank(
            query, self._embedder.embed(query), pairs, now=self._clock.now(), objective_id=objective_id, k=k
        )
        if touch and ranked:
            await self._store.touch([r.item.id for r in ranked], self._clock.now())
        return [MemoryHit(item=r.item, score=r.score) for r in ranked]

    async def pinned(
        self, project_id: str, *, limit: int = 5, include_private: bool = False
    ) -> list[MemoryItemOut]:
        """The project's standing facts: pinned project memories, always offered to its agents."""
        items = await self._store.list_items(
            MemoryFilter(scopes=("project",), project_id=project_id), limit=limit * 4
        )
        return [i for i in items if i.pinned and (include_private or not i.source.private)][:limit]

    # ======================================================================= suggestions
    async def suggest_from_objective(
        self,
        *,
        project_id: str,
        objective_id: str,
        objective: str,
        verdict: str,
        summary: str,
        deliverables: Sequence[str] = (),
        private: bool = False,
    ) -> Proposal | None:
        """After an objective finishes, suggest remembering what came of it. The person decides."""
        if not summary.strip():
            return None
        text = f'Objective "{objective.strip()[:200]}" finished ({verdict}): {summary.strip()[:600]}'
        if deliverables:
            text += f" Deliverables: {', '.join(deliverables[:6])}."
        return await self.propose(
            text,
            scope="project",
            project_id=project_id,
            source=MemorySource(kind="objective", objective_id=objective_id, private=private),
            tags=["objective"],
            pending=True,
        )

    # ======================================================================= compression
    async def compress(
        self, project_id: str, *, older_than_days: int = COMPRESS_AFTER_DAYS
    ) -> CompressionReport:
        before = self._clock.now() - timedelta(days=older_than_days)
        cands = await self._store.compression_candidates(
            project_id, before=before, max_importance=COMPRESS_MAX_IMPORTANCE, max_access=COMPRESS_MAX_ACCESS
        )
        name = self._embedder.name
        groups = compressor.group([(c.item, c.vector if c.embedder == name else None) for c in cands])
        summaries: list[str] = []
        merged = 0
        for g in groups:
            text = compressor.summarise(g)
            summary = await self._store.add(
                scope="project",
                project_id=project_id,
                content=text,
                summary="",
                importance=importance_for("summary"),
                source=MemorySource(kind="summary").model_dump(),
                tags=g.tags,
                status="active",
                content_hash=content_hash(text),
            )
            await self._embed_and_index(summary, None)
            for item in g.items:  # originals go only after the summary exists
                await self._store.update(item.id, status="deleted", merged_into=summary.id)
                await self._store.delete_embedding(item.id)
                await self._index.delete("memory", item.id)
            summaries.append(summary.id)
            merged += len(g.items)
            await self._emit(
                EventType.MEMORY_COMPRESSED,
                project_id,
                {"id": summary.id, "merged": len(g.items), **_preview(summary)},
            )
        return CompressionReport(
            project_id=project_id, groups=len(groups), compressed=merged, summaries=summaries
        )

    async def undo_compression(self, summary_id: str) -> list[MemoryItemOut]:
        summary = await self._store.get(summary_id)
        originals = await self._store.merged_into(summary_id)
        if summary.source.kind != "summary" or not originals:
            raise ConflictError("This memory is not a compression summary.")
        restored = [await self.restore(o.id) for o in originals]
        await self.delete(summary_id, reason="compression undone")
        return restored

    # ======================================================================= maintenance
    async def reembed_stale(self) -> int:
        """Give every live item a vector from the current embedder. Returns how many were updated."""
        done = 0
        while batch := await self._store.stale_embeddings(self._embedder.name):
            for item in batch:
                await self._store.set_embedding(
                    item.id, self._embedder.name, self._embedder.embed(item.content)
                )
            done += len(batch)
        return done

    async def reindex_all(self) -> int:
        items = await self._store.list_items(MemoryFilter(statuses=("active", "pending")), limit=100_000)
        for item in items:
            await self._index_item(item)
        return len(items)

    # ======================================================================= tool facade
    async def recall_for_tool(
        self,
        query: str,
        *,
        scopes: Sequence[str],
        project_id: str | None,
        objective_id: str | None,
        k: int,
        private: bool,
    ) -> list[dict[str, Any]]:
        hits = await self.search(
            query,
            scopes=scopes,
            project_id=project_id,
            k=k,
            objective_id=objective_id,
            include_private=private,
        )
        return [
            {
                "id": h.item.id,
                "scope": h.item.scope,
                "content": h.item.content,
                "tags": h.item.tags,
                "source": h.item.source.kind,
                "tainted": h.item.source.tainted,
                "score": h.score.total,
            }
            for h in hits
        ]

    async def remember_for_tool(
        self,
        content: str,
        *,
        scope: str,
        project_id: str | None,
        tags: Sequence[str],
        importance: float | None,
        source: MemorySource,
    ) -> dict[str, Any]:
        result = await self.propose(
            content, scope=scope, project_id=project_id, source=source, tags=tags, importance=importance
        )
        out: dict[str, Any] = {"outcome": result.action, "message": result.message}
        if result.item is not None:
            out.update(id=result.item.id, status=result.item.status)
        if result.categories:
            out["categories"] = result.categories
        return out

    # ======================================================================= helpers
    async def _nearest(
        self, vector: list[float], scope: str, project_id: str | None, *, private: bool
    ) -> MemoryItemOut | None:
        """The live item this text nearly duplicates. Private and shareable memories never merge."""
        cands = await self._store.candidates(
            MemoryFilter(scopes=(scope,), project_id=project_id, statuses=("active", "pending"))
        )
        best, best_sim = None, 0.0
        for c in cands:
            if c.embedder != self._embedder.name or (c.item.project_id or None) != (project_id or None):
                continue
            if c.item.source.private != private:
                continue
            sim = cosine(vector, c.vector)
            if sim > best_sim:
                best, best_sim = c.item, sim
        return best if best_sim >= NEAR_DUPLICATE else None

    async def _embed_and_index(self, item: MemoryItemOut, vector: list[float] | None) -> None:
        await self._store.set_embedding(
            item.id, self._embedder.name, vector or self._embedder.embed(item.content)
        )
        await self._index_item(item)

    async def _index_item(self, item: MemoryItemOut) -> None:
        title = item.content.splitlines()[0][:80]
        await self._index.upsert(
            "memory", item.id, item.project_id, title, item.content + "\n" + " ".join(item.tags)
        )

    async def _emit(
        self,
        type_: EventType,
        project_id: str | None,
        payload: dict[str, Any],
        source: MemorySource | None = None,
    ) -> None:
        await self._bus.emit(
            type_,
            project_id=project_id,
            objective_id=source.objective_id if source else None,
            task_id=source.task_id if source else None,
            run_id=source.run_id if source else None,
            actor=(source.agent or "system")
            if source and source.kind == "agent"
            else ("user" if source and source.kind == "user" else "system"),
            payload=payload,
        )


def _preview(item: MemoryItemOut) -> dict[str, Any]:
    text = item.content if len(item.content) <= PREVIEW else item.content[: PREVIEW - 1] + "…"
    return {"preview": text, "scope": item.scope, "status": item.status}
