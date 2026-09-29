"""Agent runtime tables (migration 0002): agents, runs, tools, tool calls, approvals, artifacts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UTCDateTime, utc_default


class Agent(TimestampMixin, Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(40), default="bot")
    color: Mapped[str] = mapped_column(String(20), default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    preferred_model: Mapped[str | None] = mapped_column(String(300), nullable=True)
    fallback_models: Mapped[list[Any]] = mapped_column(JSON, default=list)
    tools: Mapped[list[Any]] = mapped_column(JSON, default=list)
    permissions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    memory_scope: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    max_steps: Mapped[int] = mapped_column(Integer, default=20)
    max_runtime_s: Mapped[int] = mapped_column(Integer, default=300)
    max_tool_calls: Mapped[int] = mapped_column(Integer, default=40)
    token_budget: Mapped[int] = mapped_column(Integer, default=200_000)
    temperature: Mapped[float] = mapped_column(Float, default=0.2)
    reasoning_mode: Mapped[str] = mapped_column(String(10), default="off")
    status: Mapped[str] = mapped_column(String(20), default="idle")
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    knowledge_sources: Mapped[list[Any]] = mapped_column(JSON, default=list)
    overrides: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_status", "status"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(40), index=True)
    project_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    objective_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(24))
    model: Mapped[str | None] = mapped_column(String(300), nullable=True)
    step_count: Mapped[int] = mapped_column(Integer, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    request: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    checkpoint: Mapped[list[Any]] = mapped_column(JSON, default=list)
    # What the ContextBuilder gave the agent and why (migration 0004); shown on the run page.
    context_report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_default)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    @property
    def prompt(self) -> str:
        """The task in the person's words, or the orchestrator's title for it (redacted at write time)."""
        req = self.request or {}
        return str(req.get("title") or req.get("prompt", ""))[:200]


class Tool(Base):
    __tablename__ = "tools"

    name: Mapped[str] = mapped_column(String(120), primary_key=True)
    source: Mapped[str] = mapped_column(String(120), default="builtin")
    description: Mapped[str] = mapped_column(Text, default="")
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(12))
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    capabilities: Mapped[list[Any]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_default, onupdate=utc_default)
    # MCP tools (migration 0006): a hash of the definition as last seen, and why a tool was switched off
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ToolCall(Base):
    __tablename__ = "tool_calls"
    __table_args__ = (Index("ix_tool_calls_status", "status"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    project_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    tool_name: Mapped[str] = mapped_column(String(120), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(24))
    risk_level: Mapped[str] = mapped_column(String(12), default="SAFE")
    approval_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_default)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (Index("ix_approvals_status", "status"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(120))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    edited_arguments: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    risk_level: Mapped[str] = mapped_column(String(12))
    impact: Mapped[str] = mapped_column(Text, default="")
    session_grantable: Mapped[bool] = mapped_column(Boolean, default=False)
    tainted: Mapped[bool] = mapped_column(Boolean, default=False)
    taint_sources: Mapped[list[Any]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    decided_by: Mapped[str | None] = mapped_column(String(60), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_default)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Artifact(TimestampMixin, Base):
    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("project_id", "path", name="uq_artifacts_project_path"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(40), index=True)
    objective_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    type: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    path: Mapped[str] = mapped_column(String(400))
    version: Mapped[int] = mapped_column(Integer, default=1)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ArtifactVersion(Base):
    __tablename__ = "artifact_versions"
    __table_args__ = (
        UniqueConstraint("artifact_id", "version", name="uq_artifact_versions_artifact_version"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    stored_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[str | None] = mapped_column(String(60), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_default)
