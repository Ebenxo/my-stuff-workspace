"""Objective aggregate (migration 0003): objectives, tasks and task dependencies."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UTCDateTime, utc_default


class Objective(TimestampMixin, Base):
    __tablename__ = "objectives"
    __table_args__ = (Index("ix_objectives_status", "status"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(40), index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    run_mode: Mapped[str] = mapped_column(String(20), default="review_plan")
    execution_mode: Mapped[str] = mapped_column(String(20), default="normal")
    strategy: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    attachments: Mapped[list[Any]] = mapped_column(JSON, default=list)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    budget: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model: Mapped[str | None] = mapped_column(String(300), nullable=True)
    private: Mapped[bool] = mapped_column(Boolean, default=False)
    replan_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("objective_id", "key", name="uq_tasks_objective_key"),
        Index("ix_tasks_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    objective_id: Mapped[str] = mapped_column(ForeignKey("objectives.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(String(40), index=True)
    key: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(12), default="work")
    assigned_agent: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20))
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    outputs: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=2)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    optional: Mapped[bool] = mapped_column(Boolean, default=False)
    review: Mapped[bool] = mapped_column(Boolean, default=False)
    round: Mapped[int] = mapped_column(Integer, default=0)
    parent_task_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resume: Mapped[bool] = mapped_column(Boolean, default=False)  # continue run_id instead of starting fresh
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    position: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_default)


class TaskDependency(Base):
    __tablename__ = "task_dependencies"

    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    depends_on_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
