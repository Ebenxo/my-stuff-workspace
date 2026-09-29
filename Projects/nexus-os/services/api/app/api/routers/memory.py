from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import Field

from app.api.deps import Container
from app.repositories.memory_store import MemoryFilter
from app.schemas.common import StrictModel
from app.schemas.memory import (
    CompressionReport,
    MemoryCreate,
    MemoryHit,
    MemoryItemOut,
    MemoryStats,
    MemoryUpdate,
)

router = APIRouter(prefix="/api", tags=["memory"])


class CompressBody(StrictModel):
    project_id: str
    older_than_days: int = Field(default=30, ge=0, le=3650)


@router.get("/memory", response_model=list[MemoryItemOut])
async def list_memory(
    c: Container,
    project_id: str | None = None,
    scope: Literal["project", "global"] | None = None,
    status_filter: Literal["active", "pending", "deleted"] = "active",
    tag: str | None = None,
    source: Literal["user", "agent", "objective", "summary"] | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[MemoryItemOut]:
    f = MemoryFilter(
        scopes=(scope,) if scope else (),
        project_id=project_id,
        statuses=(status_filter,),
        tag=tag.lower() if tag else None,
        source_kind=source,
        text=q.strip() if q and q.strip() else None,
    )
    return await c.memory.list_items(f, limit=min(max(limit, 1), 500), offset=max(offset, 0))


@router.get("/memory/stats", response_model=MemoryStats)
async def memory_stats(c: Container, project_id: str | None = None) -> MemoryStats:
    return await c.memory.stats(project_id)


@router.get("/memory/search", response_model=list[MemoryHit])
async def search_memory(
    c: Container,
    q: str,
    project_id: str | None = None,
    scope: Literal["any", "project", "global"] = "any",
    k: int = 10,
) -> list[MemoryHit]:
    """What an agent in this project would recall for ``q``, with the score breakdown. The person sees
    private memories too; browsing does not count as use."""
    scopes = ("project", "global") if scope == "any" else (scope,)
    return await c.memory.search(
        q, scopes=scopes, project_id=project_id, k=min(max(k, 1), 50), touch=False, include_private=True
    )


@router.post("/memory", response_model=MemoryItemOut, status_code=status.HTTP_201_CREATED)
async def create_memory(body: MemoryCreate, c: Container) -> MemoryItemOut:
    if body.scope == "project":
        await c.projects.get(body.project_id or "")  # 404 for an unknown project
    return await c.memory.create_by_user(body)


@router.post("/memory/compress", response_model=CompressionReport)
async def compress_memory(body: CompressBody, c: Container) -> CompressionReport:
    await c.projects.get(body.project_id)
    return await c.memory.compress(body.project_id, older_than_days=body.older_than_days)


@router.get("/memory/{item_id}", response_model=MemoryItemOut)
async def get_memory(item_id: str, c: Container) -> MemoryItemOut:
    return await c.memory.get(item_id)


@router.patch("/memory/{item_id}", response_model=MemoryItemOut)
async def update_memory(item_id: str, body: MemoryUpdate, c: Container) -> MemoryItemOut:
    return await c.memory.update(item_id, body)


@router.post("/memory/{item_id}/confirm", response_model=MemoryItemOut)
async def confirm_memory(item_id: str, c: Container) -> MemoryItemOut:
    return await c.memory.confirm(item_id)


@router.post("/memory/{item_id}/dismiss", response_model=MemoryItemOut)
async def dismiss_memory(item_id: str, c: Container) -> MemoryItemOut:
    return await c.memory.reject(item_id)


@router.post("/memory/{item_id}/restore", response_model=MemoryItemOut)
async def restore_memory(item_id: str, c: Container) -> MemoryItemOut:
    return await c.memory.restore(item_id)


@router.post("/memory/{item_id}/undo-compression", response_model=list[MemoryItemOut])
async def undo_compression(item_id: str, c: Container) -> list[MemoryItemOut]:
    return await c.memory.undo_compression(item_id)


@router.delete("/memory/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(item_id: str, c: Container, purge: bool = False) -> Response:
    """Delete (recoverable from the Deleted list) or, with ``purge``, erase permanently."""
    if purge:
        await c.memory.purge(item_id)
    else:
        await c.memory.delete(item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
