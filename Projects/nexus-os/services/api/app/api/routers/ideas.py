from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response, status

from app.api.deps import Container
from app.schemas.ideas import IdeaCreate, IdeaObjectiveOut, IdeaOut, IdeaToObjective, IdeaUpdate, TimelineOut

router = APIRouter(prefix="/api", tags=["ideas"])


@router.get("/ideas", response_model=list[IdeaOut])
async def list_ideas(
    c: Container,
    status_filter: Literal["open", "done", "all"] = "open",
    kind: Literal["idea", "note", "todo"] | None = None,
    project_id: str | None = None,
    pinned: bool | None = None,
    q: str | None = None,
    limit: int = 200,
) -> list[IdeaOut]:
    return await c.ideas.list_ideas(
        status=None if status_filter == "all" else status_filter,
        kind=kind,
        project_id=project_id,
        pinned=pinned,
        q=q,
        limit=min(max(limit, 1), 500),
    )


@router.get("/ideas/due-count")
async def ideas_due_count(c: Container) -> dict[str, int]:
    """Open to-dos (and dated ideas or notes) whose due time has come."""
    return {"count": await c.ideas.due_count()}


@router.post("/ideas", response_model=IdeaOut, status_code=status.HTTP_201_CREATED)
async def create_idea(body: IdeaCreate, c: Container) -> IdeaOut:
    return await c.ideas.create(body)


@router.get("/ideas/{idea_id}", response_model=IdeaOut)
async def get_idea(idea_id: str, c: Container) -> IdeaOut:
    return await c.ideas.get(idea_id)


@router.patch("/ideas/{idea_id}", response_model=IdeaOut)
async def update_idea(idea_id: str, body: IdeaUpdate, c: Container) -> IdeaOut:
    return await c.ideas.update(idea_id, body)


@router.delete("/ideas/{idea_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_idea(idea_id: str, c: Container) -> Response:
    await c.ideas.delete(idea_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/ideas/{idea_id}/objective", response_model=IdeaObjectiveOut, status_code=status.HTTP_202_ACCEPTED
)
async def start_idea_as_objective(idea_id: str, body: IdeaToObjective, c: Container) -> IdeaObjectiveOut:
    """Start the idea as an objective (planning begins in the background); the idea is marked done."""
    return await c.ideas.start_objective(idea_id, body)


@router.get("/timeline", response_model=TimelineOut, tags=["timeline"])
async def timeline(c: Container, project_id: str | None = None) -> TimelineOut:
    """Now, waiting on you, coming up, and pinned. History is the event log (``/api/events``)."""
    return await c.timeline.build(project_id=project_id)
