"""Objectives, plans, task graphs, reviews and verification: structured contracts and API DTOs.

Everything agents exchange here is a Pydantic model. Free text appears only inside declared fields.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.agents import StepWith
from app.schemas.common import StrictModel

TaskKey = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9_-]{1,24}$")]
Complexity = Literal["trivial", "small", "medium", "large"]

# ---- statuses ---------------------------------------------------------------------------------


class ObjectiveStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PLANNING = "PLANNING"
    AWAITING_PLAN_APPROVAL = "AWAITING_PLAN_APPROVAL"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    PAUSED = "PAUSED"  # waiting on a person (a question, a blocked task) or interrupted by a restart
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def terminal(self) -> bool:
        return self in _TERMINAL_OBJECTIVE


_TERMINAL_OBJECTIVE = {
    ObjectiveStatus.COMPLETED,
    ObjectiveStatus.PARTIAL,
    ObjectiveStatus.FAILED,
    ObjectiveStatus.CANCELLED,
}


class TaskStatus(StrEnum):
    WAITING = "WAITING"  # dependencies not finished
    QUEUED = "QUEUED"  # ready; will start when a slot is free
    RUNNING = "RUNNING"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"  # its agent is waiting on an approval card
    BLOCKED = "BLOCKED"  # needs a person: a question, or a failure that recovery could not handle
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"  # an optional task that was skipped; dependents continue without its output
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def settled(self) -> bool:
        return self in (
            TaskStatus.COMPLETED,
            TaskStatus.SKIPPED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        )


TaskKind = Literal["work", "review", "revise", "verify"]
RunMode = Literal["review_plan", "auto"]  # show the plan first, or start as soon as it is valid
ExecutionMode = Literal["normal", "safe_only"]  # safe_only: only SAFE actions auto-run, all else asks


# ---- the plan ---------------------------------------------------------------------------------


class PlanTask(BaseModel):
    key: TaskKey = Field(description="Short id used in depends_on, e.g. 't1'.")
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(max_length=4000, description="What to do and what good output looks like.")
    agent: str = Field(max_length=60, description="Slug of the specialist, e.g. 'researcher'.")
    depends_on: list[TaskKey] = Field(default_factory=list, max_length=12)
    tools: list[str] = Field(default_factory=list, max_length=20, description="Tools it will likely need.")
    expected_outputs: list[str] = Field(default_factory=list, max_length=10)
    approval_required: bool = False
    optional: bool = False
    review: bool = Field(default=False, description="Have the Critic review this task's output.")
    complexity: Complexity = "small"


class PlanResult(BaseModel):
    objective: str = Field(max_length=2000)
    assumptions: list[str] = Field(default_factory=list, max_length=15)
    constraints: list[str] = Field(default_factory=list, max_length=15)
    tasks: list[PlanTask] = Field(min_length=1, max_length=20)
    risks: list[str] = Field(default_factory=list, max_length=15)
    required_approvals: list[str] = Field(default_factory=list, max_length=15)
    completion_criteria: list[str] = Field(min_length=1, max_length=15)
    complexity: Complexity = "small"


class PlanStep(StepWith[PlanResult]):
    """A Planner step: it may read project files, then finishes with a PlanResult."""


# ---- review and verification ------------------------------------------------------------------

Severity = Literal["blocker", "major", "minor", "nit"]


class ReviewIssue(BaseModel):
    severity: Severity
    category: str = Field(default="quality", max_length=40)
    location: str = Field(default="", max_length=300)
    description: str = Field(max_length=2000)
    suggestion: str = Field(default="", max_length=2000)

    @property
    def blocking(self) -> bool:
        return self.severity in ("blocker", "major")


class ReviewResult(BaseModel):
    verdict: Literal["approve", "revise"]
    summary: str = Field(max_length=2000)
    issues: list[ReviewIssue] = Field(default_factory=list, max_length=30)
    checks: dict[str, bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _revise_needs_a_reason(self) -> ReviewResult:
        if self.verdict == "revise" and not self.issues:
            raise ValueError("a 'revise' verdict must list the issues to fix")
        return self


class ReviewStep(StepWith[ReviewResult]):
    """A Critic step: it reads the work, then finishes with a ReviewResult."""


class CriterionCheck(BaseModel):
    criterion: str = Field(max_length=500)
    met: bool
    evidence: str = Field(default="", max_length=2000)


class VerificationResult(BaseModel):
    verdict: Literal["PASS", "PARTIAL", "FAIL"]
    summary: str = Field(max_length=4000)
    criteria: list[CriterionCheck] = Field(default_factory=list, max_length=20)
    missing_requirements: list[str] = Field(default_factory=list, max_length=15)

    @model_validator(mode="after")
    def _consistent(self) -> VerificationResult:
        if self.verdict == "PASS" and any(not c.met for c in self.criteria):
            raise ValueError("PASS is only possible when every criterion is met")
        return self


class VerifyStep(StepWith[VerificationResult]):
    """A Verifier step: it checks the deliverables, then finishes with a VerificationResult."""


# ---- agent messages ---------------------------------------------------------------------------

MessageType = Literal[
    "TASK_REQUEST",
    "TASK_RESULT",
    "QUESTION",
    "ERROR",
    "STATUS",
    "REVIEW_REQUEST",
    "REVIEW_RESULT",
    "APPROVAL_REQUIRED",
]


class AgentMessage(BaseModel):
    """Structured collaboration record. Persisted as an AGENT_MESSAGE event."""

    id: str
    sender: str  # agent slug, "orchestrator" or "user"
    recipient: str
    task_id: str | None
    type: MessageType
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime


# ---- API ----------------------------------------------------------------------------------------


class ObjectiveCreate(StrictModel):
    project_id: str
    text: str = Field(min_length=3, max_length=20_000)
    run_mode: RunMode = "review_plan"
    model: str | None = Field(
        default=None, max_length=300, description="Manual model: '<provider_id>:<model>'"
    )
    private: bool = False


class ObjectiveRun(StrictModel):
    mode: ExecutionMode = "normal"


class PlanEdit(StrictModel):
    """Replace the plan's tasks before it runs. Validated exactly like a plan from the Planner."""

    tasks: list[PlanTask] = Field(min_length=1, max_length=20)
    completion_criteria: list[str] | None = Field(default=None, max_length=15)


class TaskAnswer(StrictModel):
    text: str = Field(min_length=1, max_length=10_000)


class ObjectiveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    text: str
    status: ObjectiveStatus
    run_mode: str
    execution_mode: str
    strategy: dict[str, Any] | None
    plan: dict[str, Any] | None
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    model: str | None
    private: bool
    replan_count: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    objective_id: str
    project_id: str
    key: str
    title: str
    description: str
    kind: str
    assigned_agent: str
    status: TaskStatus
    depends_on: list[str] = Field(default_factory=list)  # task ids
    inputs: dict[str, Any]
    outputs: dict[str, Any] | None
    attempts: int
    max_attempts: int
    approval_required: bool
    optional: bool
    review: bool
    round: int
    parent_task_id: str | None
    run_id: str | None
    resume: bool = False  # the next start continues run_id instead of starting fresh
    error: dict[str, Any] | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class ObjectiveDetail(BaseModel):
    objective: ObjectiveOut
    tasks: list[TaskOut]
    messages: list[AgentMessage]
