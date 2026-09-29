"""Agent definitions and the structured contracts agents speak."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.risk import RiskLevel
from app.schemas.common import StrictModel

ReasoningMode = Literal["off", "light", "deep"]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{1,40}$")]
Text80 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class AgentPermissions(StrictModel):
    """What an agent may even *propose*. The policy engine still judges every action."""

    max_risk: RiskLevel = RiskLevel.MODERATE
    may_request_approval: bool = True


ScopeName = Literal["conversation", "project", "global"]


def _default_read() -> list[ScopeName]:
    return ["conversation", "project"]


def _default_write() -> list[ScopeName]:
    return ["project"]


class MemoryScope(StrictModel):
    read: list[ScopeName] = Field(default_factory=_default_read)
    write: list[ScopeName] = Field(default_factory=_default_write)


class AgentDefinition(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    role: str
    description: str = ""
    icon: str = "bot"
    color: str = ""
    system_prompt: str = ""
    preferred_model: str | None = None
    fallback_models: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)  # exact names or "prefix*" patterns
    permissions: AgentPermissions = Field(default_factory=AgentPermissions)
    memory_scope: MemoryScope = Field(default_factory=MemoryScope)
    max_steps: int = 20
    max_runtime_s: int = 300
    max_tool_calls: int = 40
    token_budget: int = 200_000
    temperature: float = 0.2
    reasoning_mode: ReasoningMode = "off"
    status: Literal["idle", "busy", "disabled"] = "idle"
    builtin: bool = False
    knowledge_sources: list[str] = Field(default_factory=list)
    version: int = 1


class AgentCreate(StrictModel):
    name: Text80
    role: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    description: str = Field(default="", max_length=2000)
    icon: str = Field(default="bot", max_length=40)
    system_prompt: str = Field(default="", max_length=20_000)
    preferred_model: str | None = Field(default=None, max_length=300)
    fallback_models: list[str] = Field(default_factory=list, max_length=6)
    tools: list[str] = Field(default_factory=list, max_length=60)
    permissions: AgentPermissions = Field(default_factory=AgentPermissions)
    memory_scope: MemoryScope = Field(default_factory=MemoryScope)
    max_steps: int = Field(default=20, ge=1, le=100)
    max_runtime_s: int = Field(default=300, ge=10, le=3600)
    max_tool_calls: int = Field(default=40, ge=0, le=200)
    token_budget: int = Field(default=200_000, ge=1000, le=5_000_000)
    temperature: float = Field(default=0.2, ge=0, le=1)
    reasoning_mode: ReasoningMode = "off"
    knowledge_sources: list[str] = Field(default_factory=list, max_length=20)


class AgentUpdate(StrictModel):
    name: Text80 | None = None
    role: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None = None
    description: str | None = Field(default=None, max_length=2000)
    icon: str | None = Field(default=None, max_length=40)
    system_prompt: str | None = Field(default=None, max_length=20_000)
    preferred_model: str | None = Field(default=None, max_length=300)
    fallback_models: list[str] | None = Field(default=None, max_length=6)
    tools: list[str] | None = Field(default=None, max_length=60)
    permissions: AgentPermissions | None = None
    memory_scope: MemoryScope | None = None
    max_steps: int | None = Field(default=None, ge=1, le=100)
    max_runtime_s: int | None = Field(default=None, ge=10, le=3600)
    max_tool_calls: int | None = Field(default=None, ge=0, le=200)
    token_budget: int | None = Field(default=None, ge=1000, le=5_000_000)
    temperature: float | None = Field(default=None, ge=0, le=1)
    reasoning_mode: ReasoningMode | None = None
    status: Literal["idle", "disabled"] | None = None


# ---- the step protocol ---------------------------------------------------------------------


class OutputRef(BaseModel):
    kind: Literal["text", "data", "artifact"] = "text"
    name: str = Field(max_length=200)
    value: str | None = Field(default=None, max_length=50_000)
    artifact_id: str | None = None


class ArtifactRef(BaseModel):
    artifact_id: str
    name: str
    version: int = 1


class TaskResult(BaseModel):
    """What an agent hands back when it believes its task is done."""

    status: Literal["completed", "partial", "failed", "needs_input"] = "completed"
    summary: str = Field(max_length=8000)
    outputs: list[OutputRef] = Field(default_factory=list, max_length=50)
    artifacts: list[ArtifactRef] = Field(default_factory=list, max_length=50)
    errors: list[str] = Field(default_factory=list, max_length=20)
    recommendations: list[str] = Field(default_factory=list, max_length=20)


class ToolCallAction(BaseModel):
    type: Literal["tool_call"]
    tool: str = Field(max_length=120)
    arguments: dict[str, Any] = Field(default_factory=dict)


class FinishAction(BaseModel):
    type: Literal["finish"]
    result: TaskResult


class AskHumanAction(BaseModel):
    type: Literal["ask_human"]
    question: str = Field(max_length=2000)
    options: list[str] = Field(default_factory=list, max_length=8)


class AgentStep(BaseModel):
    """One model turn. ``summary`` is a short public description of the intent: never reasoning."""

    summary: str = Field(max_length=300)
    action: Annotated[ToolCallAction | FinishAction | AskHumanAction, Field(discriminator="type")]
