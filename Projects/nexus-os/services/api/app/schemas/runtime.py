"""Runs, tool calls, approvals, artifacts: enums and API DTOs."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.risk import RiskLevel
from app.schemas.common import StrictModel

ArtifactType = Literal[
    "document",
    "markdown",
    "code",
    "spreadsheet",
    "chart",
    "image_ref",
    "presentation",
    "report",
    "json",
    "dataset",
    "website",
]


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_INPUT = "WAITING_INPUT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    INTERRUPTED = "INTERRUPTED"

    @property
    def terminal(self) -> bool:
        return self in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.TIMED_OUT)


class ToolCallStatus(StrEnum):
    PROPOSED = "PROPOSED"
    DENIED = "DENIED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED_ONCE = "APPROVED_ONCE"
    APPROVED_SESSION = "APPROVED_SESSION"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    project_id: str | None
    objective_id: str | None
    task_id: str | None
    status: RunStatus
    model: str | None
    step_count: int
    tool_call_count: int
    tokens_in: int
    tokens_out: int
    attempt: int
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    started_at: datetime
    finished_at: datetime | None


class AgentRunRequest(StrictModel):
    agent: str = Field(min_length=1, max_length=60, description="Agent id or slug")
    project_id: str
    prompt: str = Field(min_length=1, max_length=20_000)
    model: str | None = Field(
        default=None, max_length=300, description="Manual model override: '<provider_id>:<model>'"
    )
    private: bool = False


class ToolCallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str | None
    task_id: str | None
    project_id: str | None
    tool_name: str
    summary: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None
    status: ToolCallStatus
    risk_level: RiskLevel
    approval_id: str | None
    provenance: dict[str, Any]
    error: dict[str, Any] | None
    duration_ms: int | None
    started_at: datetime
    finished_at: datetime | None


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    run_id: str | None
    task_id: str | None
    agent_id: str | None
    tool_name: str
    arguments: dict[str, Any]
    edited_arguments: dict[str, Any] | None
    reason: str
    risk_level: RiskLevel
    impact: str
    session_grantable: bool
    tainted: bool
    taint_sources: list[str]
    status: ApprovalStatus
    decided_by: str | None
    decision_note: str | None
    created_at: datetime
    decided_at: datetime | None


class ApprovalDecision(StrictModel):
    decision: Literal["approve_once", "approve_session", "deny"]
    edited_arguments: dict[str, Any] | None = None
    note: str | None = Field(default=None, max_length=1000)


class SessionGrantOut(BaseModel):
    id: str
    project_id: str | None
    tool_name: str
    created_at: datetime


class ToolOut(BaseModel):
    name: str
    source: str
    description: str
    risk_level: RiskLevel
    requires_approval: bool
    capabilities: list[str]
    enabled: bool
    input_schema: dict[str, Any]


class ToolToggle(StrictModel):
    enabled: bool


class ArtifactVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    sha256: str
    size: int
    created_by: str | None
    note: str
    created_at: datetime


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    objective_id: str | None
    task_id: str | None
    agent_id: str | None
    type: ArtifactType
    name: str
    path: str
    version: int
    meta: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ArtifactContent(BaseModel):
    artifact: ArtifactOut
    version: int
    content: str
    truncated: bool


class FileEntryOut(BaseModel):
    path: str
    kind: Literal["file", "dir"]
    size: int
    modified: float


class FileContentOut(BaseModel):
    path: str
    content: str
    truncated: bool


class FileWrite(StrictModel):
    content: str = Field(max_length=5_000_000)
