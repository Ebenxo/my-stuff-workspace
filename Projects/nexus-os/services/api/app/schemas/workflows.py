"""Workflows: a trigger, typed nodes and edges, stored as one versioned definition; runs and schedules."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.common import StrictModel

NodeKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
NodeType = Literal[
    "trigger", "agent", "tool", "condition", "approval", "transform", "output", "delay", "loop", "subworkflow"
]
MAX_NODES = 50


class Position(BaseModel):
    x: float = 0
    y: float = 0


class WorkflowNode(StrictModel):
    id: NodeKey
    type: NodeType
    label: str = Field(default="", max_length=80)
    config: dict[str, Any] = Field(default_factory=dict)
    position: Position = Field(default_factory=Position)
    continue_on_error: bool = False  # a failure becomes this node's output instead of stopping the run


class WorkflowEdge(StrictModel):
    id: str = Field(min_length=1, max_length=90)
    source: NodeKey
    target: NodeKey
    # Only from condition and approval nodes: which outcome this edge follows ("true" = approved).
    branch: Literal["true", "false"] | None = None


class WorkflowInput(StrictModel):
    name: NodeKey
    type: Literal["text", "number", "boolean"] = "text"
    required: bool = True
    default: str | float | bool | None = None
    description: str = Field(default="", max_length=200)


class WorkflowDefinition(StrictModel):
    inputs: list[WorkflowInput] = Field(default_factory=list, max_length=20)
    nodes: list[WorkflowNode] = Field(default_factory=list, max_length=MAX_NODES)
    edges: list[WorkflowEdge] = Field(default_factory=list, max_length=MAX_NODES * 3)


# ---- per-type node configuration -------------------------------------------------------------


class AgentNodeConfig(StrictModel):
    agent: str = Field(min_length=1, max_length=60)
    prompt: str = Field(min_length=1, max_length=20_000)
    model: str | None = Field(default=None, max_length=300)


class ToolNodeConfig(StrictModel):
    tool: str = Field(min_length=1, max_length=120)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ConditionNodeConfig(StrictModel):
    expression: str = Field(min_length=1, max_length=2000)


class ApprovalNodeConfig(StrictModel):
    message: str = Field(min_length=1, max_length=2000)


class ValuesNodeConfig(StrictModel):
    """transform and output nodes: each value is an expression."""

    values: dict[NodeKey, str] = Field(default_factory=dict, max_length=20)


class DelayNodeConfig(StrictModel):
    seconds: int = Field(ge=1, le=86_400)


class LoopBody(StrictModel):
    type: Literal["agent", "tool"]
    config: dict[str, Any]


class LoopNodeConfig(StrictModel):
    items: str = Field(min_length=1, max_length=2000, description="An expression giving a list")
    max_items: int = Field(default=10, ge=1, le=50)
    body: LoopBody


class SubworkflowNodeConfig(StrictModel):
    workflow_id: str = Field(min_length=1, max_length=40)
    inputs: dict[NodeKey, str] = Field(default_factory=dict, max_length=20)


CONFIG_MODELS: dict[str, type[BaseModel] | None] = {
    "trigger": None,
    "agent": AgentNodeConfig,
    "tool": ToolNodeConfig,
    "condition": ConditionNodeConfig,
    "approval": ApprovalNodeConfig,
    "transform": ValuesNodeConfig,
    "output": ValuesNodeConfig,
    "delay": DelayNodeConfig,
    "loop": LoopNodeConfig,
    "subworkflow": SubworkflowNodeConfig,
}

# ---- workflows ----------------------------------------------------------------------------------


class WorkflowCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    project_id: str
    definition: WorkflowDefinition | None = None  # a starter graph when omitted


class WorkflowUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    definition: WorkflowDefinition | None = None
    enabled: bool | None = None


class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    description: str
    version: int
    enabled: bool
    definition: WorkflowDefinition
    created_at: datetime
    updated_at: datetime


class WorkflowVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    definition: WorkflowDefinition
    created_at: datetime


class ValidationIssue(BaseModel):
    node: str | None = None
    message: str


class ValidationReport(BaseModel):
    ok: bool
    issues: list[ValidationIssue]


# ---- runs ---------------------------------------------------------------------------------------


class WorkflowRunStatus(StrEnum):
    RUNNING = "RUNNING"
    WAITING = "WAITING"  # a node waits for a person (an approval node, or a tool/agent approval)
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def terminal(self) -> bool:
        return self in (WorkflowRunStatus.COMPLETED, WorkflowRunStatus.FAILED, WorkflowRunStatus.CANCELLED)


NodeStatus = Literal["PENDING", "RUNNING", "WAITING", "COMPLETED", "SKIPPED", "FAILED", "CANCELLED"]


class NodeState(BaseModel):
    status: NodeStatus = "PENDING"
    output: Any = None
    error: dict[str, Any] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    run_id: str | None = None  # agent node: its agent run
    child_run_id: str | None = None  # subworkflow node: the child workflow run
    resume: bool = False  # agent node: continue run_id from its checkpoint instead of starting fresh
    approval_id: str | None = None  # tool node: the approval it is (or was last) waiting on
    attempts: int = 0


class RunWorkflow(StrictModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workflow_id: str
    workflow_version: int
    project_id: str
    status: WorkflowRunStatus
    unattended: bool
    schedule_id: str | None
    parent_run_id: str | None
    depth: int = 0
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    node_states: dict[str, NodeState]
    error: dict[str, Any] | None
    started_at: datetime
    finished_at: datetime | None


class WorkflowRunDetail(BaseModel):
    run: WorkflowRunOut
    definition: WorkflowDefinition  # the version this run used
    name: str


class NodeDecision(StrictModel):
    note: str = Field(default="", max_length=2000)


# ---- schedules ----------------------------------------------------------------------------------


class ScheduleCreate(StrictModel):
    workflow_id: str
    cron: str = Field(min_length=1, max_length=120)
    timezone: str = Field(default="UTC", max_length=64)
    inputs: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ScheduleUpdate(StrictModel):
    cron: str | None = Field(default=None, min_length=1, max_length=120)
    timezone: str | None = Field(default=None, max_length=64)
    inputs: dict[str, Any] | None = None
    enabled: bool | None = None


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workflow_id: str
    cron: str
    timezone: str
    inputs: dict[str, Any]
    enabled: bool
    description: str = ""
    last_run_at: datetime | None
    last_run_id: str | None
    last_status: str | None
    next_run_at: datetime | None
    created_at: datetime


class CronPreview(BaseModel):
    description: str
    next_runs: list[datetime]
