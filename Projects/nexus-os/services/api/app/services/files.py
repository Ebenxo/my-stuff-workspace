"""FilesService: the person's own view of a project's files (same path guard the agents use)."""

from __future__ import annotations

from typing import NoReturn

from app.core.errors import ConflictError, InvalidRequestError, NotFoundError
from app.events.bus import EventBus
from app.events.types import EventType
from app.files.fs import FsError, WorkspaceFS
from app.schemas.runtime import FileContentOut, FileEntryOut
from app.services.projects import ProjectService


def _translate(exc: FsError) -> NoReturn:
    if exc.code == "not_found":
        raise NotFoundError(exc.message) from exc
    if exc.code in ("exists", "is_a_directory", "not_a_file", "not_a_directory", "changed"):
        raise ConflictError(exc.message) from exc
    raise InvalidRequestError(exc.message) from exc


class FilesService:
    def __init__(self, projects: ProjectService, bus: EventBus) -> None:
        self._projects = projects
        self._bus = bus

    async def _fs(self, project_id: str) -> WorkspaceFS:
        return WorkspaceFS(await self._projects.project_dir(project_id))

    async def list_dir(self, project_id: str, path: str = ".") -> list[FileEntryOut]:
        fs = await self._fs(project_id)
        try:
            return [
                FileEntryOut(path=e.path, kind=e.kind, size=e.size, modified=e.modified)
                for e in fs.list_dir(path)
            ]
        except FsError as exc:
            _translate(exc)

    async def read(self, project_id: str, path: str) -> FileContentOut:
        fs = await self._fs(project_id)
        try:
            clean, _ = fs.resolve(path)
            text, truncated = fs.read_text(path)
        except FsError as exc:
            _translate(exc)
        return FileContentOut(path=clean, content=text, truncated=truncated)

    async def write(self, project_id: str, path: str, content: str) -> dict[str, object]:
        fs = await self._fs(project_id)
        try:
            written = fs.write_text(path, content)
        except FsError as exc:
            _translate(exc)
        await self._bus.emit(
            EventType.FILE_WRITTEN,
            project_id=project_id,
            actor="user",
            payload={"path": written["path"], "bytes": written["bytes"], "created": written["created"]},
        )
        return written

    async def delete(self, project_id: str, path: str) -> dict[str, object]:
        fs = await self._fs(project_id)
        try:
            gone = fs.soft_delete(path)
        except FsError as exc:
            _translate(exc)
        await self._bus.emit(
            EventType.FILE_DELETED,
            project_id=project_id,
            actor="user",
            payload={"path": gone["path"], "recoverable": True},
        )
        return gone
