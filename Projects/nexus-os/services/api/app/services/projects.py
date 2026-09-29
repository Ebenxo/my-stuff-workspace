"""Project use cases."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from app.core.clock import Clock
from app.core.errors import ConflictError, NotFoundError
from app.core.ids import new_id
from app.events.bus import EventBus
from app.events.types import EventType
from app.files.workspace import WorkspaceManager
from app.models.database import Database
from app.models.foundation import Conversation, Project
from app.repositories.projects import ConversationRepository, ProjectRepository
from app.schemas.projects import ProjectCreate, ProjectOut, ProjectSettings, ProjectUpdate
from app.services.settings import SettingsService


def slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:60] or "project"


def to_out(row: Project) -> ProjectOut:
    return ProjectOut(
        id=row.id,
        name=row.name,
        slug=row.slug,
        description=row.description,
        icon=row.icon,
        status=row.status,
        is_demo=row.is_demo,
        settings=ProjectSettings.model_validate(row.settings or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ProjectService:
    def __init__(self, db: Database, bus: EventBus, settings_service: SettingsService, clock: Clock) -> None:
        self._db = db
        self._bus = bus
        self._settings = settings_service
        self._clock = clock

    async def workspace(self) -> WorkspaceManager:
        return WorkspaceManager(await self._settings.workspace_root())

    async def project_dir(self, project_id: str) -> Path:
        await self.get(project_id)
        return (await self.workspace()).project_dir(project_id)

    async def create(self, data: ProjectCreate, *, is_demo: bool = False) -> ProjectOut:
        workspace = await self.workspace()
        project_id = new_id("proj")
        async with self._db.session() as session:
            repo = ProjectRepository(session)
            base = slugify(data.name)
            slug, n = base, 1
            while await repo.slug_exists(slug):
                n += 1
                slug = f"{base}-{n}"
            now = self._clock.now()
            row = await repo.add(
                Project(
                    id=project_id,
                    name=data.name.strip(),
                    slug=slug,
                    description=data.description,
                    icon=data.icon,
                    root_rel_path=workspace.project_rel_path(project_id),
                    settings=data.settings.model_dump(mode="json"),
                    status="active",
                    is_demo=is_demo,
                    created_at=now,
                    updated_at=now,
                )
            )
            await ConversationRepository(session).add(
                Conversation(
                    id=new_id("conv"),
                    project_id=project_id,
                    title="Main",
                    created_at=now,
                    updated_at=now,
                )
            )
            out = to_out(row)
        workspace.ensure_project(project_id)
        await self._bus.emit(
            EventType.PROJECT_CREATED,
            project_id=project_id,
            actor="user",
            payload={"name": out.name, "slug": out.slug, "is_demo": is_demo},
        )
        return out

    async def get(self, project_id: str) -> ProjectOut:
        async with self._db.session() as session:
            row = await ProjectRepository(session).get(project_id)
            if row is None:
                raise NotFoundError(f"Project {project_id} not found")
            return to_out(row)

    async def list_all(self, *, status: str | None = None) -> list[ProjectOut]:
        async with self._db.session() as session:
            return [to_out(r) for r in await ProjectRepository(session).list_all(status=status)]

    async def update(self, project_id: str, patch: ProjectUpdate) -> ProjectOut:
        changes = patch.model_dump(exclude_unset=True)
        async with self._db.session() as session:
            row = await ProjectRepository(session).get(project_id)
            if row is None:
                raise NotFoundError(f"Project {project_id} not found")
            for key in ("name", "description", "icon"):
                if changes.get(key) is not None:
                    setattr(row, key, changes[key].strip() if key == "name" else changes[key])
            if patch.settings is not None:
                row.settings = patch.settings.model_dump(mode="json")
            row.updated_at = self._clock.now()
            out = to_out(row)
        await self._bus.emit(
            EventType.PROJECT_UPDATED,
            project_id=project_id,
            actor="user",
            payload={"changed": sorted(k for k, v in changes.items() if v is not None)},
        )
        return out

    async def monthly_budgets(self) -> dict[str, float]:
        """Per-project monthly USD limits set in each project's own settings."""
        out: dict[str, float] = {}
        async with self._db.session() as session:
            for row in await ProjectRepository(session).list_all():
                limit = ProjectSettings.model_validate(row.settings or {}).monthly_budget_usd
                if limit is not None:
                    out[row.id] = limit
        return out

    async def set_status(self, project_id: str, status: str) -> ProjectOut:
        async with self._db.session() as session:
            row = await ProjectRepository(session).get(project_id)
            if row is None:
                raise NotFoundError(f"Project {project_id} not found")
            if row.status == status:
                raise ConflictError(f"Project is already {status}")
            row.status = status
            row.updated_at = self._clock.now()
            out = to_out(row)
        await self._bus.emit(
            EventType.PROJECT_ARCHIVED if status == "archived" else EventType.PROJECT_UPDATED,
            project_id=project_id,
            actor="user",
            payload={"status": status},
        )
        return out
