"""Artifact store: persistent, versioned deliverables. Nothing significant is ever overwritten."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.clock import Clock, SystemClock
from app.core.errors import InvalidRequestError, NotFoundError
from app.events.bus import EventBus
from app.events.types import EventType
from app.repositories.runtime_store import ArtifactRepo
from app.schemas.runtime import ArtifactOut, ArtifactType, ArtifactVersionOut

MAX_ARTIFACT_BYTES = 10_000_000
_EXT: dict[str, str] = {
    "document": ".md",
    "markdown": ".md",
    "report": ".md",
    "presentation": ".md",
    "code": ".txt",
    "spreadsheet": ".csv",
    "dataset": ".csv",
    "json": ".json",
    "chart": ".svg",
    "image_ref": ".json",
    "website": ".html",
}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")
_ALLOWED_EXT = frozenset(
    {
        ".md",
        ".txt",
        ".csv",
        ".json",
        ".svg",
        ".html",
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".css",
        ".yaml",
        ".yml",
        ".toml",
        ".sql",
        ".xml",
    }
)


def sanitize_artifact_name(name: str, type_: str) -> str:
    """Flat, safe file name. Never contains a path separator or a leading dot; extension is allow-listed."""
    base = _SAFE_NAME.sub("_", name.replace("\\", "/").rsplit("/", 1)[-1]).strip(" .")
    if not base:
        raise InvalidRequestError("The artifact needs a name.")
    stem, dot, ext = base.rpartition(".")
    if not dot or f".{ext.lower()}" not in _ALLOWED_EXT:
        stem, ext = base, _EXT.get(type_, ".md").lstrip(".")
    return f"{stem[:100].rstrip(' .') or 'artifact'}.{ext.lower()}"


@dataclass(frozen=True)
class ArtifactWrite:
    artifact: ArtifactOut
    created: bool  # a brand new artifact
    changed: bool  # a new version was stored (False = identical content, nothing written)


class ArtifactStore:
    def __init__(
        self, repo: ArtifactRepo, bus: EventBus, project_dir_for: Any, clock: Clock | None = None
    ) -> None:
        self._repo = repo
        self._bus = bus
        self._project_dir_for = project_dir_for  # async (project_id) -> Path
        self._clock = clock or SystemClock()

    async def _root(self, project_id: str) -> Path:
        root: Path = await self._project_dir_for(project_id)
        return root

    async def save(
        self,
        *,
        project_id: str,
        name: str,
        type_: ArtifactType,
        content: str | bytes,
        agent_id: str | None = None,
        task_id: str | None = None,
        objective_id: str | None = None,
        meta: dict[str, Any] | None = None,
        note: str = "",
    ) -> ArtifactWrite:
        data = content.encode("utf-8") if isinstance(content, str) else content
        if len(data) > MAX_ARTIFACT_BYTES:
            raise InvalidRequestError(f"The artifact is larger than {MAX_ARTIFACT_BYTES // 1_000_000} MB.")
        file_name = sanitize_artifact_name(name, type_)
        rel = f"artifacts/{file_name}"
        digest = hashlib.sha256(data).hexdigest()
        root = await self._root(project_id)
        existing = await self._repo.find(project_id, rel)

        if existing is not None:
            artifact, versions = existing
            if versions and versions[-1].sha256 == digest:
                return ArtifactWrite(artifact, created=False, changed=False)
            version_no = artifact.version + 1
            stored = self._write_version(root, artifact.id, version_no, file_name, data)
            self._write_current(root, file_name, data)
            updated = await self._repo.add_version(
                artifact.id,
                {
                    "version": version_no,
                    "stored_path": stored,
                    "sha256": digest,
                    "size": len(data),
                    "created_by": agent_id,
                    "note": note,
                    "created_at": self._clock.now(),
                },
                agent_id=agent_id,
                task_id=task_id,
                meta=meta or {},
            )
            await self._bus.emit(
                EventType.ARTIFACT_UPDATED,
                project_id=project_id,
                objective_id=objective_id or artifact.objective_id,
                task_id=task_id,
                agent_id=agent_id,
                payload={
                    "artifact_id": artifact.id,
                    "name": artifact.name,
                    "version": version_no,
                    "type": artifact.type,
                },
            )
            return ArtifactWrite(updated, created=False, changed=True)

        from app.core.ids import new_id  # local import keeps the module header light

        artifact_id = new_id("art")
        stored = self._write_version(root, artifact_id, 1, file_name, data)
        self._write_current(root, file_name, data)
        now = self._clock.now()
        created = await self._repo.create(
            {
                "id": artifact_id,
                "project_id": project_id,
                "objective_id": objective_id,
                "task_id": task_id,
                "agent_id": agent_id,
                "type": type_,
                "name": file_name,
                "path": rel,
                "version": 1,
                "meta": meta or {},
                "created_at": now,
                "updated_at": now,
            },
            {
                "version": 1,
                "stored_path": stored,
                "sha256": digest,
                "size": len(data),
                "created_by": agent_id,
                "note": note,
                "created_at": now,
            },
        )
        await self._bus.emit(
            EventType.ARTIFACT_CREATED,
            project_id=project_id,
            objective_id=objective_id,
            task_id=task_id,
            agent_id=agent_id,
            payload={"artifact_id": artifact_id, "name": file_name, "version": 1, "type": type_},
        )
        return ArtifactWrite(created, created=True, changed=True)

    @staticmethod
    def _write_version(root: Path, artifact_id: str, version: int, file_name: str, data: bytes) -> str:
        suffix = Path(file_name).suffix
        rel = f"artifacts/.versions/{artifact_id}/v{version}{suffix}"
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return rel

    @staticmethod
    def _write_current(root: Path, file_name: str, data: bytes) -> None:
        dest = root / "artifacts" / file_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(f".{dest.name}.tmp")
        tmp.write_bytes(data)
        tmp.replace(dest)

    async def get(self, artifact_id: str) -> ArtifactOut:
        return await self._repo.get(artifact_id)

    async def versions(self, artifact_id: str) -> list[ArtifactVersionOut]:
        return [v for v, _ in await self._repo.versions(artifact_id)]

    async def read(
        self, artifact_id: str, version: int | None = None, *, max_bytes: int = 1_000_000
    ) -> tuple[ArtifactOut, int, str, bool]:
        artifact = await self._repo.get(artifact_id)
        pairs = await self._repo.versions(artifact_id)
        if not pairs:
            raise NotFoundError("This artifact has no stored versions.")
        wanted = version or artifact.version
        match = next(((v, p) for v, p in pairs if v.version == wanted), None)
        if match is None:
            raise NotFoundError(f"Artifact {artifact.name} has no version {wanted}.")
        root = await self._root(artifact.project_id)
        raw = (root / match[1]).read_bytes()
        return artifact, wanted, raw[:max_bytes].decode("utf-8", errors="replace"), len(raw) > max_bytes

    async def list_artifacts(
        self, *, project_id: str, objective_id: str | None = None, type_: str | None = None
    ) -> list[ArtifactOut]:
        return await self._repo.list_artifacts(project_id=project_id, objective_id=objective_id, type_=type_)
