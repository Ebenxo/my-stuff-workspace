"""Workflows (migration 0005): definitions with version history, runs, and schedules."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UTCDateTime, utc_default


class Workflow(TimestampMixin, Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON)  # the current version's graph
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)  # runs keep pointing at it


class WorkflowVersion(Base):
    __tablename__ = "workflow_versions"

    workflow_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("workflows.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_default)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (Index("ix_workflow_runs_status", "status"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(40), index=True)
    workflow_version: Mapped[int] = mapped_column(Integer)
    project_id: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(20))
    unattended: Mapped[bool] = mapped_column(Boolean, default=False)
    schedule_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    parent_run_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    depth: Mapped[int] = mapped_column(Integer, default=0)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    outputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    node_states: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_default)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(40), index=True)
    cron: Mapped[str] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_run_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_default)
