"""Memory items, retrieval results, context reports and universal search."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.common import StrictModel

MemoryScopeName = Literal["conversation", "project", "global"]
MemoryStatus = Literal["active", "pending", "deleted"]
SourceKind = Literal["user", "agent", "objective", "summary"]
Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class MemorySource(BaseModel):
    """Where a memory came from. Always shown next to it."""

    kind: SourceKind
    agent: str | None = None  # agent slug
    run_id: str | None = None
    task_id: str | None = None
    objective_id: str | None = None
    tainted: bool = False  # written by a run that had read untrusted content
    private: bool = False  # from a "keep on this device" run: only ever recalled into private runs


class MemoryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scope: MemoryScopeName
    project_id: str | None
    content: str
    summary: str
    importance: float
    source: MemorySource
    tags: list[str]
    status: MemoryStatus
    content_hash: str
    access_count: int
    last_accessed_at: datetime | None
    merged_into: str | None
    created_at: datetime
    updated_at: datetime

    @property
    def pinned(self) -> bool:
        return self.importance >= 1.0


class MemoryCreate(StrictModel):
    """A memory the person writes themselves."""

    scope: Literal["project", "global"] = "project"
    project_id: str | None = None
    content: str = Field(min_length=3, max_length=4000)
    tags: list[Tag] = Field(default_factory=list, max_length=12)
    pinned: bool = False


class MemoryUpdate(StrictModel):
    content: str | None = Field(default=None, min_length=3, max_length=4000)
    tags: list[Tag] | None = Field(default=None, max_length=12)
    pinned: bool | None = None


class ScoreBreakdown(BaseModel):
    semantic: float
    keyword: float
    recency: float
    importance: float
    task: float
    total: float


class MemoryHit(BaseModel):
    item: MemoryItemOut
    score: ScoreBreakdown


class MemoryStats(BaseModel):
    active: int
    pending: int
    deleted: int


class CompressionReport(BaseModel):
    project_id: str
    groups: int
    compressed: int
    summaries: list[str]  # ids of the new summary items


# ---- context ------------------------------------------------------------------------------------


class ContextEntry(BaseModel):
    source: str  # e.g. "task:t1", "memory:mem_…"
    kind: Literal["upstream", "memory", "given"]
    tokens: int
    score: float
    included: bool
    truncated: bool = False
    reason: str
    memory_id: str | None = None


class ContextReport(BaseModel):
    """What an agent was given besides its task, and why. Stored with the run and shown in the UI."""

    budget_tokens: int
    used_tokens: int
    entries: list[ContextEntry] = Field(default_factory=list)
    memory_query: str = ""
    notes: list[str] = Field(default_factory=list)


# ---- universal search --------------------------------------------------------------------------

SearchKind = Literal["project", "objective", "artifact", "memory"]


class SearchHit(BaseModel):
    kind: SearchKind
    id: str
    project_id: str | None
    title: str
    snippet: str
    score: float


class SearchResults(BaseModel):
    query: str
    hits: list[SearchHit]
    engine: Literal["fts5", "like"]


def source_dict(source: MemorySource | dict[str, Any]) -> dict[str, Any]:
    return source.model_dump() if isinstance(source, MemorySource) else dict(source)
