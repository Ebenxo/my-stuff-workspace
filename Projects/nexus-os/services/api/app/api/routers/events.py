from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Query
from fastapi.responses import StreamingResponse

from app.api.deps import Container
from app.events.sse import event_stream
from app.repositories.events import EventFilter
from app.schemas.events import ChainVerification, EventRecord

router = APIRouter(prefix="/api/events", tags=["events"])


def _types(csv: str | None) -> frozenset[str] | None:
    return frozenset(t for t in (csv or "").split(",") if t) or None


def _filter(
    project_id: str | None,
    objective_id: str | None,
    task_id: str | None,
    run_id: str | None,
    types: str | None,
    exclude_types: str | None = None,
) -> EventFilter:
    return EventFilter(
        project_id=project_id,
        objective_id=objective_id,
        task_id=task_id,
        run_id=run_id,
        types=_types(types),
        exclude_types=_types(exclude_types),
    )


@router.get("", response_model=list[EventRecord])
async def list_events(
    c: Container,
    project_id: str | None = None,
    objective_id: str | None = None,
    task_id: str | None = None,
    run_id: str | None = None,
    types: Annotated[str | None, Query(description="Comma-separated event types")] = None,
    exclude_types: Annotated[
        str | None, Query(description="Comma-separated event types to leave out")
    ] = None,
    after_seq: int = 0,
    before_seq: Annotated[
        int, Query(description="Only events older than this seq (page back in history)")
    ] = 0,
    limit: int = 200,
    newest_first: bool = False,
) -> list[EventRecord]:
    flt = _filter(project_id, objective_id, task_id, run_id, types, exclude_types)
    return await c.bus.query(
        flt,
        after_seq=after_seq,
        before_seq=max(before_seq, 0),
        limit=min(max(limit, 1), 1000),
        newest_first=newest_first,
    )


@router.get("/verify", response_model=ChainVerification)
async def verify_events(c: Container, project_id: str | None = None) -> ChainVerification:
    """Recompute the audit-log hash chain (all chains, or one project's)."""
    return await (c.bus.verify(project_id) if project_id else c.bus.verify())


@router.get("/stream")
async def stream_events(
    c: Container,
    project_id: str | None = None,
    objective_id: str | None = None,
    task_id: str | None = None,
    run_id: str | None = None,
    types: str | None = None,
    after: int | None = None,
    last_event_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    """SSE feed. Resume with ``Last-Event-ID`` (or ``after``) to replay without gaps."""
    resume = after
    if resume is None and last_event_id and last_event_id.isdigit():
        resume = int(last_event_id)
    flt = _filter(project_id, objective_id, task_id, run_id, types)
    return StreamingResponse(
        event_stream(c.bus, flt, after_seq=resume),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
