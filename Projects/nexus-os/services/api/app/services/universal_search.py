"""Universal search across projects, objectives, deliverables and memory.

The index follows the event log: an in-process listener re-indexes a project, objective or artifact
whenever an event says it changed (memory is indexed by the MemoryService itself). Listeners run right
after the event is committed, so the index is current by the time the action returns. A full rebuild
runs at startup when the index is empty (first start after the migration, or after a reset).
"""

from __future__ import annotations

import logging

from app.core.errors import NotFoundError
from app.events.types import EventType
from app.files.artifacts import ArtifactStore
from app.memory.service import MemoryService
from app.repositories.orchestration_store import ObjectiveStore
from app.repositories.search_index import SearchIndex
from app.schemas.events import EventRecord
from app.schemas.memory import SearchHit, SearchKind, SearchResults
from app.services.projects import ProjectService

log = logging.getLogger(__name__)

TEXT_ARTIFACTS = frozenset(
    {"document", "markdown", "code", "spreadsheet", "report", "json", "dataset", "website"}
)
_PROJECT_EVENTS = {
    EventType.PROJECT_CREATED.value,
    EventType.PROJECT_UPDATED.value,
    EventType.PROJECT_ARCHIVED.value,
}
_OBJECTIVE_EVENTS = {
    EventType.OBJECTIVE_CREATED.value,
    EventType.PLAN_CREATED.value,
    EventType.OBJECTIVE_COMPLETED.value,
    EventType.OBJECTIVE_FAILED.value,
    EventType.OBJECTIVE_CANCELLED.value,
}
_ARTIFACT_EVENTS = {EventType.ARTIFACT_CREATED.value, EventType.ARTIFACT_UPDATED.value}


class UniversalSearch:
    def __init__(
        self,
        index: SearchIndex,
        *,
        projects: ProjectService,
        objectives: ObjectiveStore,
        artifacts: ArtifactStore,
        memory: MemoryService,
    ) -> None:
        self._index = index
        self._projects = projects
        self._objectives = objectives
        self._artifacts = artifacts
        self._memory = memory

    # ---- keeping the index current --------------------------------------------------------
    async def on_event(self, record: EventRecord) -> None:
        try:
            if record.type in _PROJECT_EVENTS and record.project_id:
                await self.index_project(record.project_id)
            elif record.type in _OBJECTIVE_EVENTS and record.objective_id:
                await self.index_objective(record.objective_id)
            elif record.type in _ARTIFACT_EVENTS:
                artifact_id = record.payload.get("artifact_id")
                if isinstance(artifact_id, str):
                    await self.index_artifact(artifact_id)
        except NotFoundError:
            pass  # removed in the meantime; nothing to index

    async def index_project(self, project_id: str) -> None:
        p = await self._projects.get(project_id)
        title = p.name + (" (archived)" if p.status == "archived" else "")
        await self._index.upsert("project", p.id, p.id, title, p.description or "")

    async def index_objective(self, objective_id: str) -> None:
        o = await self._objectives.get(objective_id)
        body = o.text
        if o.result and isinstance(o.result.get("summary"), str):
            body += "\n" + o.result["summary"]
        title = o.text.strip().splitlines()[0][:120] if o.text.strip() else "Objective"
        await self._index.upsert("objective", o.id, o.project_id, title, body)

    async def index_artifact(self, artifact_id: str) -> None:
        a = await self._artifacts.get(artifact_id)
        body = ""
        if a.type in TEXT_ARTIFACTS:
            try:
                _, _, text, _ = await self._artifacts.read(artifact_id, max_bytes=200_000)
                body = text if "\x00" not in text else ""
            except (NotFoundError, OSError):
                body = ""
        await self._index.upsert("artifact", a.id, a.project_id, a.name, body)

    async def rebuild(self) -> int:
        await self._index.clear()
        count = 0
        for p in await self._projects.list_all():
            await self.index_project(p.id)
            count += 1
            for a in await self._artifacts.list_artifacts(project_id=p.id):
                await self.index_artifact(a.id)
                count += 1
        for o in await self._objectives.list_objectives(limit=100_000):
            await self.index_objective(o.id)
            count += 1
        count += await self._memory.reindex_all()
        return count

    async def ensure_built(self) -> None:
        if await self._index.count() == 0 and await self._projects.list_all():
            n = await self.rebuild()
            log.info("search index rebuilt with %d entries", n)

    # ---- querying -------------------------------------------------------------------------
    async def search(
        self, q: str, *, project_id: str | None = None, kinds: list[SearchKind] | None = None, limit: int = 30
    ) -> SearchResults:
        hits = await self._index.query(q, kinds=kinds or [], project_id=project_id, limit=limit)
        engine = "fts5" if await self._index.uses_fts() else "like"
        return SearchResults(
            query=q,
            engine=engine,
            hits=[
                SearchHit(
                    kind=h.kind,
                    id=h.ref_id,
                    project_id=h.project_id,
                    title=h.title,
                    snippet=h.snippet,
                    score=h.score,
                )
                for h in hits
            ],
        )
