from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import Container
from app.schemas.memory import SearchKind, SearchResults

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search", response_model=SearchResults)
async def universal_search(
    c: Container,
    q: str = Query(min_length=1, max_length=200),
    project_id: str | None = None,
    kinds: list[SearchKind] = Query(default=[]),
    limit: int = 30,
) -> SearchResults:
    """Search projects, objectives, deliverables and memory at once."""
    return await c.universal_search.search(
        q, project_id=project_id, kinds=kinds, limit=min(max(limit, 1), 100)
    )
