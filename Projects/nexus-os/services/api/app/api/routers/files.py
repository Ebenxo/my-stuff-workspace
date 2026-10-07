from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import Container
from app.schemas.runtime import FileContentOut, FileEntryOut, FileWrite

router = APIRouter(prefix="/api/projects/{project_id}/files", tags=["files"])


@router.get("", response_model=list[FileEntryOut])
async def list_files(project_id: str, c: Container, path: str = ".") -> list[FileEntryOut]:
    return await c.files.list_dir(project_id, path)


@router.get("/content", response_model=FileContentOut)
async def read_file(project_id: str, path: str, c: Container) -> FileContentOut:
    return await c.files.read(project_id, path)


@router.put("/content")
async def write_file(project_id: str, path: str, body: FileWrite, c: Container) -> dict[str, Any]:
    return await c.files.write(project_id, path, body.content)


@router.delete("")
async def delete_file(project_id: str, path: str, c: Container) -> dict[str, Any]:
    return await c.files.delete(project_id, path)
