"""Ideas, notes and to-dos: the small things the person wants to keep track of.

- Every change is an event (IDEA_CREATED / IDEA_UPDATED / IDEA_DELETED), so the timeline and the
  activity feed show them like everything else. Event payloads carry a redacted snippet, never more.
- They are in universal search (kind ``idea``), kept current here as they change.
- A to-do with a due time gets one reminder (a notification and an IDEA_DUE event) when it comes due;
  moving the due time arms a new reminder. The scheduler's tick calls ``remind_due``.
- An idea can be started as an objective; the idea then points at it and is marked done.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.clock import Clock, SystemClock
from app.core.errors import ConflictError
from app.core.security import redact_text
from app.events.bus import EventBus
from app.events.types import EventType
from app.repositories.idea_store import IdeaStore
from app.repositories.search_index import SearchIndex
from app.schemas.ideas import IdeaCreate, IdeaObjectiveOut, IdeaOut, IdeaToObjective, IdeaUpdate
from app.schemas.orchestration import ObjectiveCreate
from app.services.notifications import NotificationService
from app.services.objectives import ObjectiveService
from app.services.projects import ProjectService

SNIPPET_CHARS = 120
KIND_LABEL = {"idea": "Idea", "note": "Note", "todo": "To-do"}


def title_of(text: str) -> str:
    first = text.strip().splitlines()[0] if text.strip() else ""
    return first[:SNIPPET_CHARS] or "Untitled"


class IdeaService:
    def __init__(
        self,
        *,
        store: IdeaStore,
        index: SearchIndex,
        projects: ProjectService,
        objectives: ObjectiveService,
        notifications: NotificationService,
        bus: EventBus,
        clock: Clock | None = None,
    ) -> None:
        self._store = store
        self._index = index
        self._projects = projects
        self._objectives = objectives
        self._notifications = notifications
        self._bus = bus
        self._clock = clock or SystemClock()

    # ---- reading ----------------------------------------------------------------------------
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
        return await self._store.list_ideas(
            status=status, kind=kind, project_id=project_id, pinned=pinned, q=q, limit=limit
        )

    async def get(self, idea_id: str) -> IdeaOut:
        return await self._store.get(idea_id)

    async def due_count(self) -> int:
        return await self._store.count_due(self._clock.now())

    # ---- writing ----------------------------------------------------------------------------
    async def create(self, body: IdeaCreate) -> IdeaOut:
        if body.project_id:
            await self._projects.get(body.project_id)  # 404 if it does not exist
        idea = await self._store.create(
            project_id=body.project_id,
            kind=body.kind,
            text=body.text,
            pinned=body.pinned,
            due_at=body.due_at,
        )
        await self._reindex(idea)
        await self._emit(EventType.IDEA_CREATED, idea, {})
        return idea

    async def update(self, idea_id: str, body: IdeaUpdate) -> IdeaOut:
        current = await self._store.get(idea_id)
        sent = body.model_fields_set
        fields: dict[str, Any] = {}
        for name in ("text", "kind", "pinned", "status"):
            value = getattr(body, name)
            if name in sent and value is not None and value != getattr(current, name):
                fields[name] = value
        if "project_id" in sent and body.project_id != current.project_id:
            if body.project_id:
                await self._projects.get(body.project_id)
            fields["project_id"] = body.project_id
        if "due_at" in sent and body.due_at != current.due_at:
            fields["due_at"] = body.due_at
            fields["reminded_at"] = None  # a new due time gets its own reminder
        if "status" in fields:
            fields["done_at"] = self._clock.now() if fields["status"] == "done" else None
        if not fields:
            return current
        idea = await self._store.update(idea_id, **fields)
        await self._reindex(idea)
        await self._emit(
            EventType.IDEA_UPDATED, idea, {"changed": sorted(k for k in fields if k != "reminded_at")}
        )
        return idea

    async def delete(self, idea_id: str) -> None:
        idea = await self._store.delete(idea_id)
        await self._index.delete("idea", idea.id)
        await self._emit(EventType.IDEA_DELETED, idea, {})

    async def start_objective(self, idea_id: str, body: IdeaToObjective) -> IdeaObjectiveOut:
        idea = await self._store.get(idea_id)
        if idea.objective_id:
            raise ConflictError("This idea has already been started as an objective.")
        project_id = body.project_id or idea.project_id
        if not project_id:
            raise ConflictError("Choose a project for this objective.")
        text = idea.text if len(idea.text) >= 3 else f"{idea.text} (from an idea)"
        objective = await self._objectives.create(
            ObjectiveCreate(project_id=project_id, text=text, run_mode=body.run_mode, private=body.private)
        )
        updated = await self._store.update(
            idea_id,
            objective_id=objective.id,
            project_id=idea.project_id or project_id,
            status="done",
            done_at=self._clock.now(),
        )
        await self._reindex(updated)
        await self._emit(
            EventType.IDEA_UPDATED,
            updated,
            {"changed": ["objective_id", "status"], "objective_id": objective.id},
        )
        return IdeaObjectiveOut(idea=updated, objective=objective)

    # ---- reminders --------------------------------------------------------------------------
    async def remind_due(self, now: datetime | None = None) -> list[str]:
        """Send one reminder for each open item that has come due. Returns their ids."""
        now = now or self._clock.now()
        reminded: list[str] = []
        for idea in await self._store.due_unreminded(now):
            await self._store.update(idea.id, reminded_at=now)
            label = KIND_LABEL.get(idea.kind, "Item")
            await self._notifications.notify(
                "idea_due",
                f"{label} due: {title_of(redact_text(idea.text))}",
                project_id=idea.project_id,
                ref={"idea_id": idea.id},
            )
            await self._emit(EventType.IDEA_DUE, idea, {})
            reminded.append(idea.id)
        return reminded

    async def reindex_all(self) -> int:
        ideas = await self._store.list_ideas(limit=100_000)
        for idea in ideas:
            await self._reindex(idea)
        return len(ideas)

    # ---- helpers ----------------------------------------------------------------------------
    async def _reindex(self, idea: IdeaOut) -> None:
        title = title_of(idea.text) + (" (done)" if idea.status == "done" else "")
        await self._index.upsert("idea", idea.id, idea.project_id, title, idea.text)

    async def _emit(self, type_: EventType, idea: IdeaOut, extra: dict[str, object]) -> None:
        await self._bus.emit(
            type_,
            project_id=idea.project_id,
            actor="scheduler" if type_ is EventType.IDEA_DUE else "user",
            payload={
                "idea_id": idea.id,
                "kind": idea.kind,
                "status": idea.status,
                "pinned": idea.pinned,
                "due_at": idea.due_at.isoformat() if idea.due_at else None,
                "text": title_of(redact_text(idea.text)),
                **extra,
            },
        )
