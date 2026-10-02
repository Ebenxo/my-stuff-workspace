"""Ideas, notes and to-dos the person keeps, and the timeline that brings everything together."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints

from app.schemas.common import StrictModel
from app.schemas.orchestration import ObjectiveOut, RunMode

IdeaKind = Literal["idea", "note", "todo"]
IdeaStatus = Literal["open", "done"]
IdeaText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class IdeaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    kind: IdeaKind
    text: str
    status: IdeaStatus
    pinned: bool
    due_at: datetime | None
    reminded_at: datetime | None
    done_at: datetime | None
    objective_id: str | None
    created_at: datetime
    updated_at: datetime


class IdeaCreate(StrictModel):
    text: IdeaText
    kind: IdeaKind = "idea"
    project_id: str | None = None
    pinned: bool = False
    due_at: AwareDatetime | None = None


class IdeaUpdate(StrictModel):
    """Only the fields sent are changed. Send ``null`` to clear ``project_id`` or ``due_at``."""

    text: IdeaText | None = None
    kind: IdeaKind | None = None
    project_id: str | None = None
    pinned: bool | None = None
    due_at: AwareDatetime | None = None
    status: IdeaStatus | None = None


class IdeaToObjective(StrictModel):
    """Start an idea as an objective. The project defaults to the idea's own."""

    project_id: str | None = None
    run_mode: RunMode = "review_plan"
    private: bool = False


class IdeaObjectiveOut(BaseModel):
    idea: IdeaOut
    objective: ObjectiveOut


# ---- timeline -----------------------------------------------------------------------------------

TimelineKind = Literal["objective", "agent_run", "workflow_run", "schedule", "approval", "idea"]


class TimelineItem(BaseModel):
    kind: TimelineKind
    id: str
    title: str
    detail: str = ""
    status: str
    project_id: str | None
    at: datetime | None  # started (now), raised (waiting), due or next run (next), created (pinned)
    ref_id: str | None = None  # schedule: its workflow; approval: the run waiting on it
    idea_kind: IdeaKind | None = None  # idea: idea, note or to-do


class TimelineOut(BaseModel):
    """What is happening now, what needs the person, what is coming up, and what they pinned."""

    generated_at: datetime
    now: list[TimelineItem]
    waiting: list[TimelineItem]
    next: list[TimelineItem]
    pinned: list[TimelineItem]
